# data_service/app.py
import os
import subprocess
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
    # logging.info(f"[FastAPI] 수신된 데이터 요청: uid={uid}, start={s}, end={e}")
    # logging.info(f"[FastAPI] 토큰 앞 10자: {token[:100]}")
    # logging.info(f"[FastAPI] 토큰 끝 10자: {token[-10:]}")
    # logging.info(f"[FastAPI] 환경변수에 FITBIT_TOKEN 설정 완료")
    os.environ["FITBIT_TOKEN"] = token

    if not token:
        raise HTTPException(status_code=400, detail="FITBIT_TOKEN 환경변수가 없습니다.")

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

    return {
        "status": "ok",
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
