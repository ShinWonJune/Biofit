import os
import json
import requests
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import logging
import psycopg2
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# 페이지 네비게이션 설정
st.set_page_config(page_title="BioFit Multi-Page Frontend", layout="centered")
page = st.sidebar.selectbox("📑 페이지 선택", ["데이터 & AI 예측", "숙면 피드백"] )

if page == "숙면 피드백":
    # Feedback 앱을 iframe으로 임베드
    FEEDBACK_URL = os.getenv("FEEDBACK_APP_URL", "http://172.28.8.101:8502")
    st.title("🌙 BioFit: 숙면 피드백 입력")
    components.iframe(f"{FEEDBACK_URL}", height=700, scrolling=True)

else:
    st.title("🔄 BioFit: 데이터 수집·전처리 요청")

    # ─── Session state 초기화 ───
    if "data_ready" not in st.session_state:
        st.session_state.data_ready = False
    if "last_uid" not in st.session_state:
        st.session_state.last_uid = ""

    # (1) 사용자 입력
    uid = st.text_input("1) 내부 회원 ID (예: employee_001)", value="")
    start_date = st.date_input("2) 조회 시작 날짜", value=datetime.today())
    end_date = st.date_input("3) 조회 종료 날짜", value=datetime.today())
    token = st.text_input("4) Fitbit Access Token", type="password")

    # (2) Environment Variables
    DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data:8001/fetch")
    AI_URL           = os.getenv("AI_URL",           "http://ai_service:8000/predict")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "biofitdb"),
        user=os.getenv("DB_USER", "biofit"),
        password=os.getenv("DB_PASSWORD", "biofitpass"),
    )

    # ─── 1) 데이터 수집·전처리 버튼 ───
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
        payload = {
            "uid": uid.strip(),
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "token": token.strip()
        }
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

        st.success(data.get("message", "데이터 수집·전처리 완료"))
        st.info("✅ 데이터가 DB에 저장되었습니다.")
        st.write("이제 AI 서비스 또는 다른 로직을 호출할 수 있습니다.")
        st.session_state.data_ready = True
        st.session_state.last_uid   = uid.strip()

    # ─── 2) AI 추론 버튼 ───
    disabled = not st.session_state.data_ready or st.session_state.last_uid != uid.strip()
    if st.button("🤖 AI 추론 실행", disabled=disabled):
        st.info("⏳ AI 모델 추론 중...")
        try:
            r = requests.post(AI_URL, json={"uid": uid.strip()}, timeout=300)
            r.raise_for_status()
        except requests.RequestException as e:
            st.error(f"❌ AI 서비스 호출 실패: {e}")
            st.stop()

        if r.json().get("status") != "ok":
            st.error(f"❌ AI 서비스 오류: {r.text}")
            st.stop()

        st.success("AI 추론 완료 ✅")

        # DB에서 가장 최근 메시지를 문자열로 가져오기
        df = pd.read_sql(
            "SELECT message FROM predictions WHERE uid = %s "
            "ORDER BY created_at DESC LIMIT 1",
            conn,
            params=(uid.strip(),),
        )
        message = df["message"].iloc[0]

        # 헤더
        st.markdown("## 예측 결과")

        # 강조 박스 HTML (components.html 사용)
        html = f"""
        <div style="
            background-color: #e8f5e9;
            padding: 20px;
            border-radius: 12px;
            margin-top: 10px;
            white-space: pre-wrap;
        ">
            <p style="
                font-size: 16px;
                font-weight: bold;
                line-height: 1.4;
                color: #2e7d32;
                text-align: left;
                margin: 0;
            ">
                {message}
            </p>
        </div>
        """
        components.html(html, height=1000, scrolling=True)
