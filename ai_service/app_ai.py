# -*- coding: utf-8 -*-
# ai_service/app_ai.py
from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, Field
from typing import Optional, Any, List
from datetime import datetime, date
import uuid, os, logging, json, threading
import requests
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
    # Phase D — PSQI 4 모델 결과 (옵트인 default 0이라 모두 None일 수 있음)
    psqi_scores           = result.get("psqi_scores")
    psqi_predicted_total  = result.get("psqi_predicted_total")
    recommended_slot_psqi = result.get("recommended_slot_psqi")
    recommendation_mode   = result.get("recommendation_mode")

    _update_run_status(run_id, "running", "predictions_insert")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {DB_TABLE}(
                  uid, run_id, note, message,
                  rmse_test, mae_test, data_window_end, feature_set_version,
                  model_version, prompt_hash, llm_params, recommended_slot_json,
                  psqi_scores, psqi_predicted_total, recommended_slot_psqi, recommendation_mode
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (req.uid, str(run_id), "run completed", message,
             rmse_test, mae_test, data_window_end, feature_set_version,
             model_version, prompt_hash, llm_params, recommended_slot_json,
             psqi_scores, psqi_predicted_total, recommended_slot_psqi, recommendation_mode)
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


# ─────────────────────────────────────────────
# Phase 5 §9.1 contract: ai_service exposes — 외부 클라이언트(streamlit·group_service)가
# *DB 직접 SELECT 대신* 이 endpoint로 prediction 결과를 조회.
# 결합 지점이 *predictions 테이블 스키마* → *명시적 HTTP 계약 + Pydantic*으로 이동.
# @contract: shared with streamlit, group_service. Phase 6+ extract to biofit-contracts.
# ─────────────────────────────────────────────
class PredictionResponse(BaseModel):
    uid:                   str
    run_id:                str
    note:                  Optional[str]      = None
    message:               str
    created_at:            Optional[datetime] = None
    rmse_test:             Optional[float]    = None
    mae_test:              Optional[float]    = None
    data_window_end:       Optional[date]     = None
    feature_set_version:   Optional[str]      = None
    model_version:         Optional[str]      = None
    prompt_hash:           Optional[str]      = None
    llm_params:            Optional[Any]      = None   # JSONB
    recommended_slot_json: Optional[Any]      = None   # JSONB list
    # Phase F.5 — PSQI 정형 데이터 (옵트인 default 0이라 NULL 가능)
    psqi_scores:           Optional[Any]      = None   # JSONB {c1, c2, c3, c4, total}
    psqi_predicted_total:  Optional[float]    = None
    recommended_slot_psqi: Optional[Any]      = None   # JSONB {slot, predicted_c1..c4, total}
    recommendation_mode:   Optional[str]      = None   # 'exploration' / 'exploitation'


@app.get("/predictions/{run_id}", response_model=PredictionResponse)
def get_prediction(run_id: str):
    """Phase 5 §9.1 contract: predictions 단일 row 조회 endpoint.

    psycopg2가 JSONB 컬럼을 dict/list로 자동 변환하므로 그대로 통과.
    404: predictions에 해당 run_id 없음.
    Phase F.5 추가 — PSQI 정형 데이터 4 필드 포함.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT uid, run_id, note, message, created_at,
                       rmse_test, mae_test, data_window_end, feature_set_version,
                       model_version, prompt_hash, llm_params, recommended_slot_json,
                       psqi_scores, psqi_predicted_total, recommended_slot_psqi, recommendation_mode
                FROM {DB_TABLE} WHERE run_id = %s""",
            (run_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} not found in predictions")

    cols = ["uid", "run_id", "note", "message", "created_at",
            "rmse_test", "mae_test", "data_window_end", "feature_set_version",
            "model_version", "prompt_hash", "llm_params", "recommended_slot_json",
            "psqi_scores", "psqi_predicted_total", "recommended_slot_psqi", "recommendation_mode"]
    d = dict(zip(cols, row))
    # JSONB 필드가 string으로 와도 dict/list로 보정 (드라이버 차이 흡수)
    for k in ("llm_params", "recommended_slot_json", "psqi_scores", "recommended_slot_psqi"):
        if isinstance(d.get(k), str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass

    return PredictionResponse(
        uid=str(d["uid"]),
        run_id=str(d["run_id"]),
        note=d.get("note"),
        message=d.get("message") or "",
        created_at=d.get("created_at"),
        rmse_test=d.get("rmse_test"),
        mae_test=d.get("mae_test"),
        data_window_end=d.get("data_window_end"),
        feature_set_version=d.get("feature_set_version"),
        model_version=d.get("model_version"),
        prompt_hash=d.get("prompt_hash"),
        llm_params=d.get("llm_params"),
        recommended_slot_json=d.get("recommended_slot_json"),
        psqi_scores=d.get("psqi_scores"),
        psqi_predicted_total=d.get("psqi_predicted_total"),
        recommended_slot_psqi=d.get("recommended_slot_psqi"),
        recommendation_mode=d.get("recommendation_mode"),
    )


# ─────────────────────────────────────────────
# Phase G.2 — model_runs 외부 조회 endpoint
# 클라이언트(streamlit)가 *추론 작업의 진행 단계*를 조회. 분산 추적의 토대.
# ─────────────────────────────────────────────
class ModelRunStatus(BaseModel):
    run_id:        str
    uid:           str
    status:        str
    current_step:  Optional[str]      = None
    started_at:    Optional[datetime] = None
    finished_at:   Optional[datetime] = None
    error:         Optional[str]      = None
    retry_count:   Optional[int]      = None


def _row_to_model_run(row) -> ModelRunStatus:
    cols = ["run_id", "uid", "status", "current_step",
            "started_at", "finished_at", "error", "retry_count"]
    d = dict(zip(cols, row))
    return ModelRunStatus(
        run_id=str(d["run_id"]),
        uid=d["uid"],
        status=d["status"],
        current_step=d.get("current_step"),
        started_at=d.get("started_at"),
        finished_at=d.get("finished_at"),
        error=d.get("error"),
        retry_count=d.get("retry_count"),
    )


@app.get("/model_runs/{run_id}", response_model=ModelRunStatus)
def get_model_run(run_id: str):
    """단일 추론 작업의 진행 상태 조회."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT run_id, uid, status, current_step,
                          started_at, finished_at, error, retry_count
                   FROM model_runs WHERE run_id = %s""",
                (run_id,),
            )
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"model_runs 조회 실패: {e}")
    if not row:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} not found")
    return _row_to_model_run(row)


