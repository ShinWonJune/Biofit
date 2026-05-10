# feedback_api/main.py

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, MetaData, Table, Column, String, Date, Integer, CheckConstraint, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from typing import Optional, List
import datetime as _dt
import os

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

engine = create_engine(DATABASE_URL)
app = FastAPI()

class Feedback(BaseModel):
    user_id: str
    date: str
    # Phase A.1 — PSQI C1과 *동일 0~3 규모*로 통일.
    # 0=최고, 1=잘잤어, 2=못잤어, 3=최악. 기존 0/1/2 데이터는 학습에서 제외(옵션 A).
    sleep_score: int = Field(..., ge=0, le=3, description="0=최고, 1=잘잤어, 2=못잤어, 3=최악")

@app.post("/feedback")
def receive_feedback(fb: Feedback):
    metadata = MetaData()
    table_name = f"{fb.user_id}_feedback"

    feedback_table = Table(
        table_name,
        metadata,
        Column("user_id", String, nullable=False),
        Column("date", Date, nullable=False),
        Column("sleep_score", Integer, nullable=False),
        # Phase A.1 — DB 측에도 0~3 강제. Pydantic 검증을 우회한 직접 INSERT도 차단.
        CheckConstraint(
            "sleep_score >= 0 AND sleep_score <= 3",
            name=f"{table_name}_sleep_score_0_3"
        ),
        extend_existing=True  # 테이블이 이미 있다면 무시하고 덮어씀
    )

    # 테이블이 없으면 자동 생성
    metadata.create_all(engine, tables=[feedback_table])

    # 데이터 삽입
    insert_query = feedback_table.insert().values(
        user_id=fb.user_id,
        date=fb.date,
        sleep_score=fb.sleep_score
    )

    with engine.begin() as conn:
        conn.execute(insert_query)

    return {"status": "ok", "message": f"✅ {table_name} 테이블에 피드백 저장 완료"}


# ─────────────────────────────────────────────
# §8.3 코칭 메시지 평가 루프 — 트레이너 thumbs up/down + 회원 별점
# ─────────────────────────────────────────────
class PredictionFeedback(BaseModel):
    rating:   Optional[int]  = Field(None, ge=1, le=5, description="회원 별점 1~5")
    useful:   Optional[bool] = Field(None, description="트레이너 thumbs up/down")
    comment:  Optional[str]  = Field(None, max_length=2000)
    rated_by: str            = Field(..., min_length=1, max_length=128)


