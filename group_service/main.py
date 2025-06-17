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

# ─────────────────────────────────────────
# 1) 요청 스키마
# ─────────────────────────────────────────
class RecoReq(BaseModel):
    uid: str          # Streamlit 에서 넘겨준 현재 사용자 ID
    # 이번 테스트에서는 uid = 23RK3S 로 들어올 것


# ─────────────────────────────────────────
# 2) 현재 유저 기본 설정
# ─────────────────────────────────────────
CURRENT_USER_SLOTS = [
    (time(10, 0), time(11, 0)),
    (time(18, 0), time(19, 0)),
]
SLEEP_TIME = time(22, 0)
WAKE_TIME  = time(8, 0)


# ─────────────────────────────────────────
# 3) 겹침 여부 헬퍼
# ─────────────────────────────────────────
def overlap(a_start: time, a_end: time,
            b_start: time, b_end: time,
            min_minutes: int = 30) -> bool:
    latest  = max(datetime.combine(datetime.today(), a_start),
                  datetime.combine(datetime.today(), b_start))
    earliest = min(datetime.combine(datetime.today(), a_end),
                   datetime.combine(datetime.today(), b_end))
    return (earliest - latest).total_seconds() / 60 >= min_minutes


# ─────────────────────────────────────────
# 4) 추천 로직
# ─────────────────────────────────────────
def get_reco() -> Dict[str, List[dict]]:
    with engine.begin() as conn:
        partners = pd.read_sql("""
            SELECT u.user_id, u.name, u.workout_level, u.image_url,
                   ps.slot_start, ps.slot_end
            FROM users u
            JOIN preferred_slots ps ON ps.user_id = u.user_id
        """, conn)
        groups = pd.read_sql("SELECT * FROM group_sessions", conn)

    # 4-1) 파트너 매칭
    partner_dict = {}          # user_id → {info + slot list}
    for _, row in partners.iterrows():
        p_slot = (row.slot_start, row.slot_end)
        # 현재 유저 슬롯 중 하나라도 겹치면 매칭
        if any(overlap(*p_slot, *cslot) for cslot in CURRENT_USER_SLOTS):
            info = partner_dict.setdefault(
                row.user_id,
                dict(name=row.name,
                     workout_level=row.workout_level,
                     image_url=row.image_url,
                     slots=[],
                    # ▼ 첫 번째 슬롯을 preferred_* 로도 저장
                    preferred_start=str(row.slot_start),
                    preferred_end=str(row.slot_end))
                    )
            info["slots"].append(p_slot)

    # 4-2) 그룹 세션 매칭
    g_match = []
    for _, row in groups.iterrows():
        g_slot = (row.start_time, row.end_time)
        if any(overlap(*g_slot, *cslot) for cslot in CURRENT_USER_SLOTS):
            g_match.append(row.to_dict())

    return {
        "partners": list(partner_dict.values()),
        "groups": g_match,
        # ↓ 수면/기상 시간도 필요하면 응답에 포함
        "sleep_time": SLEEP_TIME.isoformat(timespec="minutes"),
        "wake_time":  WAKE_TIME.isoformat(timespec="minutes"),
    }


# ─────────────────────────────────────────
# 5) API 엔드-포인트
# ─────────────────────────────────────────
@app.post("/predict")
def recommend(req: RecoReq):
    return {"status": "ok", **get_reco()}
