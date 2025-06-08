# -*- coding: utf-8 -*-
"""
sleep_coach_full_kr_v6.py  (DB)

CSV 대신 DB에서 직접 데이터를 조회하여 마스터 DF를 구성하고, CatBoost & SHAP로 수면 효율을 예측한 뒤
Mistral-7B 모델을 사용해 한국어 코칭 메시지를 생성합니다.
"""

from __future__ import annotations
from pathlib import Path
import re, textwrap, warnings, argparse
import pandas as pd, numpy as np
from catboost import CatBoostRegressor
import shap
from llama_cpp import Llama

from db_utils import read_table  # DB에서 테이블을 읽어오는 유틸

warnings.filterwarnings("ignore", category=FutureWarning)

KEYS = ["user_id"]
TARGET, EXCL = "efficiency", ["user_id"]
TIME_ONLY = re.compile(r"\d{1,2}:\d{2}:\d{2}\s*(AM|PM|am|pm)?$")


def _combine_dt(df: pd.DataFrame, dcol="date", tcol="time") -> pd.DatetimeIndex:
    """
    날짜 열(dcol)과 시간 열(tcol)을 합쳐서 datetime으로 변환합니다.
    """
    date_str = pd.to_datetime(df[dcol], errors="coerce").dt.strftime("%Y-%m-%d")

    def clean(t):
        s = str(t).strip()
        if TIME_ONLY.match(s):
            return s
        return s[-8:] if len(s) >= 8 else "00:00:00"

    time_str = df[tcol].apply(clean)
    return pd.to_datetime(
        date_str + " " + time_str,
        errors="coerce"
    )


# ────────────────── daily reader ──────────────────
def read_daily_db(table: str, agg: dict[str, str], uid: str) -> pd.DataFrame:
    """
    지정된 테이블에서 user_id 기준으로 daily 집계 데이터프레임을 반환합니다.
    """
    df = read_table(table, where=f"user_id = '{uid}'")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.groupby(KEYS + ["date"], as_index=False).agg(agg)


# ────────────────── minute reader ──────────────────
def read_minute_db(
    table: str,
    *,
    mean_cols: list[str] | None = None,
    sum_cols: list[str] | None = None,
    uid: str,
) -> pd.DataFrame:
    df = read_table(table, where=f"user_id = '{uid}'")
    df["timestamp"] = _combine_dt(df)
    df["date"] = df["timestamp"].dt.normalize()

    agg: dict[str, str] = {}
    if mean_cols:
        agg.update({c: "mean" for c in mean_cols})
    if sum_cols:
        agg.update({c: "sum" for c in sum_cols})

    return df.groupby(KEYS + ["date"]).agg(agg).reset_index()


def read_activity_hourly_db(table: str, uid: str) -> pd.DataFrame:
    df = read_table(table, where=f"user_id = '{uid}'")
    df["timestamp"] = _combine_dt(df)
    df["date"] = df["timestamp"].dt.normalize()
    df["hour"] = df["timestamp"].dt.hour
    return (
        df.groupby(KEYS + ["date", "hour"], as_index=False)["steps"]
          .sum()
          .rename(columns={"steps": "steps_hour_sum"})
    )


def read_sleep_detail_stage_db(table: str, uid: str) -> pd.DataFrame:
    df = read_table(table, where=f"user_id = '{uid}'")
    df["start"] = _combine_dt(df, dcol="date", tcol="time")
    df["date"] = df["start"].dt.normalize()
    df["duration_min"] = df["duration"] / 60
    return (
        df.groupby(KEYS + ["date", "stage"], as_index=False)["duration_min"]
          .sum()
          .pivot(index=KEYS + ["date"], columns="stage", values="duration_min")
          .reset_index()
          .rename(columns=lambda c: f"stage_{c}_min" if c not in KEYS + ["date"] else c)
    )


def read_sleep_window_db(table: str, uid: str) -> pd.DataFrame:
    df = read_table(table, where=f"user_id = '{uid}'")
    df["start"] = _combine_dt(df, dcol="date", tcol="time")
    df["end"] = df["start"] + pd.to_timedelta(df["duration"], unit="s")
    df["sleep_date"] = df["end"].dt.normalize()

    first = df.groupby(KEYS + ["sleep_date"], as_index=False)["start"].min()
    last  = df.groupby(KEYS + ["sleep_date"], as_index=False)["end"].max()

    return (
        first.merge(last, on=KEYS + ["sleep_date"])
             .rename(columns={"sleep_date": "date",
                              "start": "sleep_time",
                              "end":   "wake_time"})
    )


# ────────────────── master DF ──────────────────
def build_master(uid: str) -> pd.DataFrame:
    daily = [
        read_daily_db(
            "23RK3S_sleep_summary",
            {"efficiency": "mean", "stage_deep": "sum",
             "stage_light": "sum", "stage_rem": "sum", "stage_wake": "sum"},
            uid
        ),
        read_daily_db(
            "23RK3S_activity_sum",
            {"steps": "sum", "distance": "sum", "calories": "sum"},
            uid
        ),
        read_daily_db("23RK3S_resting_hr", {"resting_hr": "mean"}, uid),
        read_daily_db("23RK3S_azm", {"total": "sum", "fatburn": "sum", "cardio": "sum"}, uid),
    ]
    minute = [
        read_minute_db("23RK3S_heart_rate_1min", mean_cols=["bpm"], uid=uid),
        read_minute_db("23RK3S_activity_1min", sum_cols=["steps", "distance", "calories"], uid=uid),
        read_minute_db("23RK3S_hrv", mean_cols=["rmssd", "hf", "lf"], uid=uid),
        read_sleep_detail_stage_db("23RK3S_sleep_detail", uid),
    ]

    master = daily[0]
    for d in daily[1:] + minute:
        master = master.merge(d, on=KEYS + ["date"], how="outer")

    return master.sort_values("date").fillna(method="ffill")


