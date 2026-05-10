"""Phase A.2 — 저녁 시간대 세분화 features 산출.

기존 features는 *steps_evening(18-24)* 단일 binning이라 *취침 직전 운동*(20-22 종료)과
*충분한 여유 운동*(18-20 종료)을 구분하지 못함. 이 모듈은 *운동 종료 시각*을 기준으로
저녁대를 둘로 나눠 PSQI C2(잠복기) 차원 모델이 잡을 수 있는 신호를 분리한다.

핵심 가설: `steps_evening_20_22`(취침 직전)는 C2 잠복기에 *부정적* SHAP, 같은 양이라도
`steps_evening_18_20`(여유 시간 운동)은 *긍정적* SHAP을 잡을 가능성.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

# 분당 steps 임계값 — 이 이상이면 *운동 minute*으로 간주.
# 일반 보행은 분당 60~100 steps, 헬스장 활동은 100+ steps.
# 너무 낮으면 일상 보행도 포함, 너무 높으면 강도 낮은 운동 누락.
STEPS_INTENSITY_THRESHOLD = 60


def compute_evening_split(
    df_min: pd.DataFrame,
    intensity_threshold: int = STEPS_INTENSITY_THRESHOLD,
) -> pd.DataFrame:
    """운동 *종료* 시각 기준 저녁대 세분화 features 산출.

    Args:
        df_min: 분 단위 활동 데이터. 컬럼 = (user_id, date, time, steps, ...).
            date는 ISO 문자열 또는 date 형. time은 'HH:MM:SS' 문자열.
        intensity_threshold: 분당 steps 임계값. 이 이상인 minute을 *운동*으로 간주.

    Returns:
        DataFrame with columns:
            - user_id
            - date
            - workout_end_hour      그 날의 마지막 운동 시각 (운동 없는 날 NaN)
            - steps_evening_18_20   운동 종료가 [18, 20)인 날의 18-20시 steps 합
            - steps_evening_20_22   운동 종료가 [20, 22)인 날의 20-22시 steps 합
        운동이 없는 날 또는 종료 시각이 저녁대 밖인 날은 두 evening 컬럼이 NaN.
    """
    if df_min.empty:
        return pd.DataFrame(columns=[
            "user_id", "date",
            "workout_end_hour",
            "steps_evening_18_20",
            "steps_evening_20_22",
        ])

    df = df_min.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["hour"] = pd.to_datetime(df["time"], format="%H:%M:%S", errors="coerce").dt.hour
    df = df.dropna(subset=["hour"])
    df["hour"] = df["hour"].astype(int)

    # 운동 종료 시각 = (강도 임계값 이상인 minute의) 그 날 *마지막 hour*
    workout_min = df[df["steps"] >= intensity_threshold]
    workout_end = (
        workout_min.groupby(["user_id", "date"])["hour"]
        .max()
        .rename("workout_end_hour")
        .reset_index()
    )

    # 18-20 종료 일자에서 18-20시 steps 합
    end_18_20 = workout_end[
        (workout_end["workout_end_hour"] >= 18) & (workout_end["workout_end_hour"] < 20)
    ]
    steps_18_20 = (
        df.merge(end_18_20[["user_id", "date"]], on=["user_id", "date"])
        .loc[lambda x: x["hour"].between(18, 19, inclusive="both")]
        .groupby(["user_id", "date"])["steps"]
        .sum()
        .rename("steps_evening_18_20")
        .reset_index()
    )

    # 20-22 종료 일자에서 20-22시 steps 합
    end_20_22 = workout_end[
        (workout_end["workout_end_hour"] >= 20) & (workout_end["workout_end_hour"] < 22)
    ]
    steps_20_22 = (
        df.merge(end_20_22[["user_id", "date"]], on=["user_id", "date"])
        .loc[lambda x: x["hour"].between(20, 21, inclusive="both")]
        .groupby(["user_id", "date"])["steps"]
        .sum()
        .rename("steps_evening_20_22")
        .reset_index()
    )

    # 모든 (user_id, date) 조합을 base로 left-join. 빈 일자는 NaN으로 유지.
    base = df[["user_id", "date"]].drop_duplicates()
    out = (
        base
        .merge(workout_end, on=["user_id", "date"], how="left")
        .merge(steps_18_20, on=["user_id", "date"], how="left")
        .merge(steps_20_22, on=["user_id", "date"], how="left")
        .sort_values(["user_id", "date"])
        .reset_index(drop=True)
    )
    return out


def compute_evening_split_from_csv(
    csv_path: Path | str,
    intensity_threshold: int = STEPS_INTENSITY_THRESHOLD,
) -> pd.DataFrame:
    """CSV 경로 → 저녁 세분화 features. CLI/노트북에서 직접 호출용 편의 함수."""
    df_min = pd.read_csv(csv_path)
    return compute_evening_split(df_min, intensity_threshold=intensity_threshold)


# ─────────────────────────────────────────────────────────
# CLI 검증 — 회원 23RK3S 데이터로 분포 점검
# ─────────────────────────────────────────────────────────
def _main() -> None:
    """`python -m experiments.lib.features`로 호출해 회원 23RK3S 데이터의 분포 출력."""
    repo_root = Path(__file__).resolve().parents[2]
    csv = repo_root / "JG-Data" / "activity_1min.csv"
    if not csv.exists():
        print(f"[skip] activity_1min.csv not found at {csv}")
        return

    print(f"[load] {csv}")
    out = compute_evening_split_from_csv(csv)

    n_total = len(out)
    n_workout = out["workout_end_hour"].notna().sum()
    n_18_20 = out["steps_evening_18_20"].notna().sum()
    n_20_22 = out["steps_evening_20_22"].notna().sum()

    print(f"\n[summary] 회원 데이터 요약")
    print(f"  - 전체 일자 수            : {n_total}")
    print(f"  - 운동 발생 일자          : {n_workout}  ({n_workout/n_total*100:.1f}%)")
    print(f"  - 운동 종료 18-20시 일자  : {n_18_20}    ({n_18_20/n_total*100:.1f}%)")
    print(f"  - 운동 종료 20-22시 일자  : {n_20_22}    ({n_20_22/n_total*100:.1f}%)")

    if n_18_20 > 0:
        s = out["steps_evening_18_20"].dropna()
        print(f"\n[steps_evening_18_20] 분포 (운동 발생 일자만)")
        print(f"  mean={s.mean():.0f}  median={s.median():.0f}  max={s.max():.0f}")
    if n_20_22 > 0:
        s = out["steps_evening_20_22"].dropna()
        print(f"\n[steps_evening_20_22] 분포 (운동 발생 일자만)")
        print(f"  mean={s.mean():.0f}  median={s.median():.0f}  max={s.max():.0f}")

    # 두 컬럼이 *서로 다른 일자* 분포인지 (mutually exclusive 가설 검증)
    both_set = (out["steps_evening_18_20"].notna() & out["steps_evening_20_22"].notna()).sum()
    print(f"\n[가설 검증] 두 컬럼이 *동시에* 채워진 일자 = {both_set}")
    print(f"  → 0이어야 정상 (운동 종료 시각은 일자당 단일 hour이므로 한쪽에만 속함)")


if __name__ == "__main__":
    _main()
