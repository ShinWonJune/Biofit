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
                             "http://localhost:8502")
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
        "pred_html":  None,          # ▲ AI 결과 HTML (자연어 메시지 영역)
        "psqi_data":  None,          # ▲ PSQI 정형 데이터 (Phase F.5 — 점수·추천 슬롯)
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

# DB 연결 — 비밀번호는 환경변수 필수 (fallback 평문 제거)
try:
    _db_password = os.environ["DB_PASSWORD"]
except KeyError:
    raise RuntimeError(
        "DB_PASSWORD 환경변수가 설정되지 않았습니다. "
        ".env.example을 참고해 .env 파일을 생성하세요."
    )

conn = psycopg2.connect(
    host     = os.getenv("DB_HOST", "db"),
    port     = os.getenv("DB_PORT", "5432"),
    dbname   = os.getenv("DB_NAME", "biofitdb"),
    user     = os.getenv("DB_USER", "biofit"),
    password = _db_password,
)

# ───────────────────────────────────────────────────────────
# 🔸 함수: AI 메시지를 카드 HTML로 변환
# ───────────────────────────────────────────────────────────
def build_pred_card(msg: str) -> str:
    """
    AI가 저장한 'message' 문자열을 예쁜 카드 HTML로 변환
    · **summary**, **plan** 키워드를 찾아 h2 태그로 분리 (대괄호 변형 흡수)
    · 줄바꿈은 <br> 또는 <li> 로
    """
    if not msg:
        return ""
    # 섹션 구분 — `**summary**` / `**[summary]**` / 공백·대소문자 변형 모두 매치
    parts = re.split(r"\*\*\s*\[?\s*([Ss]ummary|[Pp]lan)\s*\]?\s*\*\*", msg)
    # 결과: ['', 'summary', '\n\n좋은 점 …', 'plan', '\n\n운동: …']

    # 마커가 매치 안 되면 (LLM 형식 깨짐) — 본문 전체를 한 단락으로 fallback
    if len(parts) < 3:
        safe = msg.strip().replace("\n", "<br>")
        return f"""
        <div class="pred-card" style="background:#f3f7f4;border-left:6px solid #4caf50;
             border-radius:10px;padding:1.2rem 1.6rem;font-size:16px;line-height:1.55;color:#222;">
          <p>{safe}</p>
        </div>
        """

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
# Phase F.4 — 트레이너 카드 정형/자연어 분리
# 정형 영역 (PSQI 점수·추천 슬롯·예측값)은 *언어 모델 안 거치고* 직접 렌더해
# 환각 위험 차단. 자연어 한 단락만 LLM이 만든 build_pred_card로.
# ───────────────────────────────────────────────────────────
def render_psqi_panel(data: dict) -> None:
    """PSQI 정형 데이터를 st.metric · st.dataframe으로 직접 렌더 (LLM 안 거침).

    data 키:
        - psqi_scores: {c1, c2, c3, c4, total}  현재 회원의 PSQI 4 차원 점수 + 합산
        - psqi_predicted_total: float            추천 슬롯에서의 예측 합산 점수
        - recommended_slot_psqi: {slot, ...}     추천 슬롯 정보
        - recommendation_mode: 'exploration' | 'exploitation'
    어느 키든 None이면 그 영역만 건너뜀. 옵트인 path 미사용 시 호출 안 됨.
    """
    if not data:
        return

    mode = data.get("recommendation_mode")
    if mode == "exploration":
        st.info("🔵 신규 회원 cold-start 단계 — 추천이 *데이터 균등 수집*용입니다.")
    elif mode == "exploitation":
        st.success("🟢 Forward simulation 추천 활성")

    scores = data.get("psqi_scores")
    if scores:
        st.markdown("### 🛌 PSQI 4 차원 점수 (낮을수록 수면 질 ↑)")
        cols = st.columns(5)
        for col_obj, dim_key, label in zip(
            cols,
            ["c1", "c2", "c3", "c4", "total"],
            ["C1 주관", "C2 잠복기", "C3 시간", "C4 효율", "합산"],
        ):
            v = scores.get(dim_key) if isinstance(scores, dict) else None
            col_obj.metric(label, f"{v:.1f}" if v is not None else "—")

    rec = data.get("recommended_slot_psqi")
    pred_total = data.get("psqi_predicted_total")
    if rec or pred_total is not None:
        st.markdown("### 🎯 추천 운동 시간대 + 예측 PSQI")
        if rec and isinstance(rec, dict):
            slot = rec.get("slot") or rec.get("slot_hour")
            st.markdown(f"- **추천 슬롯**: `{slot}`")
            preds = rec.get("predicted_dims")
            if isinstance(preds, dict):
                st.markdown("- **차원별 예측**: " + ", ".join(
                    f"{k}={v:.1f}" for k, v in preds.items()
                ))
        if pred_total is not None:
            current = scores.get("total") if isinstance(scores, dict) else None
            delta = (pred_total - current) if current is not None else None
            st.metric(
                "예측 PSQI 합산",
                f"{pred_total:.1f}",
                delta=f"{delta:+.1f}" if delta is not None else None,
                delta_color="inverse",  # PSQI는 낮을수록 좋음 → 감소가 긍정
            )


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
    progress = st.empty()
    progress.info("⏳ Data Service 호출 중 …")
    try:
        resp = requests.post(DATA_SERVICE_URL, json=payload, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        progress.empty()
        st.error(f"❌ Data Service 실패: {e}"); st.stop()

    data = resp.json()
    if data.get("status") != "ok":
        progress.empty()
        st.error(f"❌ Data Service 오류: {data}"); st.stop()

    progress.empty()
    st.success("✅ 데이터 저장 완료")
    st.session_state.data_ready = True
    st.session_state.last_uid   = uid.strip()

# ───────────────────────────────────────────────────────────
# 2) AI 추론
# ───────────────────────────────────────────────────────────
disabled = (not st.session_state.data_ready
            or st.session_state.last_uid != uid.strip())

if st.button("🤖 AI 추론 실행", disabled=disabled):
    # Streamlit이 위젯을 자동 제거하지 않으므로 placeholder 패턴 — 완료 후 .empty()로 제거
    progress = st.empty()
    progress.info("⏳ AI 모델 추론 중 …")
    try:
        r = requests.post(AI_URL, json={"uid": uid.strip()}, timeout=300)
        r.raise_for_status()
    except requests.RequestException as e:
        progress.empty()
        st.error(f"❌ AI 서비스 실패: {e}"); st.stop()

    if r.json().get("status") != "ok":
        progress.empty()
        st.error(f"❌ AI 서비스 오류: {r.text}"); st.stop()

    progress.empty()
    st.success("✅ AI 추론 완료")

    # Phase 5 §9.1 contract: 옵트인 (USE_PREDICTIONS_API=1) 시 ai_service의
    # GET /predictions/{run_id} API로 결과 조회. default(0) 또는 API 실패 시
    # 기존 psycopg2 SELECT로 fallback — 결합 지점이 *predictions 테이블 스키마*에서
    # *명시적 HTTP 계약*으로 이동.
    ai_response = r.json()
    run_id      = ai_response.get("run_id")
    message     = None
    use_api     = os.getenv("USE_PREDICTIONS_API", "0") == "1"

    if use_api and run_id:
        try:
            ai_base   = AI_URL.rsplit('/', 1)[0]   # 'http://ai_service:8000'
            api_resp  = requests.get(f"{ai_base}/predictions/{run_id}", timeout=10)
            if api_resp.status_code == 200:
                api_json = api_resp.json()
                message = api_json.get("message")
                # Phase F.5 — PSQI 정형 데이터 함께 받아 세션에 박제 (옵트인 시에만)
                psqi_payload = {
                    "psqi_scores":           api_json.get("psqi_scores"),
                    "psqi_predicted_total":  api_json.get("psqi_predicted_total"),
                    "recommended_slot_psqi": api_json.get("recommended_slot_psqi"),
                    "recommendation_mode":   api_json.get("recommendation_mode"),
                }
                if any(v is not None for v in psqi_payload.values()):
                    st.session_state.psqi_data = psqi_payload
                logging.info(f"[Phase 5] ai_service /predictions/{run_id} API 사용")
            else:
                logging.warning(f"[Phase 5] /predictions/{run_id} status={api_resp.status_code} → DB fallback")
        except Exception as e:
            logging.warning(f"[Phase 5] /predictions API 실패 → DB SELECT fallback: {e}")

    if message is None:
        # Legacy path: psycopg2로 predictions 직접 SELECT (Phase 5 commit 후에도 default)
        df = pd.read_sql("""
            SELECT message FROM predictions
            WHERE uid = %s ORDER BY created_at DESC LIMIT 1
        """, conn, params=(uid.strip(),))
        message = df["message"].iloc[0]

    # 카드 HTML 생성 & 세션에 저장
    st.session_state.pred_html = build_pred_card(message)

# ───────────────────────────────────────────────────────────
# 📌 AI 예측 결과 카드 (정형 패널 + 자연어 메시지 분리 — Phase F.4)
# ───────────────────────────────────────────────────────────
# 정형 영역 (PSQI 점수·추천 슬롯·예측값) — LLM 안 거침
if st.session_state.psqi_data:
    render_psqi_panel(st.session_state.psqi_data)

# 자연어 영역 (LLM 1단락 코칭) — 환각 검증 부담은 이 영역에 한정
if st.session_state.pred_html:
    st.markdown("### 💬 코칭 메시지")
    components.html(st.session_state.pred_html,
                    height=500, scrolling=True)
# ───────────────────────────────────────────────────────────
# 3) 파트너·그룹 추천
# ───────────────────────────────────────────────────────────
if st.button("🤝 파트너·그룹 추천 보기", disabled=disabled):
    progress = st.empty()
    progress.info("⏳ 추천 계산 중 …")
    try:
        rec = requests.post(GROUP_URL, json={"uid": uid.strip()}, timeout=60
                            ).json()
    except Exception as e:
        progress.empty()
        st.error(f"❌ Group Service 실패: {e}"); st.stop()

    if rec.get("status") != "ok":
        progress.empty()
        st.error(f"❌ Group Service 오류: {rec}"); st.stop()

    progress.empty()

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
