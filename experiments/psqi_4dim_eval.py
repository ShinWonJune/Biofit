"""Phase B+C — PSQI 4 차원 학습·평가·SHAP 통합 실행 스크립트.

컨테이너 환경에서 1회 실행:
    docker compose run --rm ai_service python /app/experiments/psqi_4dim_eval.py
또는 venv:
    python -m experiments.psqi_4dim_eval

산출물:
    - 콘솔 출력: 4 차원 점수 분포, RMSE 비교 표, PASS/FAIL 판정, 차원별 SHAP top-3
    - experiments/output/psqi_eval_summary.txt
    - experiments/output/psqi_shap_<dim>.png (4개)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# repo root를 sys.path에 추가 (experiments.lib import 가능하게)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.lib import datasets as D  # noqa: E402
from experiments.lib import models as M  # noqa: E402

DATA_DIR = ROOT / "JG-Data"
FEEDBACK_CSV = ROOT / "db" / "init" / "feedback_sleep.csv"
OUT_DIR = ROOT / "experiments" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    print(f"[load] data_dir={DATA_DIR}")
    df = D.build_master_dataset(DATA_DIR, feedback_csv=FEEDBACK_CSV)
    print(f"[load] master rows={len(df)}, columns={len(df.columns)}")

    # ── 4 차원 점수 분포 ──
    print("\n[4 차원 점수 분포]")
    for col in ["c1_subjective", "c2_latency", "c3_duration", "c4_efficiency", "score_total"]:
        s = df[col].dropna()
        if len(s) == 0:
            print(f"  {col:18s} : 결측 (입력 데이터 부재)")
            continue
        print(f"  {col:18s} : n={len(s):4d}  mean={s.mean():.2f}  "
              f"median={s.median():.1f}  range=[{s.min():.0f}, {s.max():.0f}]")

    # ── 결측률 (옵션 A 영향) ──
    print("\n[결측률] (학습에서 제외될 일자 비율)")
    for col in ["c1_subjective", "c2_latency", "c3_duration", "c4_efficiency"]:
        miss = df[col].isna().sum()
        print(f"  {col:18s} : {miss:4d} / {len(df)} ({miss/len(df)*100:.1f}%)")

    # ── Phase B 학습·평가 ──
    print(f"\n[Phase B] 학습 시작 (features {len(D.FEATURE_COLUMNS)}개, holdout 7일)")
    feature_cols = [c for c in D.FEATURE_COLUMNS if c in df.columns]
    results, dim_models = M.train_eval_psqi_4dim(
        df, feature_cols=feature_cols, dims=M.PSQI_DIMS, holdout_days=7,
    )

    summary = M.summarize_results(results)
    print("\n" + summary)

    # 파일로 박제
    summary_path = OUT_DIR / "psqi_eval_summary.txt"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"\n[saved] {summary_path}")

    # ── Phase C SHAP top-3 차원별 ──
    print("\n[Phase C] 차원별 SHAP top-3 변수")
    try:
        import shap
        for dim, model in dim_models.items():
            valid = df.dropna(subset=[dim])
            X = valid[feature_cols]
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            mean_abs = np.abs(shap_values).mean(axis=0)
            top_idx = np.argsort(mean_abs)[::-1][:3]
            top_features = [(feature_cols[i], float(mean_abs[i])) for i in top_idx]
            print(f"  {dim:18s} : " + ", ".join(
                f"{f}({v:.3f})" for f, v in top_features
            ))

            # 시각화 (선택 — matplotlib 가능 시)
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                shap.summary_plot(shap_values, X, plot_type="bar", show=False)
                plt.tight_layout()
                plt.savefig(OUT_DIR / f"psqi_shap_{dim}.png", dpi=80)
                plt.close()
            except Exception as e:
                print(f"    (시각화 실패: {e})")
    except ImportError:
        print("  shap 모듈 부재 — Phase C SHAP 분석 건너뜀")

    # ── 게이트 #1 판정 → exit code ──
    n_pass_dims = sum(1 for ev in results.by_dim.values() if ev.beats_baseline)
    total_pass = (
        results.total_model_rmse is not None
        and results.total_baseline_rmse is not None
        and results.total_model_rmse < results.total_baseline_rmse
    )
    gate_pass = (n_pass_dims == len(results.by_dim)) and total_pass

    print(f"\n[게이트 #1] {'✅ PASS' if gate_pass else '❌ FAIL'}")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
