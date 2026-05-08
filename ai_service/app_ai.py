# -*- coding: utf-8 -*-
# ai_service/app_ai.py
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import uuid, os, logging, json
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
# §9.6 model_runs 상태 머신 — 신규 테이블 없는 환경에서도 깨지지 않게 try/except로 감쌈
def _update_run_status(run_id, status: str, current_step: str = None, error: str = None) -> None:
    parts = ["status = %s"]
    args  = [status]
    if current_step is not None:
        parts.append("current_step = %s"); args.append(current_step)
    if error is not None:
        parts.append("error = %s"); args.append(error)
    if status in ("succeeded", "failed"):
        parts.append("finished_at = NOW()")
    args.append(str(run_id))
    sql = f"UPDATE model_runs SET {', '.join(parts)} WHERE run_id = %s"
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            conn.commit()
    except Exception as e:
        logger.warning(f"[§9.6] model_runs UPDATE 실패 (테이블 미적용?): {e}")


@app.post("/predict")
def predict(
    req: Req,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    # §9.6 멱등성 키 hit 체크 — 같은 키로 재호출되면 기존 응답 그대로 반환 (vLLM·CatBoost 재실행 0)
    if idempotency_key:
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT response_body FROM idempotency_log WHERE key = %s",
                    (idempotency_key,),
                )
                row = cur.fetchone()
                if row:
                    logger.info(f"[§9.6] idempotency hit: key={idempotency_key}")
                    return row[0]   # JSONB → dict (psycopg2가 자동 변환)
        except Exception as e:
            logger.warning(f"[§9.6] idempotency_log 조회 실패 → 정상 처리 진행: {e}")

    run_id = uuid.uuid4()

    # §9.6 model_runs INSERT (status='queued')
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO model_runs (run_id, uid, status, current_step) "
                "VALUES (%s, %s, %s, %s)",
                (str(run_id), req.uid, "queued", "init"),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"[§9.6] model_runs INSERT 실패 (테이블 미적용?): {e}")

    try:
        _update_run_status(run_id, "running", "coach_main")
        # §2.1: coach_main now returns a dict with message + eval metrics + §8.5 메타
        result = coach_main(uid=req.uid,
                            model_path=MODEL_PATH,
                            window=WINDOW)
    except Exception as e:
        logger.exception("predict 실패")
        _update_run_status(run_id, "failed", error=str(e))
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

    _update_run_status(run_id, "running", "predictions_insert")
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

    _update_run_status(run_id, "succeeded", "done")

    response = {"status":           "ok",
                "run_id":            str(run_id),
                "rmse_test":         rmse_test,
                "baseline_rmse":     baseline_rmse,
                "model_version":     model_version,
                "prompt_hash":       prompt_hash,
                "recommended_slots": recommended_slot_json,
                "message_preview":   message[:120] + "..."}

    # §9.6 idempotency 적재 (키 있을 때만)
    if idempotency_key:
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO idempotency_log (key, run_id, response_body) "
                    "VALUES (%s, %s, %s::jsonb) ON CONFLICT (key) DO NOTHING",
                    (idempotency_key, str(run_id), json.dumps(response)),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"[§9.6] idempotency_log INSERT 실패: {e}")

    return response

