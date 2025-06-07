# data_service/app.py
import os
import subprocess
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
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

# 환경변수에서 DB URL과 (필요 시) FITBIT_TOKEN을 읽어옴
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")



# AI Service 호출은 Data Service 역할이 아니므로 여기에서는 생략

@app.post("/fetch")
def fetch_and_preprocess(req: FetchRequest):
    uid = req.uid
    s = req.start_date
    e = req.end_date
    token = req.token # streamlit에서 입력받은 토큰
    logging.info(f"[FastAPI] 수신된 데이터 요청: uid={uid}, start={s}, end={e}")
    logging.info(f"[FastAPI] 토큰 앞 10자: {token[:100]}")
    logging.info(f"[FastAPI] 토큰 끝 10자: {token[-10:]}")
    logging.info(f"[FastAPI] 환경변수에 FITBIT_TOKEN 설정 완료")
    os.environ["FITBIT_TOKEN"] = token

    if not token:
        raise HTTPException(status_code=400, detail="FITBIT_TOKEN 환경변수가 없습니다.")

    # 2) 00-CallAPI.py 실행: Fitbit API → /app/fitbit_csv/*.csv 생성
    try:
        subprocess.run(
            ["python3", "00-CallAPI.py", uid, s, e],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"00-CallAPI 실패: {e.stderr}")

    # 3) raw CSV → DB 저장 (csv_to_db.py)
    try:
        subprocess.run(
            ["python3", "csv_to_db.py"],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Raw CSV→DB 실패: {e.stderr}")

    # 4) 전처리 단계 (01~03 스크립트 순차 실행)
    for script in ["01-preprocess-averaged.py", "02-preprocess-merged.py", "03-preprocess-check.py"]:
        try:
            subprocess.run(
                ["python3", script],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=500,
                detail=f"{script} 실행 실패: {e.stderr}"
            )

    # 5) processed CSV → DB 저장 (processed 전용 스크립트)
    try:
        subprocess.run(
            ["python3", "csv_to_db_processed.py"],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Processed CSV→DB 저장 실패: {e.stderr}"
        )

    return {
        "status": "ok",
        "message": f"{uid} 데이터 수집·전처리 완료 ({s} ~ {e})"
    }
