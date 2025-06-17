import os
import requests
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import logging
import psycopg2
import pandas as pd
import re

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ───────────────────────────────────────────────────────────
# 공통 설정
# ───────────────────────────────────────────────────────────
st.set_page_config(page_title="BioFit Multi-Page Frontend",
                   layout="centered")
page = st.sidebar.selectbox("📑 페이지 선택",
                            ["데이터 & AI 예측", "숙면 피드백"])

# ───────────────────────────────────────────────────────────
# 페이지 2) 숙면 피드백 (iframe)
# ───────────────────────────────────────────────────────────
if page == "숙면 피드백":
    FEEDBACK_URL = os.getenv("FEEDBACK_APP_URL",
                             "http://172.28.8.101:8502")
    st.title("🌙 BioFit: 숙면 피드백 입력")
    components.iframe(f"{FEEDBACK_URL}", height=700, scrolling=True)
    st.stop()                      # 해당 페이지는 여기서 끝

# ───────────────────────────────────────────────────────────
# 페이지 1) 데이터 & AI 예측
# ───────────────────────────────────────────────────────────
st.title("🔄 BioFit: 데이터 수집·전처리 요청")

# ─── Session state 초기화 ───
for k, v in {
        "data_ready": False,
        "last_uid":   "",
        "pred_html":  None,          # ▲ AI 결과 HTML
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# (1) 사용자 입력
uid        = st.text_input("1) 내부 회원 ID (예: employee_001)", value="")
start_date = st.date_input("2) 조회 시작 날짜", value=datetime.today())
end_date   = st.date_input("3) 조회 종료 날짜", value=datetime.today())
token      = st.text_input("4) Fitbit Access Token", type="password")

# (2) 각종 엔드포인트
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL",
                             "http://data:8001/fetch")
AI_URL           = os.getenv("AI_URL",
                             "http://ai_service:8000/predict")
GROUP_URL        = os.getenv("GROUP_URL",
                             "http://group_service:8003/predict")

# DB 연결
conn = psycopg2.connect(
    host     = os.getenv("DB_HOST", "db"),
    port     = os.getenv("DB_PORT", "5432"),
    dbname   = os.getenv("DB_NAME", "biofitdb"),
    user     = os.getenv("DB_USER", "biofit"),
    password = os.getenv("DB_PASSWORD", "biofitpass"),
)

# ───────────────────────────────────────────────────────────
# 🔸 함수: AI 메시지를 카드 HTML로 변환
# ───────────────────────────────────────────────────────────
def build_pred_card(msg: str) -> str:
    """
    AI가 저장한 'message' 문자열을 예쁜 카드 HTML로 변환
    · **summary**, **plan** 키워드를 찾아 h2 태그로 분리
    · 줄바꿈은 <br> 또는 <li> 로
    """
    # 섹션 구분
    parts = re.split(r"\*\*([Ss]ummary|[Pp]lan)\*\*", msg)
    # 결과: ['', 'summary', '\n\n좋은 점 …', 'plan', '\n\n운동: …']
    html_body = ""
    for i in range(1, len(parts), 2):
        title = parts[i].capitalize()
        body  = parts[i+1].strip()

        # •와 숫자 등을 <li> 로 바꾸기
        body_lines = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"^[•\-]|^\d+\.", line):
                clean = re.sub(r"^[•\-\d\.]+\s*", "", line)
                body_lines.append(f"<li>{clean}</li>")
            else:
                body_lines.append(f"<p>{line}</p>")

        html_body += f"""
        <h3 style="margin-bottom:0.3rem;">{title}</h3>
        <ul style="margin-top:0.2rem; margin-left:1rem;">
            {''.join(body_lines)}
        </ul>
        """

    card = f"""
    <style>
    .pred-card {{
        background:#f3f7f4;
        border-left:6px solid #4caf50;
        border-radius:10px;
        padding:1.2rem 1.6rem;
        font-size:16px;
        line-height:1.55;
        color:#222;
    }}
    .pred-card h3 {{
        color:#1b5e20;
        font-size:18px;
    }}
    </style>
    <div class="pred-card">
        {html_body}
    </div>
    """
    return card


