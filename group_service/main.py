# group_service/main.py
import os
from datetime import datetime, time
from typing import List, Dict
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, text

DB_URL = os.getenv("DATABASE_URL",
                   "postgresql://biofit:biofitpass@db:5432/biofitdb")
engine = create_engine(DB_URL, pool_pre_ping=True)

app = FastAPI(title="BioFit Group-Recommender")

# ����������������������������������������������������������������������������������
# 1) ��û ��Ű��
# ����������������������������������������������������������������������������������
class RecoReq(BaseModel):
    uid: str          # Streamlit ���� �Ѱ��� ���� ����� ID
    # �̹� �׽�Ʈ������ uid = 23RK3S �� ���� ��


# ����������������������������������������������������������������������������������
# 2) ���� ���� �⺻ ����
# ����������������������������������������������������������������������������������
CURRENT_USER_SLOTS = [
    (time(10, 0), time(11, 0)),
    (time(18, 0), time(19, 0)),
]
SLEEP_TIME = time(22, 0)
WAKE_TIME  = time(8, 0)


# ����������������������������������������������������������������������������������
# 3) ��ħ ���� ����
# ����������������������������������������������������������������������������������
def overlap(a_start: time, a_end: time,
            b_start: time, b_end: time,
            min_minutes: int = 30) -> bool:
    latest  = max(datetime.combine(datetime.today(), a_start),
                  datetime.combine(datetime.today(), b_start))
    earliest = min(datetime.combine(datetime.today(), a_end),
                   datetime.combine(datetime.today(), b_end))
    return (earliest - latest).total_seconds() / 60 >= min_minutes


# ����������������������������������������������������������������������������������
# 4) ��õ ����
# ����������������������������������������������������������������������������������
def get_reco() -> Dict[str, List[dict]]:
    with engine.begin() as conn:
        partners = pd.read_sql("""
            SELECT u.user_id, u.name, u.workout_level, u.image_url,
                   ps.slot_start, ps.slot_end
            FROM users u
            JOIN preferred_slots ps ON ps.user_id = u.user_id
        """, conn)
        groups = pd.read_sql("SELECT * FROM group_sessions", conn)

    # 4-1) ��Ʈ�� ��Ī
    partner_dict = {}          # user_id �� {info + slot list}
    for _, row in partners.iterrows():
        p_slot = (row.slot_start, row.slot_end)
        # ���� ���� ���� �� �ϳ��� ��ġ�� ��Ī
        if any(overlap(*p_slot, *cslot) for cslot in CURRENT_USER_SLOTS):
            info = partner_dict.setdefault(
                row.user_id,
                dict(name=row.name,
                     workout_level=row.workout_level,
                     image_url=row.image_url,
                     slots=[],
                    # �� ù ��° ������ preferred_* �ε� ����
                    preferred_start=str(row.slot_start),
                    preferred_end=str(row.slot_end))
                    )
            info["slots"].append(p_slot)

    # 4-2) �׷� ���� ��Ī
    g_match = []
    for _, row in groups.iterrows():
        g_slot = (row.start_time, row.end_time)
        if any(overlap(*g_slot, *cslot) for cslot in CURRENT_USER_SLOTS):
            g_match.append(row.to_dict())

    return {
        "partners": list(partner_dict.values()),
        "groups": g_match,
        # �� ����/��� �ð��� �ʿ��ϸ� ���信 ����
        "sleep_time": SLEEP_TIME.isoformat(timespec="minutes"),
        "wake_time":  WAKE_TIME.isoformat(timespec="minutes"),
    }


# ����������������������������������������������������������������������������������
# 5) API ����-����Ʈ
# ����������������������������������������������������������������������������������
@app.post("/predict")
def recommend(req: RecoReq):
    return {"status": "ok", **get_reco()}


# ─────────────────────────────────────────────
# Phase 5 §9.1 contract: 실제 uid의 preferred_slots를 조회 — 분석 문서 §6에서 발견된
# *uid 무시* 결함 fix. POST /predict는 legacy hardcoded slot 그대로 (옵션 default).
# @contract: shared with streamlit (and ai_service if downstream needed). Phase 6+ extract.
# ─────────────────────────────────────────────
from typing import Optional, Tuple
from pydantic import Field


class PartnerEntry(BaseModel):
    user_id:         str
    name:            Optional[str] = None
    workout_level:   Optional[str] = None
    image_url:       Optional[str] = None
    overlap_minutes: int


