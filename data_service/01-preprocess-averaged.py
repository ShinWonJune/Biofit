#!/usr/bin/env python
"""
Fitbit minute-level HR・HRV → daily tabular

* 입력 (fitbit_csv/ 하위)
  ├─ heart_rate_1min.csv : user_id,date,time,bpm
  └─ hrv.csv             : user_id,date,time(or timestamp),<hrv cols …>

* 출력
  └─ daily_biometrics.csv
      user_id,date,hr_mean,hr_std,hr_median,hr_max,hr_min,
      hrv_mean,hrv_std,hrv_median,hrv_max,hrv_min
"""
from pathlib import Path
import argparse, pandas as pd, numpy as np


###############################################################################
# 1) 공통 유틸
###############################################################################
def _read_csv(file: Path, **read_csv_kw) -> pd.DataFrame:
    if not file.exists():
        raise FileNotFoundError(file)
    return pd.read_csv(file, **read_csv_kw)

def _flatten_cols(df: pd.DataFrame, sep: str = "_") -> pd.DataFrame:
    """groupby().agg() 후 MultiIndex 열 → 평평한 문자열 열 이름으로 바꾼다."""
    df.columns = [sep.join(col).rstrip(sep) for col in df.columns.to_flat_index()]
    return df.reset_index()


###############################################################################
# 2) HR 분-단위 → 일-단위 통계
###############################################################################
def daily_from_hr(hr_csv: Path) -> pd.DataFrame:
    hr = _read_csv(hr_csv)

    # datetime 합치고 date 컬럼 만들기
    hr["dt"] = pd.to_datetime(hr["date"] + " " + hr["time"])
    hr["date"] = hr["dt"].dt.date

    # 하루 통계
    agg_hr = (
        hr.groupby(["user_id", "date"])["bpm"]
        .agg(["mean", "std", "median", "max", "min"])
        .rename(columns=lambda c: f"hr_{c}")
    )
    return _flatten_cols(agg_hr)


###############################################################################
# 3) HRV 데이터 하루-단위 통계  (컬럼명이 어떻게 되어 있든 모든 수치형 열에 대해 평균 등 계산)
###############################################################################
def daily_from_hrv(hrv_csv: Path) -> pd.DataFrame:
    hrv = _read_csv(hrv_csv)

    # 일부 Fitbit HRV 파일은 timestamp 하나로만 시간 정보가 있을 수 있음
    if {"time", "date"}.issubset(hrv.columns):
        hrv["dt"] = pd.to_datetime(hrv["date"] + " " + hrv["time"])
        hrv["date"] = hrv["dt"].dt.date
    elif "timestamp" in hrv.columns:
        hrv["dt"] = pd.to_datetime(hrv["timestamp"])
        hrv["date"] = hrv["dt"].dt.date
    else:
        # 이미 date 열만 있는 경우
        hrv["date"] = pd.to_datetime(hrv["date"]).dt.date

    numeric_cols = hrv.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        raise ValueError("No numeric columns found in HRV csv.")

    agg_funcs = {col: ["mean", "std", "median", "max", "min"] for col in numeric_cols}
    agg_hrv = hrv.groupby(["user_id", "date"]).agg(agg_funcs)
    agg_hrv.columns = [
        f"{c}_{stat}" for c, stat in agg_hrv.columns.to_flat_index()
    ]
    return agg_hrv.reset_index()


###############################################################################
# 4) main – 병합 & 저장
###############################################################################
def main(src_dir: Path, out_csv: Path):
    hr_daily  = daily_from_hr(src_dir / "heart_rate_1min.csv")
    hrv_daily = daily_from_hrv(src_dir / "hrv.csv")

    daily = hr_daily.merge(hrv_daily, on=["user_id", "date"], how="left")

    # 날짜 오름차순 정렬
    daily = daily.sort_values(["user_id", "date"])

    daily.to_csv(out_csv, index=False)
    print(f"[OK] wrote {out_csv} ({len(daily)} rows)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src_dir", default="/app/fitbit_csv", type=Path,
                        help="Folder containing original csv files")
    parser.add_argument("--out_csv", default="/app/daily_biometrics.csv", type=Path,
                        help="Path to save daily csv file")
    args = parser.parse_args()
    main(args.src_dir, args.out_csv)
