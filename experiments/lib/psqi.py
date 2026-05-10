"""Phase A.3 — PSQI 4 차원 점수화 함수.

피츠버그 수면 질 지수(PSQI)의 *임상 척도*를 따라 일별 데이터를 4 차원 0~3 점수로 매핑.
합산은 0~12, *낮을수록* 수면 질 높음.

| 차원 | 입력 데이터               | 0점       | 1점       | 2점       | 3점     |
|------|------------------------|-----------|-----------|-----------|--------|
| C1   | feedback.sleep_score    | 0(최고)   | 1(잘잤어) | 2(못잤어) | 3(최악)|
| C2   | sleep_detail의 잠복기   | <16분    | 16~30분  | 31~60분   | >60분 |
| C3   | minutes_asleep         | >7시간   | 6~7시간 | 5~6시간   | <5시간|
| C4   | efficiency (%)         | >85%     | 75~84%   | 65~74%    | <65%  |

C2 잠복기는 *침대에 누운 시각*을 fitbit이 정확히 주지 못해 근사값 — sleep_detail의
*첫 wake 구간 누적*을 잠복기로 근사. 한계는 plan §2.2에 명시.

C1은 feedback.sleep_score가 *4단계(0~3)*임을 가정. Phase A.1 선결.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


# ─────────────────────────────────────────────────────────
# 차원별 점수 매핑 함수 (벡터화 가능한 형태)
# ─────────────────────────────────────────────────────────
def score_c1_subjective(sleep_score: pd.Series) -> pd.Series:
    """C1 주관적 수면 질 — feedback.sleep_score(0~3)를 그대로 PSQI 점수로 사용.

    가정: Phase A.1로 sleep_score가 4단계(0=최고~3=최악)로 통일됨.
    *학습 제외 정책 (옵션 A)*은 호출자 책임 — 본 함수는 0~3 입력만 가정.
    """
    s = pd.to_numeric(sleep_score, errors="coerce")
    return s.where((s >= 0) & (s <= 3))


def score_c3_duration(minutes_asleep: pd.Series) -> pd.Series:
    """C3 수면 시간 — 분 단위 입력을 시간으로 환산해 0~3 점수 매핑."""
    hours = pd.to_numeric(minutes_asleep, errors="coerce") / 60.0
    out = pd.Series(index=hours.index, dtype="float64")
    out[hours > 7] = 0
    out[(hours > 6) & (hours <= 7)] = 1
    out[(hours > 5) & (hours <= 6)] = 2
    out[hours <= 5] = 3
    out[hours.isna()] = pd.NA
    return out


def score_c4_efficiency(efficiency_pct: pd.Series) -> pd.Series:
    """C4 습관적 수면 효율 — 0~100 percentage 입력으로 0~3 점수 매핑."""
    eff = pd.to_numeric(efficiency_pct, errors="coerce")
    out = pd.Series(index=eff.index, dtype="float64")
    out[eff > 85] = 0
    out[(eff >= 75) & (eff <= 85)] = 1
    out[(eff >= 65) & (eff < 75)] = 2
    out[eff < 65] = 3
    out[eff.isna()] = pd.NA
    return out


def score_c2_latency(latency_minutes: pd.Series) -> pd.Series:
    """C2 수면 잠복기 — 잠드는 데 걸린 분을 0~3 점수로 매핑."""
    lat = pd.to_numeric(latency_minutes, errors="coerce")
    out = pd.Series(index=lat.index, dtype="float64")
    out[lat < 16] = 0
    out[(lat >= 16) & (lat <= 30)] = 1
    out[(lat >= 31) & (lat <= 60)] = 2
    out[lat > 60] = 3
    out[lat.isna()] = pd.NA
    return out


# ─────────────────────────────────────────────────────────
# 잠복기 산출 — bedtime_log 우선 + sleep_detail wake 누적 fallback
# ─────────────────────────────────────────────────────────
def estimate_latency_minutes(
    sleep_detail: pd.DataFrame,
    bedtime_log: Optional[pd.DataFrame] = None,
    max_lookback_hours: float = 24.0,
) -> pd.DataFrame:
    """잠복기 분 단위 산출. *회원 측 입력*이 있으면 우선, 없으면 fitbit 근사 fallback.

    Phase A.4 보강: PSQI C2의 measurement floor effect를 풀기 위해 회원이 직접
    입력한 침대 시각(bedtime_log)을 잠복기 산출의 1순위 출처로 사용.

    우선순위:
        1. bedtime_log — user_id가 같고 *첫 비-wake 시각 직전 max_lookback_hours 이내*에
           박제된 가장 늦은 row가 있으면 latency = 첫 비-wake 시각 - bedtime_at
        2. fallback — sleep_detail의 *첫 wake 단계 누적*을 잠복기로 근사

    Args:
        sleep_detail: (user_id, date, time, stage, duration) — duration 초 단위
        bedtime_log:  (user_id, bedtime_at) 또는 None
        max_lookback_hours: bedtime_at이 sleep onset 직전 몇 시간까지 유효한지

    Returns:
        DataFrame (user_id, date, latency_minutes, latency_source)
        latency_source: 'user_input' 또는 'fitbit_wake'
    """
    if sleep_detail.empty:
        return pd.DataFrame(columns=["user_id", "date", "latency_minutes", "latency_source"])

    df = sleep_detail.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["stage_lower"] = df["stage"].astype(str).str.lower()
    # 시각 파싱 — sub-second·milli 자르고 'YYYY-MM-DD HH:MM:SS'로
    time_clean = df["time"].astype(str).str.split(".").str[0]
    df["start"] = pd.to_datetime(
        df["date"].astype(str) + " " + time_clean,
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )

    # bedtime_log 정규화 (있으면)
    bt = None
    if bedtime_log is not None and not bedtime_log.empty:
        bt = bedtime_log.copy()
        bt["bedtime_at"] = pd.to_datetime(bt["bedtime_at"], errors="coerce", utc=True)
        # tz-aware → naive (sleep_detail의 start가 naive라 일관성)
        bt["bedtime_at"] = bt["bedtime_at"].dt.tz_localize(None)
        bt = bt.dropna(subset=["bedtime_at"])

    rows = []
    grouped = df.sort_values(["user_id", "date", "start"]).groupby(["user_id", "date"])
    for (uid, sleep_date), group in grouped:
        g = group.sort_values("start")

        # fallback: 그 밤 첫 wake 누적
        wake_cum = 0.0
        for _, row in g.iterrows():
            if row["stage_lower"] == "wake":
                wake_cum += float(row["duration"]) / 60.0
            else:
                break

        # 첫 비-wake 시각 = sleep onset
        non_wake = g[g["stage_lower"] != "wake"]
        sleep_onset = non_wake["start"].iloc[0] if not non_wake.empty else None

        # bedtime_log 매칭 시도
        latency_user = None
        if bt is not None and sleep_onset is not None:
            user_bt = bt[bt["user_id"] == uid]
            if not user_bt.empty:
                window_start = sleep_onset - pd.Timedelta(hours=max_lookback_hours)
                in_window = user_bt[
                    (user_bt["bedtime_at"] >= window_start)
                    & (user_bt["bedtime_at"] <= sleep_onset)
                ]
                if not in_window.empty:
                    latest = in_window["bedtime_at"].max()
                    latency_user = (sleep_onset - latest).total_seconds() / 60.0

        if latency_user is not None and latency_user >= 0:
            rows.append({
                "user_id": uid,
                "date": sleep_date,
                "latency_minutes": float(latency_user),
                "latency_source": "user_input",
            })
        else:
            rows.append({
                "user_id": uid,
                "date": sleep_date,
                "latency_minutes": float(wake_cum),
                "latency_source": "fitbit_wake",
            })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────
# 메인 — 4 차원 점수 통합
# ─────────────────────────────────────────────────────────
def compute_psqi_scores(
    daily: pd.DataFrame,
    feedback: Optional[pd.DataFrame] = None,
    sleep_detail: Optional[pd.DataFrame] = None,
    bedtime_log: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """일별 PSQI 4 차원 점수 + 합산 산출.

    Args:
        daily: sleep_summary 형태. 필수 컬럼 = (user_id, date, minutes_asleep, efficiency)
        feedback: sleep_score 형태 (4단계, 0~3). 컬럼 = (user_id, date, sleep_score).
            None이면 C1 = NaN.
        sleep_detail: stage·duration 형태. 컬럼 = (user_id, date, time, stage, duration).
            None이면 C2 = NaN.
        bedtime_log: 회원이 직접 입력한 침대 누운 시각. 컬럼 = (user_id, bedtime_at).
            Phase A.4의 보강 — 있으면 C2 잠복기 산출의 1순위 출처. 없으면 sleep_detail
            wake 누적 fallback.

    Returns:
        DataFrame with columns:
            user_id, date,
            c1_subjective, c2_latency, c3_duration, c4_efficiency,
            score_total,
            latency_source  # 'user_input' / 'fitbit_wake' — 진단용
        score_total은 4 차원 모두 NaN이 아닐 때만 계산. *낮을수록* 수면 질 높음.
    """
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    base_cols = ["user_id", "date"]
    out = df[base_cols].drop_duplicates().reset_index(drop=True)

    # C3 / C4 — daily에서 직접
    out = out.merge(
        df[base_cols + ["minutes_asleep", "efficiency"]],
        on=base_cols,
        how="left",
    )
    out["c3_duration"] = score_c3_duration(out["minutes_asleep"])
    out["c4_efficiency"] = score_c4_efficiency(out["efficiency"])

    # C1 — feedback에서
    if feedback is not None and not feedback.empty:
        fb = feedback.copy()
        fb["date"] = pd.to_datetime(fb["date"]).dt.date
        fb["c1_subjective"] = score_c1_subjective(fb["sleep_score"])
        out = out.merge(
            fb[base_cols + ["c1_subjective"]],
            on=base_cols,
            how="left",
        )
    else:
        out["c1_subjective"] = pd.NA

    # C2 — bedtime_log 우선 + sleep_detail wake 누적 fallback (Phase A.4)
    if sleep_detail is not None and not sleep_detail.empty:
        latency = estimate_latency_minutes(sleep_detail, bedtime_log=bedtime_log)
        latency["c2_latency"] = score_c2_latency(latency["latency_minutes"])
        out = out.merge(
            latency[base_cols + ["c2_latency", "latency_source"]],
            on=base_cols,
            how="left",
        )
    else:
        out["c2_latency"] = pd.NA
        out["latency_source"] = pd.NA

    # 합산 — 4 차원 모두 채워진 일자만
    score_cols = ["c1_subjective", "c2_latency", "c3_duration", "c4_efficiency"]
    all_filled = out[score_cols].notna().all(axis=1)
    out["score_total"] = out[score_cols].sum(axis=1).where(all_filled)

    return out[base_cols + score_cols + ["score_total", "latency_source"]]


# ─────────────────────────────────────────────────────────
# CLI 검증 — 회원 23RK3S 데이터로 분포 점검
# ─────────────────────────────────────────────────────────
def _main() -> None:
    """`python -m experiments.lib.psqi`로 호출해 회원 23RK3S의 PSQI 점수 분포 출력."""
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = repo_root / "JG-Data"

    daily_csv = data_dir / "sleep_summary.csv"
    fb_csv = repo_root / "db" / "init" / "feedback_sleep.csv"
    detail_csv = data_dir / "sleep_detail.csv"

    if not daily_csv.exists():
        print(f"[skip] sleep_summary.csv not found at {daily_csv}")
        return

    print(f"[load] {daily_csv}")
    daily = pd.read_csv(daily_csv)
    feedback = pd.read_csv(fb_csv) if fb_csv.exists() else None
    sleep_detail = pd.read_csv(detail_csv) if detail_csv.exists() else None

    if feedback is not None:
        # 일자 형식이 1/1/24 → 2024-01-01로 정규화 필요
        feedback["date"] = pd.to_datetime(feedback["date"]).dt.strftime("%Y-%m-%d")

    out = compute_psqi_scores(daily, feedback=feedback, sleep_detail=sleep_detail)

    n_total = len(out)
    print(f"\n[summary] 4 차원 점수 분포")
    print(f"  - 전체 일자 수            : {n_total}")
    for col in ["c1_subjective", "c2_latency", "c3_duration", "c4_efficiency", "score_total"]:
        s = out[col].dropna()
        if len(s) == 0:
            print(f"  - {col:18s} : 결측 (입력 데이터 부재)")
            continue
        print(f"  - {col:18s} : n={len(s):4d}  mean={s.mean():.2f}  median={s.median():.1f}  range=[{s.min():.0f}, {s.max():.0f}]")

    # 차원별 결측률 — Phase A.1 옵션 A의 영향 확인
    print(f"\n[결측률] (옵션 A로 학습에서 제외될 일자 비율)")
    for col in ["c1_subjective", "c2_latency", "c3_duration", "c4_efficiency"]:
        miss = out[col].isna().sum()
        print(f"  - {col:18s} : {miss:4d} / {n_total} ({miss/n_total*100:.1f}%)")

    # 합산 점수가 *모든 4 차원이 채워진* 일자 수
    n_full = out["score_total"].notna().sum()
    print(f"\n[학습 가능 일자] (4 차원 모두 있는 일자) = {n_full} / {n_total} ({n_full/n_total*100:.1f}%)")


if __name__ == "__main__":
    _main()
