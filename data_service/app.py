# data_service/app.py
import os
import subprocess
import uuid
import requests
import datetime as _dt
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

app = FastAPI(title="BioFit Data Service")

class FetchRequest(BaseModel):
    uid: str
    start_date: str
    end_date: str
    token: str

# Phase 4 §9.1 contract: 외부 서비스(ai_service 등)에 노출하는 일별 feature 한 행 표준 모델.
# @contract: shared with ai_service. 인라인 복제 — Phase 5+에서 biofit-contracts 패키지로 추출 예정.
class FeatureRow(BaseModel):
    user_id:        str
    date:           _dt.date
    efficiency:     Optional[float] = None
    stage_deep:     Optional[int]   = None
    stage_light:    Optional[int]   = None
    stage_rem:      Optional[int]   = None
    stage_wake:     Optional[int]   = None
    time_in_bed:    Optional[int]   = None
    wake_count:     Optional[int]   = None
    steps:          Optional[int]   = None
    distance:       Optional[float] = None
    calories:       Optional[float] = None
    resting_hr:     Optional[float] = None
    azm_total:      Optional[int]   = None
    azm_fatburn:    Optional[int]   = None
    azm_cardio:     Optional[int]   = None
    hrv_rmssd:      Optional[float] = None
    hrv_hf:         Optional[float] = None
    hrv_lf:         Optional[float] = None

# 환경변수에서 DB URL과 (필요 시) FITBIT_TOKEN을 읽어옴
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

# Phase 4: data_service 자체가 fitbit_daily_features를 SELECT하기 위한 engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


FITBIT_CSV_DIR = Path("./fitbit_csv")
# AI Service 호출은 Data Service 역할이 아니므로 여기에서는 생략

@app.post("/fetch")
def fetch_and_preprocess(req: FetchRequest):
    uid = req.uid
    s = req.start_date
    e = req.end_date
    token = req.token # streamlit에서 입력받은 토큰
    os.environ["FITBIT_TOKEN"] = token

    if not token:
        raise HTTPException(status_code=400, detail="FITBIT_TOKEN 환경변수가 없습니다.")

    # Phase G.1 — 옵트인 ingestion_runs 박제 (LOG_INGESTION_RUNS=1일 때만)
    run_id = _start_ingestion_run(uid, s, e)

    # # 2) 00-CallAPI.py 실행: Fitbit API → /app/fitbit_csv/*.csv 생성
    # try:
    #     subprocess.run(
    #         ["python3", "00-CallAPI.py", uid, s, e],
    #         check=True,
    #         capture_output=True,
    #         text=True
    #     )
    # # except subprocess.CalledProcessError as e:
    # #     print("Error 1 500 call 실패")
    # #     raise HTTPException(status_code=500, detail=f"00-CallAPI 실패: {e.stderr}")
    # except subprocess.CalledProcessError as err:
    #     logging.error("[FastAPI] ❌ 00-CallAPI 실패 (exit %s)", err.returncode)
    #     logging.error("[FastAPI] ── stdout ──\n%s", err.stdout)
    #     logging.error("[FastAPI] ── stderr ──\n%s", err.stderr)
    #     raise HTTPException(500, detail="00-CallAPI 실행 실패")



    # 3) raw CSV → DB 저장 (csv_to_db.py)
    try:
        subprocess.run(
            ["python3", "csv_to_db.py"],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        logging.error("[FastAPI] ❌ csv_to_db 실패 (exit %s)", e.returncode)
        logging.error("[FastAPI] ── stdout ──\n%s", e.stdout)
        logging.error("[FastAPI] ── stderr ──\n%s", e.stderr)
        _finish_ingestion_run(run_id, "failed", error=f"csv_to_db: {e.stderr[:300] if e.stderr else 'CalledProcessError'}")
        raise HTTPException(status_code=500, detail=f"Raw CSV→DB 실패: {e.stderr}")

    try:
    # raw CSV 삭제
        for raw_file in FITBIT_CSV_DIR.glob("*.csv"):
            raw_file.unlink()
        # processed CSV 삭제 (작업 디렉터리에 생성된 모든 uid_* CSV)
        for proc_file in Path("/app").glob(f"{uid}_*.csv"):
            proc_file.unlink()

    except Exception as e:
        # Cleanup 에러는 전체 플로우 실패로 연결하지 않고 경고로 남김
        print(f"⚠️ Cleanup 중 오류 발생: {e}")

    _finish_ingestion_run(run_id, "succeeded")
    return {
        "status":  "ok",
        "run_id":  run_id,
        "message": f"{uid} 데이터 수집·전처리 완료 ({s} ~ {e})"
    }


# ─────────────────────────────────────────────
# Phase 4 §9.1 contract: 표준 feature endpoint
# ai_service가 DB 직접 access 대신 이 endpoint로 features를 가져옴 (USE_DATA_SERVICE_API=1).
# 결합 지점이 *암묵적 DB 스키마* → *명시적 HTTP 계약 + Pydantic 모델*로 이동.
# ─────────────────────────────────────────────
@app.get("/users/{uid}/features", response_model=List[FeatureRow])
def get_user_features(
    uid: str,
    window: int = Query(7, ge=1, le=1000, description="최근 N일 (default 7, max 1000 — ~3년)"),
):
    """fitbit_daily_features에서 회원의 최근 window일 features를 시간 오름차순으로 반환.

    Phase 3 §9.1 expand로 도입된 정규화 테이블이 비어 있으면(DUAL_WRITE_NORMALIZED 미옵트인)
    빈 리스트 반환 — 404 아님 (정상적으로 *데이터가 없는* 신규 회원과 구분 안 됨).
    호출자(ai_service)는 빈 응답 시 legacy path로 fallback.
    """
    # *회원의 마지막 데이터*에서 거꾸로 N일 — CURRENT_DATE 기준이 아니라 데이터 기반.
    # (운영 데이터는 매일 적재되어 CURRENT_DATE와 같지만, 본 프로젝트의 23RK3S 같은
    #  *과거 dump*는 CURRENT_DATE보다 한참 전이라 CURRENT_DATE 기준이면 빈 응답이 됨.)
    sql = text(
        """
        SELECT * FROM (
            SELECT user_id, date,
                   efficiency, stage_deep, stage_light, stage_rem, stage_wake,
                   time_in_bed, wake_count,
                   steps, distance, calories,
                   resting_hr, azm_total, azm_fatburn, azm_cardio,
                   hrv_rmssd, hrv_hf, hrv_lf
            FROM fitbit_daily_features
            WHERE user_id = :uid
            ORDER BY date DESC
            LIMIT :w
        ) sub
        ORDER BY date ASC
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, {"uid": uid, "w": window}).mappings().all()
    except Exception as e:
        # fitbit_daily_features 테이블 자체 부재(Phase 3 마이그레이션 미적용) 시
        logging.warning(f"[Phase 4] features query 실패: {e}")
        return []

    return [FeatureRow(**dict(r)) for r in rows]


# ─────────────────────────────────────────────
# Phase G.1 — ingestion_runs 진행 상태 추적
# 데이터 수집 작업의 *어디까지 진행됐는지*를 박제 + 외부 조회 endpoint 노출.
# 옵트인 default 0 (LOG_INGESTION_RUNS=1일 때만 박제). 미적용 환경에서도 안전하게
# try/except로 감쌈.
# ─────────────────────────────────────────────
def _start_ingestion_run(uid: str, date_start: str, date_end: str) -> Optional[str]:
    """LOG_INGESTION_RUNS=1일 때 ingestion_runs row INSERT. 새 run_id 반환."""
    if os.getenv("LOG_INGESTION_RUNS", "0") != "1":
        return None
    run_id = str(uuid.uuid4())
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO ingestion_runs
                        (run_id, user_id, status, current_step, date_start, date_end)
                    VALUES
                        (CAST(:rid AS UUID), :uid, 'running', 'init',
                         CAST(:ds AS DATE), CAST(:de AS DATE))
                """),
                {"rid": run_id, "uid": uid, "ds": date_start, "de": date_end},
            )
        return run_id
    except Exception as e:
        logging.warning(f"[Phase G] ingestion_runs INSERT 실패 (테이블 미적용?): {e}")
        return None


