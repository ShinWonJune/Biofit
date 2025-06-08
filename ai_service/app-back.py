# ai_service/app.py
import os, uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2

from db_utils import get_conn
from sleep_coach_full_kr_v6 import main as coach_main  

DB_TABLE = "predictions"
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/app/models/mistral-7b.q4_K_M.gguf"))
WINDOW = int(os.getenv("WINDOW", 7))

app = FastAPI()


class Req(BaseModel):
    uid: str


@app.post("/predict")
def predict(req: Req):
    run_id = uuid.uuid4()

    try:
        coach_main(uid=req.uid, model_path=MODEL_PATH, window=WINDOW)
    except Exception as e:
        raise HTTPException(500, f"coach_main error: {e}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {DB_TABLE}(uid, run_id, note) VALUES (%s, %s, %s)",
            (req.uid, str(run_id), "run completed"),
        )
        conn.commit()

    return {"status": "ok", "run_id": str(run_id)}
