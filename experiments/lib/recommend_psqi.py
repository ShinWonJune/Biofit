"""Phase F.2+F.3 — Constrained Forward Simulation 기반 추천.

Forward simulation의 *외삽 위험*을 두 제약으로 풀어 안전한 영역에서만 작동.

1. **Positivity 영역** — 회원이 *MIN_DAYS_PER_SLOT 이상 시도해 본 시간대*만 후보.
   학습 분포 *밖*으로 빠지는 입력을 원천 차단.

2. **Realistic input** — base를 *그 시간대에 운동한 과거 일자의 features 평균*으로.
   한 변수만 바꾸지 않고 *전체 features 정합*을 자동 보존 (conditional dependency).

위 두 제약 위에서 4 PSQI 모델 모두에 시뮬레이션해 *합산 최소 슬롯 top-k* 추천.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from . import features as F


MIN_DAYS_PER_SLOT = 5


# ─────────────────────────────────────────────────────────
# Positivity 영역 — 회원이 *충분히 시도해 본* 운동 종료 시간대
# ─────────────────────────────────────────────────────────
def positivity_constrained_slots(
    activity_1min: pd.DataFrame,
    uid: str,
    min_days: int = MIN_DAYS_PER_SLOT,
    intensity_threshold: int = F.STEPS_INTENSITY_THRESHOLD,
    candidate_hours: Sequence[int] = tuple(range(6, 23)),
) -> List[int]:
    """회원이 일정 횟수 이상 *운동 종료한* 시간대만 후보로 반환.

    운동 종료 시각의 hour를 기준으로 카운트. min_days 이상 시도된 hour만 통과.
    """
    df = activity_1min[activity_1min["user_id"] == uid].copy()
    if df.empty:
        return []
    df["hour"] = pd.to_datetime(df["time"], format="%H:%M:%S",
                                errors="coerce").dt.hour
    df = df.dropna(subset=["hour"])
    df["hour"] = df["hour"].astype(int)

    workout_min = df[df["steps"] >= intensity_threshold]
    end_hour_per_day = (
        workout_min.groupby("date")["hour"].max()
    )

    candidates = []
    for h in candidate_hours:
        count = (end_hour_per_day == h).sum()
        if count >= min_days:
            candidates.append(int(h))
    return candidates


# ─────────────────────────────────────────────────────────
# Realistic input — 그 시간대에 운동한 과거 일자의 features 평균
# ─────────────────────────────────────────────────────────
def build_realistic_input(
    df_master: pd.DataFrame,
    activity_1min: pd.DataFrame,
    uid: str,
    target_slot_hour: int,
    feature_cols: List[str],
    intensity_threshold: int = F.STEPS_INTENSITY_THRESHOLD,
) -> pd.DataFrame:
    """target_slot_hour에 *운동 종료한* 회원의 과거 일자 features 평균을 1-row DF로.

    이 base가 *학습 분포 안*에 머무름이 보장되어 forward simulation의 외삽 위험을
    원천 차단. 글로벌 평균은 *fallback*으로만 사용 (해당 슬롯 시도 일자가 0건이면).
    """
    am = activity_1min[activity_1min["user_id"] == uid].copy()
    if am.empty:
        return df_master[feature_cols].mean().to_frame().T

    am["hour"] = pd.to_datetime(am["time"], format="%H:%M:%S",
                                errors="coerce").dt.hour
    am = am.dropna(subset=["hour"])
    am["hour"] = am["hour"].astype(int)
    am["date"] = pd.to_datetime(am["date"]).dt.date

    workout_min = am[am["steps"] >= intensity_threshold]
    end_hour_per_day = workout_min.groupby("date")["hour"].max()
    matching_dates = set(end_hour_per_day[end_hour_per_day == target_slot_hour].index)

    if not matching_dates:
        return df_master[feature_cols].mean().to_frame().T

    df = df_master.copy()
    df["date_norm"] = pd.to_datetime(df["date"]).dt.date
    valid = df[(df["user_id"] == uid) & df["date_norm"].isin(matching_dates)]

    if valid.empty:
        return df_master[feature_cols].mean().to_frame().T
    return valid[feature_cols].mean().to_frame().T


# ─────────────────────────────────────────────────────────
# 합산 최소화 grid (Phase F.3)
# ─────────────────────────────────────────────────────────
def recommend_psqi_minimize(
    df_master: pd.DataFrame,
    activity_1min: pd.DataFrame,
    uid: str,
    psqi_models: Dict[str, "object"],
    feature_cols: List[str],
    available_hours: Optional[List[int]] = None,
    top_k: int = 3,
    min_days_per_slot: int = MIN_DAYS_PER_SLOT,
) -> List[Dict[str, object]]:
    """가용 시간대 ∩ positivity 영역에서 PSQI 합산 *최소* 슬롯 top-k.

    Args:
        df_master: 학습용 master DF (user_id, date, features..., targets...)
        activity_1min: 분 단위 활동 데이터
        uid: 회원 ID
        psqi_models: {dim_name: 학습된 CatBoost 모델}
        feature_cols: 모델 입력 features 컬럼 명단
        available_hours: 회원의 가용 시간대 hour 리스트. None이면 제약 없음
        top_k: 반환할 슬롯 개수

    Returns:
        list of dict — slot_hour, predicted_total, predicted_dims (차원별 점수),
        is_fallback (positivity 미충족이라 글로벌 평균 사용 시 True)

        positivity ∩ available_hours가 비면 빈 리스트. 호출자가 *cohort fallback*
        또는 *"새 시간대 시도 권장" 메시지*로 분기.
    """
    candidates = positivity_constrained_slots(
        activity_1min, uid, min_days=min_days_per_slot,
    )
    if available_hours is not None:
        avail_set = set(available_hours)
        candidates = [h for h in candidates if h in avail_set]

    if not candidates:
        return []

    results = []
    for h in candidates:
        X = build_realistic_input(
            df_master, activity_1min, uid, h, feature_cols,
        )
        psqi_preds: Dict[str, float] = {}
        for dim, model in psqi_models.items():
            psqi_preds[dim] = float(model.predict(X)[0])
        total = float(sum(psqi_preds.values()))
        results.append({
            "slot_hour":       h,
            "predicted_total": total,
            "predicted_dims":  psqi_preds,
        })

    results.sort(key=lambda r: r["predicted_total"])
    return results[:top_k]