@app.get("/model_runs", response_model=List[ModelRunStatus])
def list_model_runs(
    uid:    str           = Query(..., min_length=1),
    status: Optional[str] = Query(None),
):
    """uid 기반 추론 작업 목록 — *진행 중*인 작업을 찾을 때 사용."""
    where_parts = ["uid = %s"]
    params: List[Any] = [uid]
    if status:
        where_parts.append("status = %s")
        params.append(status)
    sql = ("SELECT run_id, uid, status, current_step, "
           "started_at, finished_at, error, retry_count "
           "FROM model_runs WHERE " + " AND ".join(where_parts) +
           " ORDER BY started_at DESC LIMIT 50")
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    except Exception:
        return []
    return [_row_to_model_run(r) for r in rows]


# ─────────────────────────────────────────────
# Phase G.3 — 비동기 prediction job
# 동기 5분 블로킹 → POST /predict-jobs 즉시 202 + job_id 반환. 백그라운드 thread가
# 기존 /predict를 self-call로 실행. 폴링은 GET /predict-jobs/{job_id}.
#
# 한계: BackgroundThread는 *컨테이너 재시작 시 작업 유실*. Phase G+1에서 Celery+Redis
# 기반으로 worker 재시작 무손실 보강 예정.
# ─────────────────────────────────────────────
class PredictJobResponse(BaseModel):
    job_id:            str
    status:            str
    current_step:      Optional[str]      = None
    started_at:        Optional[datetime] = None
    finished_at:       Optional[datetime] = None
    error:             Optional[str]      = None
    prediction_run_id: Optional[str]      = None  # 완료 시 GET /predictions/{id}로 결과 회수


def _self_call_predict(uid: str, job_id: str) -> None:
    """백그라운드 thread에서 자기 자신의 /predict를 호출. Idempotency-Key=job_id로
    멱등성 키 활용 — 같은 job_id로 재호출되면 기존 결과 즉시 반환."""
    try:
        # job_id를 Idempotency-Key로 보내 두 번 클릭 보호
        requests.post(
            "http://localhost:8000/predict",
            json={"uid": uid},
            headers={"Idempotency-Key": job_id},
            timeout=600,
        )
    except Exception as e:
        logger.error(f"[Phase G.3] async predict 실패 (job_id={job_id}): {e}")


@app.post("/predict-jobs", status_code=202)
def start_predict_job(req: dict):
    """비동기 추론 작업 시작 — 즉시 202 + job_id 반환. 백그라운드에서 실제 추론 실행.

    클라이언트는 GET /predict-jobs/{job_id}를 폴링해 진행 상태를 추적하고,
    완료 시 prediction_run_id로 GET /predictions/{id}에서 결과 회수.
    """
    uid = req.get("uid")
    if not uid:
        raise HTTPException(status_code=422, detail="uid 필수")

    job_id = str(uuid.uuid4())

    # model_runs INSERT (queued) — Phase 3에서 도입한 상태 머신 재사용
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO model_runs (run_id, uid, status, current_step)
                   VALUES (%s, %s, 'queued', 'job_init')""",
                (job_id, uid),
            )
    except Exception as e:
        logger.warning(f"[Phase G.3] model_runs INSERT 실패 (테이블 미적용?): {e}")

    # 백그라운드 thread로 self-call
    threading.Thread(
        target=_self_call_predict, args=(uid, job_id), daemon=True,
    ).start()

    return {"job_id": job_id, "status": "queued"}


@app.get("/predict-jobs/{job_id}", response_model=PredictJobResponse)
def get_predict_job(job_id: str):
    """진행 상태 + 완료 시 prediction_run_id 반환. job_id == prediction_run_id.

    클라이언트는 status가 'succeeded'면 prediction_run_id로 GET /predictions/{id}
    호출해 *완료된 결과 본문*을 회수.
    """
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT run_id, uid, status, current_step,
                          started_at, finished_at, error
                   FROM model_runs WHERE run_id = %s""",
                (job_id,),
            )
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"model_runs 조회 실패: {e}")

    if not row:
        raise HTTPException(status_code=404, detail=f"job_id={job_id} not found")

    cols = ["run_id", "uid", "status", "current_step",
            "started_at", "finished_at", "error"]
    d = dict(zip(cols, row))

    # 성공 시 prediction_run_id 매핑 (job_id == run_id)
    prediction_run_id = job_id if d["status"] == "succeeded" else None

    return PredictJobResponse(
        job_id=str(d["run_id"]),
        status=d["status"],
        current_step=d.get("current_step"),
        started_at=d.get("started_at"),
        finished_at=d.get("finished_at"),
        error=d.get("error"),
        prediction_run_id=prediction_run_id,
    )