class GroupEntry(BaseModel):
    group_id:        int
    session_name:    str
    start_time:      str
    end_time:        str
    level:           Optional[str] = None
    description:     Optional[str] = None
    image_url:       Optional[str] = None
    overlap_minutes: int


class RecommendationResponse(BaseModel):
    uid:              str
    user_slots_used:  List[List[str]] = Field(
        ..., description="회원의 실제 preferred_slots ([['18:00','19:00'], ...]). 비어 있으면 fallback."
    )
    fallback_used:    bool = Field(
        ..., description="True면 회원이 preferred_slots에 등록 안 돼 hardcode CURRENT_USER_SLOTS 사용"
    )
    partners:         List[PartnerEntry]
    groups:           List[GroupEntry]


def _overlap_minutes(a_start: time, a_end: time, b_start: time, b_end: time) -> int:
    """겹치는 분. 음수면 0."""
    latest   = max(datetime.combine(datetime.today(), a_start),
                   datetime.combine(datetime.today(), b_start))
    earliest = min(datetime.combine(datetime.today(), a_end),
                   datetime.combine(datetime.today(), b_end))
    delta = (earliest - latest).total_seconds() / 60
    return max(0, int(delta))


@app.get("/recommendations/{uid}", response_model=RecommendationResponse)
def get_recommendations(uid: str):
    """uid의 *실제* preferred_slots를 사용해 다른 회원·그룹과 30분 이상 겹침 매칭.

    preferred_slots에 uid가 없으면 hardcoded CURRENT_USER_SLOTS로 fallback (그 경우
    응답의 fallback_used=True). POST /predict는 legacy 동작 그대로 — 기존 클라이언트 무영향.
    """
    with engine.begin() as conn:
        my_slots = pd.read_sql(
            text("SELECT slot_start, slot_end FROM preferred_slots WHERE user_id = :uid"),
            conn, params={"uid": uid},
        )
        partners_df = pd.read_sql(
            text("""
                SELECT u.user_id, u.name, u.workout_level, u.image_url,
                       ps.slot_start, ps.slot_end
                FROM users u JOIN preferred_slots ps ON ps.user_id = u.user_id
                WHERE u.user_id != :uid
            """),
            conn, params={"uid": uid},
        )
        groups_df = pd.read_sql(text("SELECT * FROM group_sessions"), conn)

    if my_slots.empty:
        user_slots = list(CURRENT_USER_SLOTS)
        fallback_used = True
    else:
        user_slots = [(row.slot_start, row.slot_end) for _, row in my_slots.iterrows()]
        fallback_used = False

    # 파트너 매칭 — user_id별 *최대* overlap만 유지
    # NOTE: pandas row의 `.name`은 row *index*라 컬럼 'name'을 가림 → dict-style 접근 사용
    seen_partners: Dict[str, dict] = {}
    for _, p in partners_df.iterrows():
        for u_start, u_end in user_slots:
            ov = _overlap_minutes(p["slot_start"], p["slot_end"], u_start, u_end)
            if ov >= 30:
                prev = seen_partners.get(p["user_id"])
                if prev is None or ov > prev["overlap_minutes"]:
                    seen_partners[p["user_id"]] = {
                        "user_id":         p["user_id"],
                        "name":            p["name"],
                        "workout_level":   p["workout_level"],
                        "image_url":       p["image_url"],
                        "overlap_minutes": ov,
                    }

    # 그룹 매칭 — group_id별 1회만
    def _row_get(row, col):
        return row[col] if col in row.index else None

    group_results: List[dict] = []
    seen_group_ids = set()
    for _, g in groups_df.iterrows():
        if g["group_id"] in seen_group_ids:
            continue
        for u_start, u_end in user_slots:
            ov = _overlap_minutes(g["start_time"], g["end_time"], u_start, u_end)
            if ov >= 30:
                group_results.append({
                    "group_id":        int(g["group_id"]),
                    "session_name":    g["session_name"],
                    "start_time":      str(g["start_time"]),
                    "end_time":        str(g["end_time"]),
                    "level":           _row_get(g, "level"),
                    "description":     _row_get(g, "description"),
                    "image_url":       _row_get(g, "image_url"),
                    "overlap_minutes": ov,
                })
                seen_group_ids.add(g["group_id"])
                break

    return RecommendationResponse(
        uid=uid,
        user_slots_used=[[str(s), str(e)] for s, e in user_slots],
        fallback_used=fallback_used,
        partners=[PartnerEntry(**p) for p in seen_partners.values()],
        groups=[GroupEntry(**g) for g in group_results],
    )