# ───────────────────────────────────────────────────────────
# 1) 데이터 수집·전처리
# ───────────────────────────────────────────────────────────
if st.button("🚀 데이터 수집·전처리 시작"):
    if not uid.strip():
        st.error("❗ 회원 ID를 입력해주세요."); st.stop()
    if start_date > end_date:
        st.error("❗ 시작 날짜가 종료 날짜보다 큽니다."); st.stop()
    if not token.strip():
        st.error("❗ Fitbit Access Token을 입력해주세요."); st.stop()

    payload = {
        "uid": uid.strip(),
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date":   end_date.strftime("%Y-%m-%d"),
        "token":      token.strip()
    }
    st.info("⏳ Data Service 호출 중 …")
    try:
        resp = requests.post(DATA_SERVICE_URL, json=payload, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        st.error(f"❌ Data Service 실패: {e}"); st.stop()

    data = resp.json()
    if data.get("status") != "ok":
        st.error(f"❌ Data Service 오류: {data}"); st.stop()

    st.success("✅ 데이터 저장 완료")
    st.session_state.data_ready = True
    st.session_state.last_uid   = uid.strip()

# ───────────────────────────────────────────────────────────
# 2) AI 추론
# ───────────────────────────────────────────────────────────
disabled = (not st.session_state.data_ready
            or st.session_state.last_uid != uid.strip())

if st.button("🤖 AI 추론 실행", disabled=disabled):
    st.info("⏳ AI 모델 추론 중 …")
    try:
        r = requests.post(AI_URL, json={"uid": uid.strip()}, timeout=300)
        r.raise_for_status()
    except requests.RequestException as e:
        st.error(f"❌ AI 서비스 실패: {e}"); st.stop()

    if r.json().get("status") != "ok":
        st.error(f"❌ AI 서비스 오류: {r.text}"); st.stop()

    st.success("✅ AI 추론 완료")

    # DB에서 최신 message 조회
    df = pd.read_sql("""
        SELECT message FROM predictions
        WHERE uid = %s ORDER BY created_at DESC LIMIT 1
    """, conn, params=(uid.strip(),))
    message = df["message"].iloc[0]

    # 카드 HTML 생성 & 세션에 저장
    st.session_state.pred_html = build_pred_card(message)

# ───────────────────────────────────────────────────────────
# 📌 AI 예측 결과 카드 (항상 최상단에 표시)
# ───────────────────────────────────────────────────────────
if st.session_state.pred_html:
    components.html(st.session_state.pred_html,
                    height=500, scrolling=True)
# ───────────────────────────────────────────────────────────
# 3) 파트너·그룹 추천
# ───────────────────────────────────────────────────────────
if st.button("🤝 파트너·그룹 추천 보기", disabled=disabled):
    st.info("⏳ 추천 계산 중 …")
    try:
        rec = requests.post(GROUP_URL, json={"uid": uid.strip()}, timeout=60
                            ).json()
    except Exception as e:
        st.error(f"❌ Group Service 실패: {e}"); st.stop()

    if rec.get("status") != "ok":
        st.error(f"❌ Group Service 오류: {rec}"); st.stop()

    # ── 파트너 ──
    st.markdown("### 👫 파트너 추천")
    partners = rec.get("partners", [])
    if not partners:
        st.info("조건에 맞는 파트너가 없습니다.")
    else:
        cols = st.columns(3)
        for i, p in enumerate(partners):
            with cols[i % 3]:
                st.image(p.get("image_url", ""), width=150)
                st.write(f"**{p['name']}**")
                slots = ", ".join([f"{s[0]}~{s[1]}" for s in p.get("slots", [])])
                st.write(f"가능 시간: {slots or '정보 없음'}")
                st.write(f"레벨: {p['workout_level']}")

    # ── 그룹 세션 ──
    st.markdown("### 🧘‍♀️ 그룹 세션 추천")
    for g in rec.get("groups", []):
        c1, c2 = st.columns([1, 3])
        with c1:
            st.image(g.get("image_url", ""), width=120)
        with c2:
            st.write(f"**{g['session_name']}**")
            st.write(f"시간: {g['start_time']} – {g['end_time']}")
            st.write(g.get("description", ""))
