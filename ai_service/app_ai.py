# -*- coding: utf-8 -*-
# ai_service/app_ai.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid, os, logging
from pathlib import Path

from db_utils import get_conn
from sleep_coach_full_kr_v6 import main as coach_main

# ─────────────────────────────────────────────
# FastAPI 인스턴스 (on_startup 훅 필요 X)
# ─────────────────────────────────────────────
app = FastAPI()

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
DB_TABLE   = "predictions"
MODEL_PATH = Path(os.getenv("MODEL_PATH",
                "/app/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"))
WINDOW     = int(os.getenv("WINDOW", 7))

logger = logging.getLogger("app_ai")

# ─────────────────────────────────────────────
# 요청 스키마
# ─────────────────────────────────────────────
class Req(BaseModel):
    uid: str

# ─────────────────────────────────────────────
# /predict 엔드포인트
# ─────────────────────────────────────────────
@app.post("/predict")
def predict(req: Req):
    run_id = uuid.uuid4()

    try:
        message = coach_main(uid=req.uid,        # ← 메시지 수신
                             model_path=MODEL_PATH,
                             window=WINDOW)
    except Exception as e:
        logger.exception("predict 실패")
        raise HTTPException(status_code=500, detail=f"coach_main error: {e}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {DB_TABLE}(uid, run_id, note, message)
                VALUES (%s, %s, %s, %s)""",
            (req.uid, str(run_id), "run completed", message)
        )
        conn.commit()

    return {"status": "ok",
            "run_id": str(run_id),
            "message_preview": message[:120] + "..."}

