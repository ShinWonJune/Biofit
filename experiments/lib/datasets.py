"""Phase B — PSQI 4 차원 학습용 master 데이터셋 빌드.

`personal_analysis.py`의 features 빌드 로직을 재사용 가능한 형태로 추출.
저녁 세분화(Phase A.2)와 PSQI 4 차원 target(Phase A.3)을 추가로 통합.

핵심 산출:
    build_master_dataset(data_dir, feedback_csv) →
        DataFrame with columns:
          - 식별자: user_id, date
          - 24 features (기존 22 + 저녁 세분화 2)
          - 4 PSQI targets: c1_subjective, c2_latency, c3_duration, c4_efficiency
          - 합산: score_total
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from . import features as F
from . import psqi as P


HRV_COVERAGE_THRESHOLD = 0.7


def _dedupe(df: pd.DataFrame, agg: dict) -> pd.DataFrame:
    return df.groupby(["user_id", "date"], as_index=False).agg(agg)


# ─────────────────────────────────────────────────────────
# 일별 base (sleep_summary + activity_sum + resting_hr + azm + hrv)
# ─────────────────────────────────────────────────────────
def load_daily_baseline(data_dir: Path) -> pd.DataFrame:
    """일별 기본 features. personal_analysis.py:load_baseline_daily 이식."""
    sleep = _dedupe(
        pd.read_csv(data_dir / "sleep_summary.csv", parse_dates=["date"]),
        {c: ("mean" if c == "efficiency" else "sum") for c in
         ["minutes_asleep", "time_in_bed", "stage_deep", "stage_light",
          "stage_rem", "stage_wake", "efficiency",
          "cnt_deep", "cnt_light", "cnt_rem", "cnt_wake"]},
    )
    act = _dedupe(
        pd.read_csv(data_dir / "activity_sum.csv", parse_dates=["date"]),
        {"steps": "sum", "distance": "sum", "calories": "sum"},
    )
    rhr = _dedupe(
        pd.read_csv(data_dir / "resting_hr.csv", parse_dates=["date"]),
        {"resting_hr": "mean"},
    )
    azm = _dedupe(
        pd.read_csv(data_dir / "azm.csv", parse_dates=["date"]),
        {"total": "sum", "fatburn": "sum", "cardio": "sum"},
    ).rename(columns={"total": "azm_total",
                      "fatburn": "azm_fatburn",
                      "cardio": "azm_cardio"})

    hrv = pd.read_csv(data_dir / "hrv.csv", parse_dates=["date"])
    hrv_d = (hrv.groupby(["user_id", "date"], as_index=False)
             .agg(rmssd_mean=("rmssd", "mean"),
                  hf_mean=("hf", "mean"),
                  lf_mean=("lf", "mean"),
                  hrv_coverage=("coverage", "mean")))
    bad = hrv_d["hrv_coverage"] < HRV_COVERAGE_THRESHOLD
    hrv_d.loc[bad, ["rmssd_mean", "hf_mean", "lf_mean"]] = np.nan
    hrv_d = hrv_d.drop(columns="hrv_coverage")

    df = (sleep.merge(act, on=["user_id", "date"], how="left")
          .merge(rhr, on=["user_id", "date"], how="left")
          .merge(azm, on=["user_id", "date"], how="left")
          .merge(hrv_d, on=["user_id", "date"], how="left")
          .sort_values("date").reset_index(drop=True))

    df = df[(df["efficiency"] > 0) & (df["efficiency"] <= 100)].reset_index(drop=True)
    df["sleep_duration_h"] = df["time_in_bed"] / 60.0
    return df


# ─────────────────────────────────────────────────────────
# 시간대 features (steps_morning/afternoon/evening/night + last_active_hour)
# ─────────────────────────────────────────────────────────
def build_activity_time_features(data_dir: Path) -> pd.DataFrame:
    am = pd.read_csv(data_dir / "activity_1min.csv", parse_dates=["date"])
    am["hour"] = pd.to_datetime(am["time"], format="%H:%M:%S",
                                errors="coerce").dt.hour

    def bucket(h):
        if pd.isna(h):
            return "unknown"
        if 6 <= h < 12:
            return "morning"
        if 12 <= h < 18:
            return "afternoon"
        if 18 <= h < 24:
            return "evening"
        return "night"

    am["tod"] = am["hour"].apply(bucket)

    pivot = (am.groupby(["user_id", "date", "tod"], as_index=False)["steps"]
             .sum()
             .pivot(index=["user_id", "date"], columns="tod", values="steps")
             .reset_index().fillna(0))
    pivot.columns.name = None
    pivot = pivot.rename(columns={c: f"steps_{c}" for c in pivot.columns
                                  if c not in {"user_id", "date"}})

    last = (am[am["steps"] >= 50]
            .groupby(["user_id", "date"], as_index=False)["hour"]
            .max().rename(columns={"hour": "last_active_hour"}))
    return pivot.merge(last, on=["user_id", "date"], how="left")


# ─────────────────────────────────────────────────────────
# 수면 시간대 (bedtime_hour, waketime_hour, dev_min)
# ─────────────────────────────────────────────────────────
def build_sleep_time_features(data_dir: Path) -> pd.DataFrame:
    sd = pd.read_csv(data_dir / "sleep_detail.csv", parse_dates=["date"])
    t = sd["time"].astype(str).str.split(".").str[0]
    dt = pd.to_datetime(
        sd["date"].dt.strftime("%Y-%m-%d") + " " + t,
        format="%Y-%m-%d %H:%M:%S", errors="coerce")
    sd["start"] = dt
    sd["end"] = dt + pd.to_timedelta(sd["duration"], unit="s")
    sess = (sd.groupby(["user_id", "date"], as_index=False)
            .agg(sleep_start=("start", "min"),
                 sleep_end=("end", "max")))
    sess["bedtime_hour"] = (sess["sleep_start"].dt.hour
                            + sess["sleep_start"].dt.minute / 60.0)
    sess["waketime_hour"] = (sess["sleep_end"].dt.hour
                             + sess["sleep_end"].dt.minute / 60.0)
    sess.loc[sess["bedtime_hour"] < 12, "bedtime_hour"] += 24

    bed_mean = sess["bedtime_hour"].mean()
    wake_mean = sess["waketime_hour"].mean()
    sess["bedtime_dev_min"] = (sess["bedtime_hour"] - bed_mean) * 60
    sess["waketime_dev_min"] = (sess["waketime_hour"] - wake_mean) * 60
    return sess[["user_id", "date", "bedtime_hour", "waketime_hour",
                 "bedtime_dev_min", "waketime_dev_min"]]


# ─────────────────────────────────────────────────────────
# 취침 직전 활동 (pre_sleep_steps_0_2h, 2_4h)
# ─────────────────────────────────────────────────────────
def add_pre_sleep_activity(df: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    am = pd.read_csv(data_dir / "activity_1min.csv", parse_dates=["date"])
    am["hour"] = pd.to_datetime(am["time"], format="%H:%M:%S",
                                errors="coerce").dt.hour
    bed = df.set_index(["user_id", "date"])["bedtime_hour"].dropna()
    bh24 = (bed % 24).astype(int)
    am2 = am.set_index(["user_id", "date"]).join(
        bh24.rename("bed_h_24"), how="inner").reset_index()
    am2 = am2.dropna(subset=["bed_h_24", "hour"])
    am2["bed_h_24"] = am2["bed_h_24"].astype(int)
    am2["dh"] = (am2["bed_h_24"] - am2["hour"]) % 24
    pre02 = (am2[am2["dh"].between(0, 2)]
             .groupby(["user_id", "date"], as_index=False)["steps"].sum()
             .rename(columns={"steps": "pre_sleep_steps_0_2h"}))
    pre24 = (am2[am2["dh"].between(2, 4)]
             .groupby(["user_id", "date"], as_index=False)["steps"].sum()
             .rename(columns={"steps": "pre_sleep_steps_2_4h"}))
    return df.merge(pre02, on=["user_id", "date"], how="left") \
             .merge(pre24, on=["user_id", "date"], how="left")


# ─────────────────────────────────────────────────────────
# Phase A.2 — 저녁 세분화 features 추가 (운동 종료 시각 기준)
# ─────────────────────────────────────────────────────────
def add_evening_split(df: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    am = pd.read_csv(data_dir / "activity_1min.csv")
    evening = F.compute_evening_split(am)
    # Phase A.2의 컬럼만 유지 — workout_end_hour는 *진단용*이라 features 제외
    keep = ["user_id", "date", "steps_evening_18_20", "steps_evening_20_22"]
    evening = evening[keep]
    evening["date"] = pd.to_datetime(evening["date"])
    return df.merge(evening, on=["user_id", "date"], how="left")


# ─────────────────────────────────────────────────────────
# Phase A.3 — PSQI 4 차원 target 추가
# ─────────────────────────────────────────────────────────
def add_psqi_targets(
    df: pd.DataFrame,
    data_dir: Path,
    feedback_csv: Optional[Path] = None,
    bedtime_log_csv: Optional[Path] = None,
) -> pd.DataFrame:
    """PSQI 4 차원 점수 + 합산을 target 컬럼으로 추가.

    Phase A.4 보강: bedtime_log_csv가 있으면 회원 입력 침대 시각을 C2 잠복기 산출의
    1순위로 사용. 없으면 sleep_detail wake 누적 fallback. latency_source 컬럼이
    'user_input' / 'fitbit_wake'로 박제되어 *어느 일자가 정확*한지 진단 가능.
    """
    daily = pd.read_csv(data_dir / "sleep_summary.csv")
    daily["date"] = pd.to_datetime(daily["date"]).dt.date

    sleep_detail = pd.read_csv(data_dir / "sleep_detail.csv")

    feedback = None
    if feedback_csv is not None and feedback_csv.exists():
        feedback = pd.read_csv(feedback_csv)
        feedback["date"] = pd.to_datetime(feedback["date"]).dt.strftime("%Y-%m-%d")

    bedtime_log = None
    if bedtime_log_csv is not None and bedtime_log_csv.exists():
        bedtime_log = pd.read_csv(bedtime_log_csv)
        # 컬럼 정합 — user_id, bedtime_at만 필수
        if "bedtime_at" not in bedtime_log.columns:
            bedtime_log = None
        else:
            bedtime_log = bedtime_log[["user_id", "bedtime_at"]].copy()

    psqi = P.compute_psqi_scores(
        daily,
        feedback=feedback,
        sleep_detail=sleep_detail,
        bedtime_log=bedtime_log,
    )
    psqi["date"] = pd.to_datetime(psqi["date"])

    target_cols = ["c1_subjective", "c2_latency", "c3_duration",
                   "c4_efficiency", "score_total"]
    # latency_source는 진단용 — 학습 features는 아니지만 master DF에 박제
    diag_cols = ["latency_source"] if "latency_source" in psqi.columns else []
    return df.merge(psqi[["user_id", "date"] + target_cols + diag_cols],
                    on=["user_id", "date"], how="left")


# ─────────────────────────────────────────────────────────
# 통합 빌더
# ─────────────────────────────────────────────────────────
FEATURE_COLUMNS = [
    # 운동량 (6)
    "steps", "distance", "calories",
    "azm_total", "azm_fatburn", "azm_cardio",
    # 운동 시간대 (8 — 저녁 세분화 포함)
    "steps_morning", "steps_afternoon", "steps_evening",
    "steps_evening_18_20", "steps_evening_20_22",
    "steps_night", "last_active_hour",
    # 취침 직전 활동 (2)
    "pre_sleep_steps_0_2h", "pre_sleep_steps_2_4h",
    # 수면 시간대 (5)
    "bedtime_hour", "waketime_hour",
    "bedtime_dev_min", "waketime_dev_min", "sleep_duration_h",
    # HRV/HR (4)
    "resting_hr", "rmssd_mean", "hf_mean", "lf_mean",
]

TARGET_COLUMNS = ["c1_subjective", "c2_latency", "c3_duration",
                  "c4_efficiency", "score_total"]


def build_master_dataset(
    data_dir: Path,
    feedback_csv: Optional[Path] = None,
    bedtime_log_csv: Optional[Path] = None,
) -> pd.DataFrame:
    """24 features + 5 PSQI targets + latency_source 진단 컬럼.

    Args:
        data_dir: JG-Data 등 raw CSV 디렉토리
        feedback_csv: 회원 자기보고 CSV (sleep_score 0~3)
        bedtime_log_csv: Phase A.4 침대 시각 로그 CSV. DB의 bedtime_log를 export한 형태.
            None이면 C2 잠복기는 fitbit wake 누적 fallback만 사용.

    Returns: (user_id, date) PK + FEATURE_COLUMNS + TARGET_COLUMNS + latency_source
    """
    base = load_daily_baseline(data_dir)
    full = (base
            .merge(build_activity_time_features(data_dir),
                   on=["user_id", "date"], how="left")
            .merge(build_sleep_time_features(data_dir),
                   on=["user_id", "date"], how="left"))
    full = add_pre_sleep_activity(full, data_dir)
    full = add_evening_split(full, data_dir)
    full = add_psqi_targets(
        full, data_dir,
        feedback_csv=feedback_csv,
        bedtime_log_csv=bedtime_log_csv,
    )

    # (user_id, date) + features + targets + 진단 컬럼 보존
    keep = ["user_id", "date"] + FEATURE_COLUMNS + TARGET_COLUMNS + ["latency_source"]
    keep = [c for c in keep if c in full.columns]
    return full[keep].sort_values(["user_id", "date"]).reset_index(drop=True)
