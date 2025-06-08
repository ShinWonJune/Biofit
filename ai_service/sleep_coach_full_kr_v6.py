# -*- coding: utf-8 -*-
# ai_service/sleep_coach_full_kr_v6.py
from __future__ import annotations
import re, textwrap, warnings, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
import shap
from llama_cpp import Llama

from db_utils import read_table

warnings.filterwarnings("ignore", category=FutureWarning)

# ── 공통 변수 ──
KEYS   = ["user_id"]
TARGET = "efficiency"

TIME_ONLY = re.compile(r"\d{1,2}:\d{2}:\d{2}$")          # AM/PM 삭제

# ────────────────────────────────────────────────────────
# 날짜·시간 파싱 보강 ― 밀리초·AM/PM 제거 + 고정 포맷
# ────────────────────────────────────────────────────────
def _combine_dt(df: pd.DataFrame, dcol="date", tcol="time") -> pd.DatetimeIndex:
    """date·time 문자열을 안전하게 합쳐 datetime64 반환."""
    date_part = pd.to_datetime(df[dcol], errors="coerce").dt.strftime("%Y-%m-%d")

    def clean_time(cell):
        s = str(cell).strip()
        # 밀리초 제거 ("04:33:30.000" → "04:33:30")
        s = s.split(".")[0]
        # AM/PM 표기 제거
        s = s.replace("AM", "").replace("PM", "").replace("am", "").replace("pm", "").strip()
        if TIME_ONLY.match(s):
            return s
        return "00:00:00"   # 파싱 불가 시 0시 처리

    time_part = df[tcol].apply(clean_time)
    return pd.to_datetime(
        date_part + " " + time_part,
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce"
    )

# ── DB 로 읽어오는 함수들 ──
def read_daily_db(table_suffix: str, agg: dict[str, str], uid: str) -> pd.DataFrame:
    tbl = f"{uid}_{table_suffix}"
    df  = read_table(tbl, where=f"user_id = '{uid}'")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.groupby(KEYS + ["date"], as_index=False).agg(agg)

def read_minute_db(
    table_suffix: str,
    *,
    mean_cols: list[str] | None = None,
    sum_cols:  list[str] | None = None,
    uid: str
) -> pd.DataFrame:
    tbl = f"{uid}_{table_suffix}"
    df  = read_table(tbl, where=f"user_id = '{uid}'")
    df["timestamp"] = _combine_dt(df)
    df["date"]      = df["timestamp"].dt.normalize()

    agg: dict[str, str] = {}
    if mean_cols:
        agg.update({c: "mean" for c in mean_cols})
    if sum_cols:
        agg.update({c: "sum"  for c in sum_cols})

    return df.groupby(KEYS + ["date"], as_index=False).agg(agg)

def read_activity_hourly_db(table_suffix: str, uid: str) -> pd.DataFrame:
    tbl = f"{uid}_{table_suffix}"
    df  = read_table(tbl, where=f"user_id = '{uid}'")
    df["timestamp"] = _combine_dt(df)
    df["hour"]      = df["timestamp"].dt.hour
    return (
        df.groupby(KEYS + ["hour"], as_index=False)["steps"]
          .sum()
          .rename(columns={"steps": "steps_hour_sum"})
    )

def read_sleep_detail_stage_db(table_suffix: str, uid: str) -> pd.DataFrame:
    tbl = f"{uid}_{table_suffix}"
    df  = read_table(tbl, where=f"user_id = '{uid}'")
    df["start"]        = _combine_dt(df, dcol="date", tcol="time")
    df["date"]         = df["start"].dt.normalize()
    df["duration_min"] = df["duration"] / 60
    pivot = (
        df.groupby(KEYS + ["date", "stage"], as_index=False)["duration_min"]
          .sum()
          .pivot(index=KEYS + ["date"], columns="stage", values="duration_min")
          .reset_index()
    )
    pivot.columns = [
        f"stage_{c}_min" if c not in KEYS + ["date"] else c
        for c in pivot.columns
    ]
    return pivot

def read_sleep_window_db(table_suffix: str, uid: str) -> pd.DataFrame:
    tbl = f"{uid}_{table_suffix}"
    df  = read_table(tbl, where=f"user_id = '{uid}'")
    df["start"] = _combine_dt(df, dcol="date", tcol="time")
    df["end"]   = df["start"] + pd.to_timedelta(df["duration"], unit="s")
    df["sleep_date"] = df["end"].dt.normalize()

    first = df.groupby(KEYS + ["sleep_date"], as_index=False)["start"].min()
    last  = df.groupby(KEYS + ["sleep_date"], as_index=False)["end"].max()

    merged = first.merge(last, on=KEYS + ["sleep_date"])
    return merged.rename(columns={
        "sleep_date": "date",
        "start": "sleep_time",
        "end":   "wake_time"
    })

