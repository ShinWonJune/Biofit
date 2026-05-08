# data_service/csv_to_db.py
import os
import glob
import pandas as pd
import sqlalchemy
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
# 반드시 환경변수에서 DATABASE_URL을 읽어야 함
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

engine = sqlalchemy.create_engine(DATABASE_URL)

CSV_DIR = Path("./fitbit_csv")  # FITBIT CSV가 이 위치에 저장됨

# CSV 파일명 별로 DB 테이블명을 지정할 수 있다.
# 예: heart_rate_1min.csv → uid_heart_rate_1min
# 여기서 uid는 CSV 내부 첫 번째 컬럼, 혹은 파일이름으로부터 파싱해야 함.
# 하지만 우리는 00-CallAPI.py가 CSV 안에 user_id 컬럼을 이미 포함해서 만든다고 가정.


# §9.1 expand dual-write — DUAL_WRITE_NORMALIZED=1 시 fitbit_daily_features에도 upsert.
# 매핑 없는 fname(예: heart_rate_1min, activity_1min)은 분 단위 데이터라 dual-write 대상 아님.
_DUAL_WRITE_COLUMN_MAP = {
    "sleep_summary": ["efficiency", "stage_deep", "stage_light", "stage_rem", "stage_wake"],
    "activity_sum":  ["steps", "distance", "calories"],
    "resting_hr":    ["resting_hr"],
    "azm":           ["azm_total", "azm_fatburn", "azm_cardio"],
}

# CSV 컬럼명 → fitbit_daily_features 컬럼명 rename map.
# fitbit_daily_features는 wide-format이라 도메인 명확성을 위해 prefix(`azm_`)를 붙였지만,
# Fitbit AZM CSV 헤더는 prefix 없이 (total, fatburn, cardio)로 와서 명시적 rename 필요.
_DUAL_WRITE_COLUMN_RENAME = {
    "azm": {"total": "azm_total", "fatburn": "azm_fatburn", "cardio": "azm_cardio"},
}


def _maybe_dual_write_normalized(uid: str, fname: str, df: pd.DataFrame) -> None:
    """DUAL_WRITE_NORMALIZED=1이면 일별 집계해 fitbit_daily_features에 upsert."""
    if os.getenv("DUAL_WRITE_NORMALIZED", "0") != "1":
        return

    cols = _DUAL_WRITE_COLUMN_MAP.get(fname)
    if cols is None or "date" not in df.columns:
        return

    rename = _DUAL_WRITE_COLUMN_RENAME.get(fname)
    df_src = df.rename(columns=rename) if rename else df

    keep = ["user_id", "date"] + [c for c in cols if c in df_src.columns]
    if len(keep) <= 2:
        logging.warning(f"[§9.1 dual-write] {uid}/{fname}: no expected cols present")
        return

    df_w = df_src[keep].copy()
    df_w["date"] = pd.to_datetime(df_w["date"], errors="coerce").dt.date
    df_w = df_w.dropna(subset=["date"])
    df_agg = df_w.groupby(["user_id", "date"], as_index=False).mean(numeric_only=True)
    if df_agg.empty:
        return

    cols_str   = ", ".join(df_agg.columns)
    placeholders = ", ".join([f":{c}" for c in df_agg.columns])
    update_str = ", ".join(
        f"{c}=EXCLUDED.{c}" for c in df_agg.columns if c not in ("user_id", "date")
    )
    sql = sqlalchemy.text(
        f"INSERT INTO fitbit_daily_features ({cols_str}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT (user_id, date) DO UPDATE SET {update_str}"
    )
    with engine.begin() as conn:
        for _, row in df_agg.iterrows():
            conn.execute(sql, row.to_dict())
    print(f">> [§9.1 dual-write] {uid}/{fname} → fitbit_daily_features ({len(df_agg)} rows upserted)")


def load_raw_csv_to_db():
    for csv_path in CSV_DIR.glob("*.csv"):
        fname = csv_path.stem  # ex) "heart_rate_1min"
        # CSV 내부에 "user_id" 컬럼이 들어있으므로, 첫 행에서 user_id 추출
        df_sample = pd.read_csv(csv_path, nrows=1, dtype=str)
        if "user_id" not in df_sample.columns:
            continue
        uid = df_sample["user_id"].iloc[0]
        table_name = f"{uid}_{fname}"
        df = pd.read_csv(csv_path)
        # DB에 replace 방식으로 저장 (이미 존재하면 덮어쓰기)
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists="replace",
            index=False,
            chunksize=500
        )
        print(f">> Raw CSV '{csv_path.name}' → '{table_name}' ({len(df)} rows)")
        # §9.1 expand opt-in: 일별 집계 컬럼은 fitbit_daily_features에도 upsert
        _maybe_dual_write_normalized(uid, fname, df)

if __name__ == "__main__":
    load_raw_csv_to_db()
