# ai_service/db_utils.py
import os
import pandas as pd
import psycopg2
from psycopg2 import sql
import logging

logger = logging.getLogger("db_utils")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)


def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(db_url)


def read_feedback(table: str, uid: str) -> pd.DataFrame:
    """
    특정 사용자의 수면 피드백 데이터를 읽어오는 함수.
    """
    q = f'SELECT user_id, date, sleep_quality FROM "{table}" WHERE user_id = %s'
    logging.info(f"[read_feedback] SQL: {q}  params=({uid},)")
    df = pd.read_sql(q, get_conn(), params=(uid,))
    df["date"] = pd.to_datetime(df["date"])
    return df

def read_table(table_name: str, where: str | None = None) -> pd.DataFrame:
    conn = get_conn()
    if where:
        query = sql.SQL("SELECT * FROM {tbl} WHERE {cond}").format(
            tbl=sql.Identifier(table_name),
            cond=sql.SQL(where)
        )
    else:
        query = sql.SQL("SELECT * FROM {tbl}").format(
            tbl=sql.Identifier(table_name)
        )

    sql_str = query.as_string(conn)
    # --- 버그 로그 찍기 ---
    logger.info(f"[read_table] SQL: {sql_str}")
    df = pd.read_sql(sql_str, conn)
    logger.info(f"[read_table] {table_name} {len(df)}, 컬럼 {list(df.columns)}")
    logger.info(f"[read_table] :\n{df.head(5).to_string(index=False)}")
    # -------------------------

    conn.close()
    return df
