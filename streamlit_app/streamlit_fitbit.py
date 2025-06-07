# streamlit_app/streamlit_fitbit.py
import os
import requests
import streamlit as st
from datetime import datetime
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

st.set_page_config(page_title="BioFit Streamlit Frontend", layout="centered")
st.title("🔄 BioFit: 데이터 수집·전처리 요청")

# (1) 사용자 입력
uid = st.text_input("1) 내부 회원 ID (예: employee_001)", value="")
start_date = st.date_input("2) 조회 시작 날짜", value=datetime.today())
end_date = st.date_input("3) 조회 종료 날짜", value=datetime.today())
token = st.text_input("4) Fitbit Access Token", type="password")

# (2) Environment Variables
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data:8001/fetch")

if st.button("🚀 데이터 수집·전처리 시작"):
    # 입력 검증
    if not uid.strip():
        st.error("❗ 회원 ID를 입력해주세요.")
        st.stop()
    if start_date > end_date:
        st.error("❗ 시작 날짜가 종료 날짜보다 큽니다.")
        st.stop()
    if not token.strip():
        st.error("❗ Fitbit Access Token을 입력해주세요.")
        st.stop()
    logging.info(f"[Streamlit] 사용자 입력 토큰 앞 10자: {token[:10]}")
    logging.info(f"[Streamlit] 사용자 입력 토큰 뒤 10자: {token[-10:]}")
    logging.info(f"[Streamlit] 전송 페이로드: uid={uid}, start={start_date}, end={end_date}")
    # (3) 환경변수에 토큰 설정 (Data Service로 전달되도록)
    # os.environ["FITBIT_TOKEN"] = token.strip()

    # (4) 요청 페이로드 구성
    payload = {
        "uid": uid.strip(),
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "token": token.strip()
    }
    logging.info(json.dumps(payload, indent=2)[:200] + "...")
    logging.info(json.dumps(payload, indent=2)[-10:] + "...")
    st.info("⏳ Data Service에 데이터 수집·전처리 요청 중...")
    try:
        resp = requests.post(DATA_SERVICE_URL, json=payload, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        st.error(f"❌ Data Service 호출 실패: {e}")
        st.stop()

    data = resp.json()
    if data.get("status") != "ok":
        st.error(f"❌ Data Service 오류: {data}")
        st.stop()

    # (5) 성공 메시지 표시
    st.success(data.get("message", "데이터 수집·전처리 완료"))

    # (6) 처리된 데이터가 DB에 모두 저장된 상태이므로, 여기서 추가 작업(조회·시각화 등)을 할 수 있음.
    st.info("✅ 데이터가 DB에 저장되었습니다.")
    st.write("이제 AI 서비스 또는 다른 로직을 호출할 수 있습니다.")