# ────────────────── ML & SHAP ──────────────────
def add_roll7(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.select_dtypes("number").columns:
        df[f"{c}_roll7"] = df[c].rolling(7, 1).mean()
    return df

def get_X(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.drop(columns=[TARGET] + EXCL, errors="ignore")
          .select_dtypes("number")
          .fillna(method="bfill").fillna(method="ffill")
    )

def train_cat(df: pd.DataFrame) -> CatBoostRegressor:
    model = CatBoostRegressor(iterations=500, depth=6, learning_rate=0.05,
                              silent=True, random_seed=0)
    model.fit(get_X(df), df[TARGET])
    return model

def shap_top(model: CatBoostRegressor, X: pd.DataFrame, k: int = 6) -> list[tuple[str, float, float]]:
    vals = shap.TreeExplainer(model).shap_values(X)[-1]
    idx  = np.abs(vals).argsort()[::-1][:k]
    return [(X.columns[i], float(X.iloc[-1, i]), float(vals[i])) for i in idx]


# ────────────────── 프롬프트 ──────────────────
SYS_PROMPT = textwrap.dedent("""
당신은 한국어 수면·활동 코치입니다.
[summary] 좋은 점 2개·개선점 2개 (숫자 포함) 4~6문장
[plan] 4줄: 운동(추천 시간대) / 환경 / 생활(취침·기상) / 식단
숫자 옆에 단위·목표차(±) 표기, '~해보세요' 어조
""")

USER_TMPL = textwrap.dedent("""
### 최근 {n}일 데이터
{table}

### 변화율(7일 vs 이전 7일)
{change}

### 활동 시각대
- 최소: {low_hr}
- 최대: {high_hr}

### 평균 취침·기상
- 취침: {avg_sleep}
- 기상: {avg_wake}

### 예측 효율: {pred:.1f} %

### SHAP TOP {k}
지표 | 현재값 | 영향
{shap_lines}

위 정보를 바탕으로 [summary]/[plan] 작성하세요.
""")


def chat(model_path: Path, sys: str, user: str) -> str:
    llm = Llama(model_path=str(model_path), n_ctx=4096,
                temperature=0.9, top_p=0.95, n_gpu_layers=0)
    res = llm.create_chat_completion(
        messages=[{"role": "user", "content": f"{sys}\n\n{user}"}]
    )
    return res["choices"][0]["message"]["content"].strip()


# ────────────────── main ──────────────────
def main(uid: str, model_path: Path, window: int):
    master = add_roll7(build_master(uid))
    cat     = train_cat(master)
    X       = get_X(master)

    pred    = float(cat.predict(X.tail(1))[0])
    shap_k  = shap_top(cat, X)
    recent  = master.tail(window)

    act_hr = read_activity_hourly_db("23RK3S_activity_1min", uid)
    low_hr  = f"{int(act_hr.groupby('hour')['steps_hour_sum'].mean().idxmin()):02d}:00"
    high_hr = f"{int(act_hr.groupby('hour')['steps_hour_sum'].mean().idxmax()):02d}:00"

    swin = read_sleep_window_db("23RK3S_sleep_detail", uid)
    avg_sleep = swin["sleep_time"].dt.time.mode()[0] if not swin.empty else "23:00"
    avg_wake  = swin["wake_time"].dt.time.mode()[0] if not swin.empty else "07:00"

    prev   = master.iloc[-2 * window : -window]
    change = []
    for col in ["steps", "total", TARGET]:
        if col in recent and col in prev and prev[col].mean() != 0:
            pct = (recent[col].mean() - prev[col].mean()) / prev[col].mean() * 100
            change.append(f"{col}:{pct:+.1f}%")
    change = "; ".join(change)

    prompt = USER_TMPL.format(
        n=len(recent),
        table=recent.iloc[:, :12].to_string(index=False),
        change=change,
        low_hr=low_hr, high_hr=high_hr,
        avg_sleep=str(avg_sleep)[:-3], avg_wake=str(avg_wake)[:-3],
        pred=pred,
        k=len(shap_k),
        shap_lines="\n".join(f"{f} | {v:.1f} | {imp:+.2f}" for f, v, imp in shap_k)
    )

    print("\n=== 한국어 코칭 메시지 ===\n")
    print(chat(model_path, SYS_PROMPT, prompt))


# ────────────────── CLI ──────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sleep-Coach v6 (DB 기반)")
    parser.add_argument("--user", required=True, help="user_id (e.g. 23RK3S)")
    parser.add_argument("--model", required=True, type=Path, help="GGUF model path")
    parser.add_argument("--window", type=int, default=7)
    args = parser.parse_args()
    main(args.user, args.model, args.window)
