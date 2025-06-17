# -*- coding: utf-8 -*-
# ai_service/sleep_coach_full_kr_v6.py
from __future__ import annotations
import re, textwrap, warnings, datetime
from pathlib import Path
import logging

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
import shap
from llama_cpp import Llama
from token_log import log          # ➊ 새로 import

from db_utils import read_table

warnings.filterwarnings("ignore", category=FutureWarning)
logger = logging.getLogger(__name__)

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
def read_feedback_db(uid: str) -> pd.DataFrame:
    try:
        df = read_table(f"{uid}_feedback", where=f"user_id = '{uid}'")
        print("[DEBUG] feedback DB 읽기 성공")
    except Exception as e:  # UndefinedTable 등
        logger.warning(f"{uid}_feedback 없음 → 빈 DF 사용 ({e})")
        return pd.DataFrame(columns=["user_id", "date", "sleep_score"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.groupby(["user_id", "date"], as_index=False)["sleep_score"].mean()

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
        
        read_feedback_db(uid),   # <─ feedback 컬럼 포함

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

# ── 새 함수 ─────────────────────────────────────────────
def get_last_feedback(uid: str) -> str | None:
    try:
        df = read_table(
            "predictions",
            where=f"uid = '{uid}' ORDER BY created_at DESC LIMIT 1"
        )
        if not df.empty and df.iloc[0]["message"]:
            return str(df.iloc[0]["message"])
    except Exception as e:
        logger.warning(f"get_last_feedback 실패: {e}")
    return None



# ── 모드 안전 헬퍼 ──
def _safe_mode(series: pd.Series, default: datetime.time) -> datetime.time:
    series = series.dropna()
    return series.mode().iat[0] if not series.empty else default

# ── LLM 프롬프트 템플릿 ──
SYS_PROMPT = textwrap.dedent("""\
당신은 한국어 수면·활동 코치입니다.
모든 답변은 반드시 "한국어로 작성"해야 하며, "영어를 사용하지 마세요".

[summary] 좋은 점 2개·개선점 2개 (숫자 포함) 4~6문장
[plan] 4줄: 운동(추천 시간대) / 환경 / 생활(취침·기상) / 식단
숫자 옆에 단위·목표차(±) 표기 해줘.
영어 사용 시 한국어로 번역 후 자연스럽게 만든 뒤 답변하세요.
""")

USER_TMPL = textwrap.dedent("""\
다음 데이터를 기반으로 [summary]/[plan]을 한국어로 작성하세요. 영어 사용 금지.
영어 사용 시 한국어로 번역 후 답변하세요.

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
마지막 문장에 반드시 "운동 시작시간: 20:00, 운동 종료시간: 20:30" 포멧으로 추가해주세요.
영어 사용 시 한국어로 번역 후 자연스럽게 만든 뒤 답변하세요.
""")

# ── 코칭 템플릿 ──
FIRST_TMPL = USER_TMPL          # 첫 코칭(=기존)

FOLLOW_TMPL = textwrap.dedent("""\
영어 사용 금지. 영어 사용 시 한국어로 번역 후 답변하세요.
### [지난 코칭 요약]
{prev_msg}

### [이번 주 데이터]  (최근 {n}일)
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

이번 데이터가 "지난 코칭을 잘 지켰는지 여부"를 먼저 한 문장으로 판단하고,
이어서는 [summary]/[plan] 형식으로 ‘구체적 개선점’을 제시하세요.

마지막 문장에 반드시 "운동 시작시간: 20:00, 운동 종료시간: 20:30" 포멧으로 추가해주세요
영어 사용 시 한국어로 번역 후 자연스럽게 만든 뒤 답변하세요.
""")




# ── vLLM(OpenAI 호환) HTTP 호출 버전 ──
from openai import OpenAI      # ① 새 클라이언트 객체 사용

client = OpenAI(
    base_url="http://172.28.8.101:8282/v1",   # ② vLLM 서버 주소
    api_key="token-abc123",                   # ③ 임의 토큰 – 서버와 일치
)


# def chat(sys: str, user: str) -> str:
#     resp = client.chat.completions.create(
#         model="./llama3",                     # served_model_name
#         temperature=0.3,
#         top_p=0.30,
#         max_tokens=1024,
#         messages=[
#             {"role": "system", "content": sys},
#             {"role": "user",   "content": user},
#         ],
#     )
#     return resp.choices[0].message.content

def chat(uid: str, sys: str, user: str) -> tuple[str, int, int]:
    """content, prompt_tokens, completion_tokens 반환"""
    resp = client.chat.completions.create(
        model="./llama3",
        temperature=0.3,
        top_p=0.30,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user",   "content": user},
        ],
    )

    content = resp.choices[0].message.content
    # vLLM-OpenAI 서버는 usage 필드를 제공합니다.
    p_tok = resp.usage.prompt_tokens
    c_tok = resp.usage.completion_tokens

    # ➋ 콘솔 + CSV/DB 로깅
    print(f"[TOKENS] {uid} | prompt={p_tok} | completion={c_tok}")
    log(uid, p_tok, c_tok)

    return content, p_tok, c_tok



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


    prev_msg = get_last_feedback(uid)
    tmpl = FOLLOW_TMPL if prev_msg else FIRST_TMPL


    prompt = tmpl.format(
        prev_msg=prev_msg or "",
        n=len(recent),
        table=recent.iloc[:, :12].to_string(index=False),
        change=change,
        low_hr=low_hr, high_hr=high_hr,
        avg_sleep=str(avg_sleep)[:-3], avg_wake=str(avg_wake)[:-3],
        pred=pred, k=len(shap_k),
        shap_lines="\n".join(f"{f} | {v:.1f} | {imp:+.2f}" for f,v,imp in shap_k)
    )

    # message = chat(SYS_PROMPT, prompt)
    message, p_tok, c_tok = chat(uid, SYS_PROMPT, prompt)
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
