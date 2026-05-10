"""Phase B — PSQI 4 차원 CatBoost 학습 + holdout 평가 + naive baseline 비교.

검증 게이트 #1의 핵심 기준:
    - C1·C2·C3·C4 *각각이* 차원별 naive baseline 이김 (information coverage)
    - 합산 RMSE < 합산 naive baseline
    - 4 차원 SHAP이 *서로 다른 변수* top-1으로 잡음 (Phase C에서)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from catboost import CatBoostRegressor
except ImportError:  # 환경 부재 시 명시적 에러
    CatBoostRegressor = None  # type: ignore


PSQI_DIMS = ["c1_subjective", "c2_latency", "c3_duration", "c4_efficiency"]
DEFAULT_HOLDOUT_DAYS = 7


@dataclass
class DimEval:
    """차원별 평가 결과."""
    dim: str
    n_train: int
    n_test: int
    model_rmse: Optional[float]
    model_mae: Optional[float]
    baseline_rmse: Optional[float]
    baseline_mae: Optional[float]
    y_pred: Optional[np.ndarray] = None
    y_true: Optional[np.ndarray] = None

    @property
    def beats_baseline(self) -> Optional[bool]:
        if self.model_rmse is None or self.baseline_rmse is None:
            return None
        return self.model_rmse < self.baseline_rmse


@dataclass
class PSQIResults:
    """Phase B 학습·평가 통합 결과."""
    by_dim: Dict[str, DimEval] = field(default_factory=dict)
    total_model_rmse: Optional[float] = None
    total_model_mae: Optional[float] = None
    total_baseline_rmse: Optional[float] = None
    total_baseline_mae: Optional[float] = None
    n_train_full: int = 0  # 4 차원 모두 채워진 train 일자
    n_test_full: int = 0


# ─────────────────────────────────────────────────────────
# Time-based holdout split
# ─────────────────────────────────────────────────────────
def split_time_holdout(
    df: pd.DataFrame,
    holdout_days: int = DEFAULT_HOLDOUT_DAYS,
    date_col: str = "date",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """시간 기반 holdout 분리. 마지막 N일을 test로.

    회원별로 분리하지 않음 — 본 회원 단일 시계열 환경.
    """
    df_sorted = df.sort_values(date_col).reset_index(drop=True)
    if len(df_sorted) < 2 * holdout_days:
        return df_sorted, df_sorted.iloc[0:0].copy()
    return (
        df_sorted.iloc[:-holdout_days].reset_index(drop=True),
        df_sorted.iloc[-holdout_days:].reset_index(drop=True),
    )


# ─────────────────────────────────────────────────────────
# 차원별 학습·평가
# ─────────────────────────────────────────────────────────
def train_dim_model(
    df_train: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    iterations: int = 500,
    depth: int = 6,
    learning_rate: float = 0.05,
    random_seed: int = 0,
) -> Optional["CatBoostRegressor"]:
    """차원별 CatBoost 학습. target NaN 행은 학습에서 자동 제외.

    데이터 14일 미만이면 None 반환 (학습 부족).
    """
    if CatBoostRegressor is None:
        raise RuntimeError("catboost 모듈이 설치되지 않았습니다. 컨테이너 환경에서 실행하세요.")

    valid = df_train.dropna(subset=[target_col])
    if len(valid) < 14:
        return None

    X = valid[feature_cols]  # CatBoost가 NaN 자체 처리
    y = valid[target_col].astype(float)

    model = CatBoostRegressor(
        iterations=iterations,
        depth=depth,
        learning_rate=learning_rate,
        silent=True,
        random_seed=random_seed,
    )
    model.fit(X, y)
    return model


def evaluate_dim(
    model: Optional["CatBoostRegressor"],
    df_test: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
) -> Dict[str, Optional[float]]:
    """차원별 holdout RMSE/MAE."""
    valid = df_test.dropna(subset=[target_col])
    if len(valid) == 0 or model is None:
        return {"rmse": None, "mae": None, "n": 0,
                "y_pred": None, "y_true": None}

    X = valid[feature_cols]
    y = valid[target_col].astype(float).values
    y_pred = np.asarray(model.predict(X), dtype=float)
    rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y - y_pred)))
    return {"rmse": rmse, "mae": mae, "n": len(valid),
            "y_pred": y_pred, "y_true": y}


def naive_baseline_eval(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    target_col: str,
) -> Dict[str, Optional[float]]:
    """naive baseline = train의 target 평균. test에 그대로 예측해 RMSE/MAE."""
    train_valid = df_train.dropna(subset=[target_col])
    test_valid = df_test.dropna(subset=[target_col])
    if len(train_valid) == 0 or len(test_valid) == 0:
        return {"rmse": None, "mae": None, "n": 0,
                "y_pred": None, "y_true": None}

    baseline = float(train_valid[target_col].mean())
    y = test_valid[target_col].astype(float).values
    y_pred = np.full_like(y, baseline, dtype=float)
    rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y - y_pred)))
    return {"rmse": rmse, "mae": mae, "n": len(test_valid),
            "y_pred": y_pred, "y_true": y, "baseline": baseline}


# ─────────────────────────────────────────────────────────
# 통합 학습·평가
# ─────────────────────────────────────────────────────────
def train_eval_psqi_4dim(
    df: pd.DataFrame,
    feature_cols: List[str],
    dims: List[str] = None,
    holdout_days: int = DEFAULT_HOLDOUT_DAYS,
    iterations: int = 500,
) -> PSQIResults:
    """4 차원 학습·평가 + 합산 점수 평가.

    합산은 *4 차원 모두 채워진* 일자만 대상.
    """
    if dims is None:
        dims = list(PSQI_DIMS)

    df_train, df_test = split_time_holdout(df, holdout_days=holdout_days)
    results = PSQIResults()

    # 차원별 학습·평가
    dim_models: Dict[str, "CatBoostRegressor"] = {}
    for dim in dims:
        model = train_dim_model(df_train, feature_cols, dim, iterations=iterations)
        if model is not None:
            dim_models[dim] = model
        m_eval = evaluate_dim(model, df_test, feature_cols, dim)
        b_eval = naive_baseline_eval(df_train, df_test, dim)
        results.by_dim[dim] = DimEval(
            dim=dim,
            n_train=df_train[dim].notna().sum(),
            n_test=m_eval["n"],
            model_rmse=m_eval["rmse"],
            model_mae=m_eval["mae"],
            baseline_rmse=b_eval["rmse"],
            baseline_mae=b_eval["mae"],
            y_pred=m_eval.get("y_pred"),
            y_true=m_eval.get("y_true"),
        )

    # 합산 점수 — 4 차원 모두 채워진 일자만
    full_train = df_train.dropna(subset=dims)
    full_test = df_test.dropna(subset=dims)
    results.n_train_full = len(full_train)
    results.n_test_full = len(full_test)

    if len(full_test) > 0 and len(dim_models) == len(dims):
        # 모델 합산 예측 = 4 차원 예측의 합
        X_test = full_test[feature_cols]
        y_pred_total = np.zeros(len(full_test), dtype=float)
        for dim in dims:
            y_pred_total += np.asarray(dim_models[dim].predict(X_test), dtype=float)
        y_true_total = full_test[dims].sum(axis=1).astype(float).values

        results.total_model_rmse = float(np.sqrt(np.mean((y_true_total - y_pred_total) ** 2)))
        results.total_model_mae = float(np.mean(np.abs(y_true_total - y_pred_total)))

        # baseline 합산 = train 평균의 합
        baseline_total = float(full_train[dims].sum(axis=1).mean())
        y_pred_base = np.full_like(y_true_total, baseline_total, dtype=float)
        results.total_baseline_rmse = float(np.sqrt(np.mean((y_true_total - y_pred_base) ** 2)))
        results.total_baseline_mae = float(np.mean(np.abs(y_true_total - y_pred_base)))

    return results, dim_models


# ─────────────────────────────────────────────────────────
# 결과 요약 — 표 + PASS/FAIL
# ─────────────────────────────────────────────────────────
def summarize_results(results: PSQIResults) -> str:
    """결과를 사람이 읽을 수 있는 표 형태로 포맷."""
    lines = []
    lines.append("=" * 78)
    lines.append("PSQI 4 차원 학습·평가 결과 (검증 게이트 #1)")
    lines.append("=" * 78)
    lines.append(f"{'차원':<18s} {'n_train':>8s} {'n_test':>7s} "
                 f"{'model_RMSE':>11s} {'base_RMSE':>10s} {'beats?':>8s}")
    lines.append("-" * 78)
    n_pass_dims = 0
    for dim_name, ev in results.by_dim.items():
        m_rmse = f"{ev.model_rmse:.4f}" if ev.model_rmse is not None else "  N/A "
        b_rmse = f"{ev.baseline_rmse:.4f}" if ev.baseline_rmse is not None else "  N/A "
        beats = "✅" if ev.beats_baseline else ("❌" if ev.beats_baseline is False else "—")
        if ev.beats_baseline:
            n_pass_dims += 1
        lines.append(f"{dim_name:<18s} {ev.n_train:>8d} {ev.n_test:>7d} "
                     f"{m_rmse:>11s} {b_rmse:>10s} {beats:>8s}")
    lines.append("-" * 78)

    # 합산
    if results.total_model_rmse is not None:
        m_rmse = f"{results.total_model_rmse:.4f}"
        b_rmse = f"{results.total_baseline_rmse:.4f}"
        total_beats = (results.total_model_rmse < results.total_baseline_rmse)
        beats_str = "✅" if total_beats else "❌"
        lines.append(f"{'score_total':<18s} {results.n_train_full:>8d} "
                     f"{results.n_test_full:>7d} {m_rmse:>11s} {b_rmse:>10s} {beats_str:>8s}")
    else:
        lines.append(f"{'score_total':<18s} (4 차원 결측으로 합산 불가)")
        total_beats = False

    lines.append("=" * 78)

    # PASS/FAIL 판정
    n_dims = len(results.by_dim)
    all_dims_pass = (n_pass_dims == n_dims)
    gate_pass = all_dims_pass and total_beats
    verdict = "✅ PASS" if gate_pass else "❌ FAIL"

    lines.append(f"검증 게이트 #1: {verdict}")
    lines.append(f"  - 차원별 baseline 이김: {n_pass_dims} / {n_dims}")
    lines.append(f"  - 합산 baseline 이김:   {'예' if total_beats else '아니오'}")

    if not gate_pass:
        lines.append("")
        lines.append("⚠️  실패 원인 후속 액션:")
        if not all_dims_pass:
            lines.append("  - 일부 차원이 baseline 미달 → features 보강 또는 multi-output 검토")
        if not total_beats:
            lines.append("  - 합산 점수가 단순 평균과 비슷 → 4 차원이 서로 비독립일 가능성")

    lines.append("=" * 78)
    return "\n".join(lines)
