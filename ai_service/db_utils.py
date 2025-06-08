# ai_service/db_utils.py
import os
import pandas as pd
import psycopg2
from psycopg2 import sql
import logging

# 로거 설정
logger = logging.getLogger("db_utils")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)


def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")
    return psycopg2.connect(db_url)


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
    # --- 디버그 로그 찍기 ---
    logger.info(f"[read_table] 실행 SQL: {sql_str}")
    df = pd.read_sql(sql_str, conn)
    logger.info(f"[read_table] {table_name} → 행 {len(df)}, 컬럼 {list(df.columns)}")
    logger.info(f"[read_table] 샘플 데이터:\n{df.head(5).to_string(index=False)}")
    # -------------------------

    conn.close()
    return df