# ── 마스터 DF 구축 ──
def build_master(uid: str) -> pd.DataFrame:
    daily = [
        read_daily_db("sleep_summary",
                     {"efficiency": "mean",
                      "stage_deep": "sum",
                      "stage_light":"sum",
                      "stage_rem":  "sum",
                      "stage_wake": "sum"},
                     uid),
        read_daily_db("activity_sum",
                     {"steps":"sum", "distance":"sum", "calories":"sum"},
                     uid),
        read_daily_db("resting_hr", {"resting_hr":"mean"}, uid),
        read_daily_db("azm",        {"total":"sum", "fatburn":"sum", "cardio":"sum"}, uid),
    ]

    minute = [
        read_minute_db("heart_rate_1min", mean_cols=["bpm"], uid=uid),
        read_minute_db("activity_1min",  sum_cols=["steps","distance","calories"], uid=uid),
        read_minute_db("hrv",            mean_cols=["rmssd","hf","lf"], uid=uid),
        read_sleep_detail_stage_db("sleep_detail", uid),
    ]

    master = daily[0]
    for df in daily[1:] + minute:
        master = master.merge(df, on=KEYS + ["date"], how="outer")

    return master.sort_values("date").fillna(method="ffill")

# ── 전처리 & 모델 ──
def add_roll7(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.select_dtypes("number"):
        out[f"{col}_roll7"] = out[col].rolling(window=7, min_periods=1).mean()
    return out

def get_X(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.drop(columns=[TARGET] + KEYS, errors="ignore")
          .select_dtypes("number")
          .fillna(method="bfill").fillna(method="ffill")
    )

def train_cat(df: pd.DataFrame) -> CatBoostRegressor:
    model = CatBoostRegressor(
        iterations=500, depth=6, learning_rate=0.05,
        silent=True, random_seed=0
    )
    model.fit(get_X(df), df[TARGET])
    return model

def shap_top(model, X: pd.DataFrame, k: int = 6):
    vals = shap.TreeExplainer(model).shap_values(X)[-1]
    idx  = np.abs(vals).argsort()[::-1][:k]
    return [(X.columns[i], float(X.iloc[-1, i]), float(vals[i])) for i in idx]

# ── 모드 안전 헬퍼 ──
def _safe_mode(series: pd.Series, default: datetime.time) -> datetime.time:
    series = series.dropna()
    return series.mode().iat[0] if not series.empty else default

# ── LLM 프롬프트 템플릿 ──
SYS_PROMPT = textwrap.dedent("""\
당신은 한국어 수면·활동 코치입니다.
[summary] 좋은 점 2개·개선점 2개 (숫자 포함) 4~6문장
[plan] 4줄: 운동(추천 시간대) / 환경 / 생활(취침·기상) / 식단
숫자 옆에 단위·목표차(±) 표기, '~해보세요' 어조
""")

USER_TMPL = textwrap.dedent("""\
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
    llm = Llama(
        model_path=str(model_path),
        n_ctx=4096,
        temperature=0.9,
        top_p=0.95,
        n_gpu_layers=0
    )
    res = llm.create_chat_completion(
        messages=[{"role": "user", "content": f"{sys}\n\n{user}"}]
    )
    return res["choices"][0]["message"]["content"].strip()

def main(uid: str, model_path: Path, window: int) -> str:   # 반환형 str
    master = add_roll7(build_master(uid))
    cat    = train_cat(master)
    X      = get_X(master)

    pred   = float(cat.predict(X.tail(1))[0])
    shap_k = shap_top(cat, X)
    recent = master.tail(window)

    # 활동 시각대
    act_hr = read_activity_hourly_db("activity_1min", uid)
    low_hr  = f"{int(act_hr.groupby('hour')['steps_hour_sum'].mean().idxmin()):02d}:00"
    high_hr = f"{int(act_hr.groupby('hour')['steps_hour_sum'].mean().idxmax()):02d}:00"

    # 수면/기상 평균 (안전 모드 사용)
    swin = read_sleep_window_db("sleep_detail", uid)
    avg_sleep = _safe_mode(swin["sleep_time"].dt.time, datetime.time(23, 0))
    avg_wake  = _safe_mode(swin["wake_time"].dt.time,  datetime.time(7, 0))

    # 변화율
    prev   = master.iloc[-2 * window:-window]
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
        pred=pred, k=len(shap_k),
        shap_lines="\n".join(f"{f} | {v:.1f} | {imp:+.2f}" for f, v, imp in shap_k)
    )

    message = chat(model_path, SYS_PROMPT, prompt)

    print("\n=== 한국어 코칭 메시지 ===\n")
    print(message)
    return message 


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sleep-Coach DB 버전")
    parser.add_argument("--user",   required=True, help="user_id")
    parser.add_argument("--model",  required=True, type=Path, help="GGUF 모델 경로")
    parser.add_argument("--window", type=int, default=7, help="최근 N일")
    args = parser.parse_args()
    main(args.user, args.model, args.window)
