# merge_daily_tables.py
import pandas as pd
from pathlib import Path
from functools import reduce

DATA_DIR = Path("../../fitbit_csv")          # Colab / 로컬 환경에 맞게 바꿔 주세요
OUT_FILE = DATA_DIR / "daily_merged.csv"


##############################################################################
# 1) 헬퍼: 파일을 읽어오며 날짜 컬럼 이름을 통일(date) + dtype을 date 로 맞춘다
##############################################################################
def load_daily_csv(fname: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / fname)

    # ─── 날짜 컬럼 자동 탐색 & 표준화 ────
    date_candidates = [c for c in df.columns
                       if c.lower() in {"date", "dt", "day", "timestamp"}]
    if not date_candidates:
        raise ValueError(f"Could not find date column in `{fname}`.")
    date_col = date_candidates[0]                 # Use first candidate
    df[date_col] = pd.to_datetime(df[date_col]).dt.date
    if date_col != "date":                        # 통일
        df = df.rename(columns={date_col: "date"})

    return df


##############################################################################
# 2) 개별 테이블 로드
##############################################################################
base = load_daily_csv("daily_biometrics.csv")      # HR(m / std…)+HRV
tables_to_merge = [
    ("activity_sum.csv",  "_act"),                # steps, distance, calories
    ("azm.csv",           "_azm"),                # active-zone-minutes
    ("resting_hr.csv",    "_rest"),               # resting HR
    ("sleep_summary.csv", "_sleep"),              # efficiency, duration …
]

other_tables = []
for fname, suffix in tables_to_merge:
    df = load_daily_csv(fname)
    # ⚠️ 동일한 피처명이 있을 때 뒤쪽 파일이 덮어쓰지 않도록 suffix 부여
    dup_cols = set(df.columns) & set(base.columns) - {"date", "user_id"}
    df = df.rename(columns={c: f"{c}{suffix}" for c in dup_cols})
    other_tables.append(df)


##############################################################################
# 3) outer join(왼쪽 = base) 으로 순차 머지
##############################################################################
def _merge(left, right):
    keys = ["date"] + ([ "user_id" ] if "user_id" in left.columns
                                         and "user_id" in right.columns else [])
    return left.merge(right, on=keys, how="left")

merged = reduce(_merge, other_tables, base)

##############################################################################
# 4) 저장
##############################################################################
merged.to_csv(OUT_FILE, index=False)
print(f"[+]  {OUT_FILE}  (rows={len(merged)},  cols={len(merged.columns)})")