@app.post("/predictions/{run_id}/feedback")
def submit_prediction_feedback(run_id: str, fb: PredictionFeedback):
    """§8.3: predictions.run_id에 대한 트레이너/회원 평가를 predictions_feedback에 적재.

    페이로드 패턴:
      - 트레이너: {"useful": true|false, "rated_by": "trainer-xyz", "comment": "..."}
      - 회원:    {"rating": 1..5,        "rated_by": "23RK3S",       "comment": "..."}
    rating·useful 중 *최소 하나*는 NOT NULL이어야 함.
    """
    if fb.rating is None and fb.useful is None:
        raise HTTPException(
            status_code=422,
            detail="rating 또는 useful 중 최소 하나는 입력해야 합니다"
        )

    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                    INSERT INTO predictions_feedback (run_id, rating, useful, comment, rated_by)
                    VALUES (CAST(:run_id AS UUID), :rating, :useful, :comment, :rated_by)
                    RETURNING id
                """),
                {
                    "run_id":   run_id,
                    "rating":   fb.rating,
                    "useful":   fb.useful,
                    "comment":  fb.comment,
                    "rated_by": fb.rated_by,
                },
            ).fetchone()
    except IntegrityError as e:
        msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if "uq_predictions_feedback_run_rater" in msg:
            raise HTTPException(
                status_code=409,
                detail=f"이미 평가됨: rated_by='{fb.rated_by}' for run_id={run_id}"
            )
        # 외래키 위반 (predictions에 해당 run_id가 없음)
        if "predictions_feedback_run_id_fkey" in msg:
            raise HTTPException(
                status_code=404,
                detail=f"run_id={run_id} not found in predictions"
            )
        raise HTTPException(status_code=400, detail=f"DB 무결성 오류: {msg}")

    return {
        "status":      "ok",
        "feedback_id": row[0],
        "run_id":      run_id,
        "rated_by":    fb.rated_by,
    }


# ─────────────────────────────────────────────
# Phase 4 §9.1 contract: 회원 체감 수면 점수 조회 endpoint
# ai_service가 DB 직접 access (read_table('{uid}_feedback')) 대신 이 endpoint로 fetch.
# @contract: shared with ai_service. Phase 5+ biofit-contracts 패키지로 추출 예정.
# ─────────────────────────────────────────────
class FeedbackRow(BaseModel):
    user_id:     str
    date:        _dt.date
    sleep_score: int
    created_at:  Optional[_dt.datetime] = None


@app.get("/users/{uid}/feedback", response_model=List[FeedbackRow])
def get_user_feedback(
    uid: str,
    from_date: Optional[_dt.date] = Query(None, description="시작 날짜 (포함, ISO YYYY-MM-DD)"),
    to_date:   Optional[_dt.date] = Query(None, description="종료 날짜 (포함)"),
):
    """동적 `{uid}_feedback` 테이블에서 회원 체감 점수를 조회. 기간 미지정 시 전체.

    테이블 부재(회원이 한 번도 입력 안 함) 시 200 + 빈 리스트. 호출자(ai_service)가
    legacy fallback과 동일하게 빈 DataFrame으로 처리.
    """
    table_name = f"{uid}_feedback"
    where_parts = ["user_id = :uid"]
    params = {"uid": uid}
    if from_date is not None:
        where_parts.append("date >= :from_date")
        params["from_date"] = from_date
    if to_date is not None:
        where_parts.append("date <= :to_date")
        params["to_date"] = to_date
    where_sql = " AND ".join(where_parts)

    sql = text(f'SELECT user_id, date, sleep_score FROM "{table_name}" WHERE {where_sql} ORDER BY date ASC')
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except ProgrammingError:
        # 테이블 부재 — 회원이 한 번도 feedback 입력 안 함. 빈 리스트로 정상 응답.
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"feedback query 실패: {e}")

    return [FeedbackRow(**dict(r)) for r in rows]


# ─────────────────────────────────────────────
# Phase A.4 — 침대 누운 시각 직접 수집 (PSQI C2 잠복기 정확도 보강)
# 회원이 streamlit-feedback 화면에서 *"방금 누웠어요"* 버튼을 누르면 그 timestamp를
# bedtime_log 테이블에 박제. PSQI C2 산출 시 fitbit 첫 wake 누적 근사 대신 사용.
# ─────────────────────────────────────────────
class BedtimeLog(BaseModel):
    user_id:    str = Field(..., min_length=1, description="회원 ID")
    bedtime_at: Optional[_dt.datetime] = Field(
        None,
        description="None이면 서버의 현재 시각(UTC)으로 박제. 클라이언트 측 timestamp를 줄 수도 있음.",
    )


@app.post("/bedtime-log")
def receive_bedtime(log: BedtimeLog):
    """회원의 침대 누운 시각을 bedtime_log 테이블에 박제.

    bedtime_at을 생략하면 *서버 수신 시각*으로 박제. PSQI C2 잠복기 산출 시
    *bedtime_at 우선 + sleep_detail wake 누적 fallback*으로 사용된다.
    """
    bedtime = log.bedtime_at or _dt.datetime.now(_dt.timezone.utc)
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                    INSERT INTO bedtime_log (user_id, bedtime_at)
                    VALUES (:uid, :bt)
                    RETURNING id
                """),
                {"uid": log.user_id, "bt": bedtime},
            ).fetchone()
    except ProgrammingError as e:
        # bedtime_log 테이블이 없으면 — Alembic 005 미적용 환경
        raise HTTPException(
            status_code=503,
            detail="bedtime_log 테이블이 미적용. Alembic 005 마이그레이션을 실행하세요.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bedtime_log INSERT 실패: {e}")

    return {
        "status":     "ok",
        "id":         row[0],
        "user_id":    log.user_id,
        "bedtime_at": bedtime.isoformat(),
    }


@app.get("/users/{uid}/bedtime-log", response_model=List[dict])
def get_user_bedtime_log(
    uid: str,
    from_date: Optional[_dt.date] = Query(None, description="bedtime_at >= 시작 날짜"),
    to_date:   Optional[_dt.date] = Query(None, description="bedtime_at <= 종료 날짜"),
):
    """회원의 침대 누운 시각 이력 조회. PSQI C2 산출 시 ai_service 또는 experiments에서 호출."""
    where = ["user_id = :uid"]
    params = {"uid": uid}
    if from_date is not None:
        where.append("bedtime_at >= :from_date")
        params["from_date"] = from_date
    if to_date is not None:
        where.append("bedtime_at <= :to_date")
        params["to_date"] = to_date

    sql = text(f"""
        SELECT id, user_id, bedtime_at
        FROM bedtime_log
        WHERE {" AND ".join(where)}
        ORDER BY bedtime_at ASC
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except ProgrammingError:
        return []  # 테이블 미적용 — 빈 리스트로 정상 응답
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bedtime_log query 실패: {e}")

    return [
        {
            "id":         r["id"],
            "user_id":    r["user_id"],
            "bedtime_at": r["bedtime_at"].isoformat() if r["bedtime_at"] else None,
        }
        for r in rows
    ]
