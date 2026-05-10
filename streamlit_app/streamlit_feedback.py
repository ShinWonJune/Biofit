# streamlit_app/streamlit_feedback.py
import os
import streamlit as st
import requests
from datetime import date

uid = st.text_input("👤 회원 ID", value="")

# ─────────────────────────────────────────────────────────
# 숙면 피드백 — PSQI C1(주관적 수면 질) 0~3
# ─────────────────────────────────────────────────────────
sleep_quality = st.radio(
    label="잘 잤나요?",
    options=["최고", "잘잤어", "못잤어", "최악"],
    horizontal=True,
)
score_map = {"최고": 0, "잘잤어": 1, "못잤어": 2, "최악": 3}
score = score_map[sleep_quality]

FEEDBACK_API_URL = os.getenv("FEEDBACK_API_URL", "http://feedback-api:8001/feedback")

if st.button("✅ 입력"):
    if not uid.strip():
        st.error("❗ 회원 ID를 입력해주세요.")
        st.stop()
    payload = {
        "user_id":     uid.strip(),
        "date":        date.today().isoformat(),
        "sleep_score": score,
    }
    try:
        resp = requests.post(FEEDBACK_API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        st.success("🎉 저장 완료")
    except requests.RequestException as e:
        st.error(f"❌ 전송 실패: {e}")


# ─────────────────────────────────────────────────────────
# 잠자리에 누웠어요 — PSQI C2 잠복기 정확도 보강
# ─────────────────────────────────────────────────────────
st.markdown("---")

BEDTIME_LOG_URL = os.getenv(
    "BEDTIME_LOG_URL",
    FEEDBACK_API_URL.rsplit("/", 1)[0] + "/bedtime-log",
)

if st.button("🛏️ 잠자리에 누웠어요"):
    if not uid.strip():
        st.error("❗ 회원 ID를 입력해주세요.")
    else:
        try:
            resp = requests.post(
                BEDTIME_LOG_URL,
                json={"user_id": uid.strip()},
                timeout=30,
            )
            resp.raise_for_status()
            st.success(f"🌙 기록됨 — {resp.json().get('bedtime_at', '')}")
        except requests.RequestException as e:
            st.error(f"❌ 전송 실패: {e}")
