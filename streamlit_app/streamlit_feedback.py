# streamlit_app/streamlit_feedback.py
import os
import streamlit as st
import requests
from datetime import date

# st.set_page_config(page_title="BioFit 숙면 피드백", layout="centered")
# st.title("🌙 BioFit: 숙면 피드백 입력")

uid = st.text_input("👤 회원 ID를 입력하세요", value="")
selected_date = st.date_input("📅 날짜 선택", value=date.today())

st.markdown("## 🛏️ 잘 잤나요?")
sleep_quality = st.radio(
    label="숙면 정도 선택",
    options=["별로", "보통?", "잘잤어!"],
    horizontal=True
)

score_map = {"별로": 0, "보통?": 1, "잘잤어!": 2}
score = score_map[sleep_quality]

FEEDBACK_API_URL = os.getenv("FEEDBACK_API_URL", "http://data:8001/feedback")

if st.button("✅ 입력"):
    if not uid.strip():
        st.error("❗ 회원 ID를 입력해주세요.")
        st.stop()

    payload = {
        "user_id": uid.strip(),
        "date": selected_date.isoformat(),
        "sleep_score": score
    }

    try:
        resp = requests.post(FEEDBACK_API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        st.success("🎉 피드백이 성공적으로 저장되었습니다.")
    except requests.RequestException as e:
        st.error(f"❌ 전송 실패: {e}")
