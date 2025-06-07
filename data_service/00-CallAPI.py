#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-

import os, sys, time, json, requests
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
import pdb;

##########################################################################
# 기본 설정
##########################################################################
CSV_DIR = Path("./fitbit_csv"); CSV_DIR.mkdir(exist_ok=True)
MAX_CALLS_HOUR = 150
SAFETY_MARGIN  = 10            # 140콜에서 자발 휴식
token = os.getenv("FITBIT_TOKEN")
pdb.set_trace()
if not token:
    sys.exit("? FITBIT_TOKEN environment variable not found")
HEADERS = {"Authorization": f"Bearer {token}"}

calls_in_window = 0
window_start    = time.time()

def csv_path(name): return CSV_DIR / f"{name}.csv"
def append_csv(name, row):
    pd.DataFrame([row]).to_csv(csv_path(name),
        mode="a", header=not csv_path(name).exists(),
        index=False, encoding="utf-8")

##########################################################################
# ★ 429 대기 로직이 들어간 요청 함수
##########################################################################
def rate_req(url: str) -> dict:
    """Fitbit API call + 429/limit management + JSON return"""
    global calls_in_window, window_start

    while True:
        # 1) 창 경과 1h → 카운터 리셋
        if time.time() - window_start >= 3600:
            calls_in_window = 0
            window_start = time.time()

        # 2) 남은 여유 확인
        if calls_in_window >= MAX_CALLS_HOUR - SAFETY_MARGIN:
            sleep_sec = 3600 - (time.time() - window_start) + 1
            print(f"[INFO] {calls_in_window} calls exhausted, voluntary wait for {sleep_sec:.0f}s")
            time.sleep(sleep_sec)
            continue  # 다시 루프

        # 3) 호출 시도
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"[WARN] Network error: {e} → Retry after 10s")
            time.sleep(10)
            continue

        # 4) 429 처리 → Retry-After 헤더 사용
        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", "3600"))
            print(f"[RATE] 429 Too Many Requests → Wait {retry}s")
            time.sleep(retry)
            continue  # 같은 URL 재시도

        # 5) 기타 오류는 상위에서 잡도록 raise
        resp.raise_for_status()

        calls_in_window += 1
        return resp.json()  # 정상 종료

def daterange(start: datetime, end: datetime):
    while start <= end:
        yield start
        start += timedelta(days=1)

def iso(d: datetime | str) -> str:
    return d if isinstance(d, str) else d.strftime("%Y-%m-%d")

##########################################################################
# 수집 함수(필요 최소 호출만)
##########################################################################
def get_activity_daily(uid, d):
    # ① 단일 summary 엔드포인트 호출
    js = rate_req(f"https://api.fitbit.com/1/user/-/activities/date/{d}.json")

    summary   = js.get("summary", {})
    steps     = summary.get("steps", 0)
    calories  = summary.get("caloriesOut", 0)

    # Distance: Find activity == "total" in summary["distances"] list
    distances = summary.get("distances", [])
    distance  = next((el["distance"] for el in distances if el["activity"] == "total"), 0)

    append_csv("activity_sum",
               dict(user_id=uid, date=d,
                    steps=steps, distance=distance, calories=calories))


def get_activity_intraday(uid, d, interval):
    base = "https://api.fitbit.com/1/user/-/activities"
    kinds = {"steps":"steps","distance":"distance","calories":"calories"}
    datasets = {}
    for k, path in kinds.items():
        js = rate_req(f"{base}/{path}/date/{d}/1d/{interval}.json")
        key = f"activities-{path}-intraday"
        datasets[k] = {x["time"]: x["value"]
                       for x in js.get(key, {}).get("dataset", [])}
    for t in sorted(set().union(*datasets.values())):
        append_csv(f"activity_{interval}",
                   {"user_id":uid,"date":d,"time":t,
                    "steps":datasets["steps"].get(t,0),
                    "distance":datasets["distance"].get(t,0),
                    "calories":datasets["calories"].get(t,0)})

def get_azm(uid, d):
    js = rate_req(f"https://api.fitbit.com/1/user/-/activities/active-zone-minutes/date/{d}/1d.json")
    items = js.get("activities-active-zone-minutes",[]) or [{"dateTime":d,"value":{}}]
    for it in items:
        v = it.get("value",{})
        append_csv("azm", {"user_id":uid,"date":it["dateTime"],
                           "total":v.get("activeZoneMinutes",0),
                           "fatburn":v.get("fatBurnActiveZoneMinutes",0),
                           "cardio":v.get("cardioActiveZoneMinutes",0)})

