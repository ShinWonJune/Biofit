import pandas as pd

df = pd.read_csv("../../fitbit_csv/daily_merged.csv")

# ── (A) user_id 가 있을 경우 ───────────────────────────────
key = ["user_id", "date"] if "user_id" in df.columns else ["date"]

dupes = (df.groupby(key).size()              # 키별 행 수
           .reset_index(name="cnt")
           .query("cnt > 1"))
print(f"Number of duplicate keys: {len(dupes)}")
print(dupes.head())


# A) 가장 마지막 행 남기기
df_nodup = (df.sort_values("date")                   # 필요하다면 다른 컬럼 오름차순
              .drop_duplicates(subset=key, keep="last"))
df_nodup.to_csv("../../fitbit_csv/daily_merged_nodup.csv", index=False)

# B) 수치 컬럼 평균내기
num_cols = df.select_dtypes("number").columns.difference(key)
df_mean = (df.groupby(key)[num_cols].mean().reset_index())


import pandas as pd

IN  = "/workspace/01-class/01.sleep_check/01-data/daily_merged_filled.csv"
OUT = "/workspace/01-class/01.sleep_check/01-data/daily_merged_filled2.csv"

# 1) 읽기 ─ 날짜형 변환 & 정렬
df = pd.read_csv(IN, parse_dates=["date"])
df = df.sort_values(["user_id", "date"]) if "user_id" in df.columns else df.sort_values("date")

# 2) 사용자별(또는 전체)로 forward-fill → backward-fill
key   = ["user_id"] if "user_id" in df.columns else None
group = df.groupby(key) if key else [(None, df)]

filled_chunks = []
for _, g in group:
    g2 = g.ffill().bfill()        # 먼저 ffill, 남은 결측은 bfill
    filled_chunks.append(g2)

df_filled = pd.concat(filled_chunks, ignore_index=True)

# 3) 저장
df_filled.to_csv(OUT, index=False)
print(f"✅ Missing value interpolation completed → {OUT}")


import pandas as pd
import numpy as np

in_path = "/workspace/01-class/01.sleep_check/01-data/daily_merged_filled2.csv"

out_path = "/workspace/01-class/01.sleep_check/01-data/daily_merged_filled2_filled.csv"

df = pd.read_csv(in_path)

# 숫자형 열만 골라 -1 → NaN
num_cols = df.select_dtypes(include=["number"]).columns
df[num_cols] = df[num_cols].replace(-1, np.nan)

na_before = df.isna().sum().sum()

# forward → backward fill
df = df.ffill().bfill()

na_after = df.isna().sum().sum()

df.to_csv(out_path, index=False)

print("Total NaN count (after -1→NaN conversion):", na_before)
print("Total NaN count (after bidirectional interpolation):", na_after)
print(f"→ Cleaned file saved: {out_path}")
