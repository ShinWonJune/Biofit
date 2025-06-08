# data_service/app.py
import os
import subprocess
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
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

# 환경변수에서 DB URL과 (필요 시) FITBIT_TOKEN을 읽어옴
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")


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