def get_sleep(uid, d):
    js = rate_req(f"https://api.fitbit.com/1.2/user/-/sleep/date/{d}.json")

    # summary & efficiency
    summary = js.get("summary", {})
    stages  = summary.get("stages", {})
    sleep_logs = js.get("sleep", [])
    if sleep_logs:
        main_log = max(sleep_logs, key=lambda x: x.get("duration",0))
        eff = main_log.get("efficiency",-1)
        levels = main_log.get("levels",{}).get("summary",{})
        cnts = {lv:levels.get(lv,{}).get("count",-1) for lv in ["deep","light","rem","wake"]}
    else:
        eff, cnts = -1, {lv:-1 for lv in ["deep","light","rem","wake"]}

    append_csv("sleep_summary",
        {"user_id":uid,"date":d,
         "minutes_asleep":summary.get("totalMinutesAsleep",0),
         "time_in_bed":summary.get("totalTimeInBed",0),
         "stage_deep":stages.get("deep",-1),
         "stage_light":stages.get("light",-1),
         "stage_rem":stages.get("rem",-1),
         "stage_wake":stages.get("wake",-1),
         "efficiency":eff,
         **{f"cnt_{k}":v for k,v in cnts.items()}}
    )

    # detail
    for sl in sleep_logs:
        for drow in sl.get("levels",{}).get("data",[]):
            day,tm = drow["dateTime"].split("T")
            append_csv("sleep_detail",
                       {"user_id":uid,"date":day,"time":tm,
                        "stage":drow["level"],"duration":drow["seconds"]})

def get_hr_intraday(uid, d):
    js = rate_req(f"https://api.fitbit.com/1/user/-/activities/heart/date/{d}/1d/1min.json")
    for rec in js.get("activities-heart-intraday",{}).get("dataset",[]):
        append_csv("heart_rate_1min",
                   {"user_id":uid,"date":d,"time":rec["time"],"bpm":rec["value"]})
    if not js.get("activities-heart-intraday"):
        append_csv("heart_rate_1min",{"user_id":uid,"date":d,"time":None,"bpm":-1})

def get_rhr(uid, d):
    js = rate_req(f"https://api.fitbit.com/1/user/-/activities/heart/date/{d}/{d}.json")
    for el in js.get("activities-heart",[]):
        append_csv("resting_hr",
                   {"user_id":uid,"date":el["dateTime"],
                    "resting_hr":el.get("value",{}).get("restingHeartRate",0)})
    if not js.get("activities-heart"):
        append_csv("resting_hr",{"user_id":uid,"date":d,"resting_hr":-1})

def get_hrv(uid, d):
    js = rate_req(f"https://api.fitbit.com/1/user/-/hrv/date/{d}/all.json")
    if not js.get("hrv"):
        append_csv("hrv",{"user_id":uid,"date":d,"time":None,
                          "rmssd":-1,"coverage":-1,"hf":-1,"lf":-1})
    for blk in js.get("hrv",[]):
        for m in blk["minutes"]:
            day,tm = m["minute"].split("T")
            v = m["value"]
            append_csv("hrv",{"user_id":uid,"date":day,"time":tm,
                              "rmssd":v["rmssd"],"coverage":v["coverage"],
                              "hf":v["hf"],"lf":v["lf"]})

##########################################################################
# 메인 루프
##########################################################################
def main():
    if len(sys.argv) != 4:
        print("Usage: python 00-CallAPI.py <USER_ID> <START_DATE> <END_DATE>") 
        sys.exit(1)

    uid, s_date, e_date = sys.argv[1], sys.argv[2], sys.argv[3]
    
    start = datetime.strptime(s_date,"%Y-%m-%d")
    end   = datetime.strptime(e_date,"%Y-%m-%d")
    
    total_days = (end-start).days + 1
    print(f"[INFO] Starting collection for {total_days} days (estimated max ~{(total_days*9)/MAX_CALLS_HOUR:.1f} hours)")

    for idx, day in enumerate(daterange(start,end),1):
        d = iso(day)
        print(f"[{idx}/{total_days}] {d} …", end="", flush=True)
        try:
            get_activity_daily(uid,d)
            get_activity_intraday(uid,d,"1min")   # 필요 시 '5min' 으로 바꿔 콜 1/3
            get_azm(uid,d)
            get_sleep(uid,d)
            get_hr_intraday(uid,d)
            get_rhr(uid,d)
            get_hrv(uid,d)
            print(" OK")
        except Exception as e:
            print(f" Failed → {e}")

    print(f"\n? Complete: CSV files have been saved to {CSV_DIR.resolve()}")

if __name__ == "__main__":
    main()