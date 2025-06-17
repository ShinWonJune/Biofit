# ai_service/token_log.py
import os, csv, pathlib, datetime
from sqlalchemy import create_engine, text

LOG_CSV = "/app/logs/token_usage.csv"
DB_URL  = os.getenv("DATABASE_URL")  # docker-compose 와 동일

engine = create_engine(DB_URL, pool_pre_ping=True)

def log(uid: str, p_tok: int, c_tok: int):
    ts = datetime.datetime.utcnow().isoformat()

    # 1) CSV
    pathlib.Path(LOG_CSV).parent.mkdir(parents=True, exist_ok=True)
    write_hdr = not pathlib.Path(LOG_CSV).exists()
    with open(LOG_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if write_hdr:
            w.writerow(["timestamp", "uid", "prompt_tokens", "completion_tokens"])
        w.writerow([ts, uid, p_tok, c_tok])

    # 2) DB (try/except 로 안전하게)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO token_usage(uid, prompt_tokens, completion_tokens)
                VALUES (:u, :p, :c)
            """), {"u": uid, "p": p_tok, "c": c_tok})
    except Exception as e:
        print(f"[WARN] token_usage DB insert 실패: {e}")