def _finish_ingestion_run(
    run_id: Optional[str],
    status: str,
    row_count: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """ingestion_runs row를 succeeded/failed로 마무리. run_id가 None이면 noop."""
    if not run_id:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE ingestion_runs
                    SET status        = :st,
                        finished_at   = NOW(),
                        current_step  = 'done',
                        row_count     = COALESCE(:rc, row_count),
                        error_message = :err
                    WHERE run_id = CAST(:rid AS UUID)
                """),
                {"st": status, "rc": row_count, "err": error, "rid": run_id},
            )
    except Exception as e:
        logging.warning(f"[Phase G] ingestion_runs UPDATE 실패: {e}")


class IngestionRunStatus(BaseModel):
    run_id:        str
    user_id:       str
    status:        str
    current_step:  Optional[str]          = None
    started_at:    Optional[_dt.datetime] = None
    finished_at:   Optional[_dt.datetime] = None
    date_start:    Optional[_dt.date]     = None
    date_end:      Optional[_dt.date]     = None
    row_count:     Optional[int]          = None
    error_message: Optional[str]          = None


def _row_to_status(row) -> IngestionRunStatus:
    return IngestionRunStatus(
        run_id=str(row["run_id"]),
        user_id=row["user_id"],
        status=row["status"],
        current_step=row["current_step"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        date_start=row["date_start"],
        date_end=row["date_end"],
        row_count=row["row_count"],
        error_message=row["error_message"],
    )


@app.get("/ingestion-runs/{run_id}", response_model=IngestionRunStatus)
def get_ingestion_run(run_id: str):
    """단일 작업 진행 상태 조회. 클라이언트가 *어디까지 진행됐는지* 물을 때 사용."""
    sql = text("""
        SELECT run_id, user_id, status, current_step,
               started_at, finished_at, date_start, date_end,
               row_count, error_message
        FROM ingestion_runs
        WHERE run_id = CAST(:rid AS UUID)
    """)
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"rid": run_id}).mappings().first()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ingestion_runs 조회 실패: {e}")
    if not row:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} not found")
    return _row_to_status(row)


@app.get("/ingestion-runs", response_model=List[IngestionRunStatus])
def list_ingestion_runs(
    uid:    str           = Query(..., min_length=1, description="회원 ID"),
    status: Optional[str] = Query(None, description="queued/running/succeeded/failed 필터"),
):
    """uid 기반 작업 목록 조회. *진행 중 작업*을 찾아 폴링할 때 사용."""
    where = ["user_id = :uid"]
    params = {"uid": uid}
    if status:
        where.append("status = :status")
        params["status"] = status
    sql = text(f"""
        SELECT run_id, user_id, status, current_step,
               started_at, finished_at, date_start, date_end,
               row_count, error_message
        FROM ingestion_runs
        WHERE {" AND ".join(where)}
        ORDER BY started_at DESC
        LIMIT 50
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except Exception:
        return []  # 테이블 미적용 또는 쿼리 실패 — 빈 리스트
    return [_row_to_status(r) for r in rows]
