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
        # §2.1: coach_main now returns a dict with message + eval metrics.
        result = coach_main(uid=req.uid,
                            model_path=MODEL_PATH,
                            window=WINDOW)
    except Exception as e:
        logger.exception("predict 실패")
        raise HTTPException(status_code=500, detail=f"coach_main error: {e}")

    message               = result["message"]
    rmse_test             = result.get("rmse_test")
    mae_test              = result.get("mae_test")
    baseline_rmse         = result.get("baseline_rmse")
    data_window_end       = result.get("data_window_end")
    feature_set_version   = result.get("feature_set_version")
    # §8.5 메타
    model_version         = result.get("model_version")
    prompt_hash           = result.get("prompt_hash")
    llm_params            = result.get("llm_params")
    recommended_slot_json = result.get("recommended_slot_json")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {DB_TABLE}(
                  uid, run_id, note, message,
                  rmse_test, mae_test, data_window_end, feature_set_version,
                  model_version, prompt_hash, llm_params, recommended_slot_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (req.uid, str(run_id), "run completed", message,
             rmse_test, mae_test, data_window_end, feature_set_version,
             model_version, prompt_hash, llm_params, recommended_slot_json)
        )
        conn.commit()

    return {"status":              "ok",
            "run_id":               str(run_id),
            "rmse_test":            rmse_test,
            "baseline_rmse":        baseline_rmse,
            "model_version":        model_version,
            "prompt_hash":          prompt_hash,
            "recommended_slots":    recommended_slot_json,
            "message_preview":      message[:120] + "..."}

