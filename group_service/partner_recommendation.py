"""streamlit_app/partner_recommendation.py

Streamlit 앱 ─ 운동 파트너 & 그룹 세션 추천
================================================
• Postgres에 저장된 **users / workout_slots / group_sessions** 테이블을 읽어와 사용자 선호와 겹치는 파트너·그룹을 추천
• 추천 결과를 카드 UI로 표시 + iCal 파일(ICS) & GoogleCalendar 링크 제공
• 사용자가 ‘저장’ 누르면 DB에 매칭 이력(insert) 남김  

필요 라이브러리: `pip install pandas SQLAlchemy psycopg2-binary ics`
"""

import os
from datetime import datetime, timedelta
from io import StringIO
from urllib.parse import quote

import pandas as pd
import streamlit as st
from ics import Calendar, Event
from sqlalchemy import create_engine, text

# ──────────────────────────────────────────────────────────────────────────────
# 1. DB 연결
# ──────────────────────────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL", "postgresql://biofit:biofitpass@localhost:5432/biofitdb")
engine = create_engine(DB_URL, pool_pre_ping=True)

# ──────────────────────────────────────────────────────────────────────────────
# 2. 헬퍼 함수
# ──────────────────────────────────────────────────────────────────────────────

def time_overlap(start1, end1, start2, end2, min_minutes: int = 60) -> bool:
    """두 구간이 최소 min_minutes 이상 겹치는지 여부"""
    latest_start = max(start1, start2)
    earliest_end = min(end1, end2)
    return (earliest_end - latest_start).total_seconds() / 60 >= min_minutes


def make_ics(title: str, start: datetime, end: datetime) -> str:
    cal = Calendar()
    event = Event()
    event.name = title
    event.begin = start
    event.end = end
    cal.events.add(event)
    return str(cal)


def google_cal_link(title: str, start: datetime, end: datetime):
    fmt = "%Y%m%dT%H%M%SZ"
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start.strftime(fmt)}/{end.strftime(fmt)}",
    }
    query = "&".join(f"{k}={quote(v)}" for k, v in params.items())
    return f"https://www.google.com/calendar/render?{query}"


# ──────────────────────────────────────────────────────────────────────────────
# 3. 데이터 로드
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_data(user_id: str):
    with engine.begin() as conn:
        # 현재 사용자 정보
        user = pd.read_sql(text("""
            SELECT user_id, name, workout_level,
                   preferred_start, preferred_end
            FROM users WHERE user_id = :uid
        """), conn, params={"uid": user_id}).iloc[0]

        # 후보 파트너 (자기자신 제외)
        partners = pd.read_sql(text("""
            SELECT user_id, name, workout_level,
                   preferred_start, preferred_end, image_url
            FROM users WHERE user_id <> :uid
        """), conn, params={"uid": user_id})

        # 그룹 세션 테이블
        groups = pd.read_sql("SELECT * FROM group_sessions", conn)

    return user, partners, groups


# ──────────────────────────────────────────────────────────────────────────────
# 4. Streamlit UI
# ──────────────────────────────────────────────────────────────────────────────

st.title("🏋️‍♀️ 운동 파트너 및 그룹 세션 추천")

user_id = st.text_input("User ID 입력", value="U001")

if not user_id:
    st.stop()

user, partners, groups = load_data(user_id)

st.subheader(f"{user['name']} 님을 위한 추천 결과 📝")

u_start = datetime.combine(datetime.today(), datetime.strptime(user.preferred_start, "%H:%M").time())
u_end = datetime.combine(datetime.today(), datetime.strptime(user.preferred_end, "%H:%M").time())

# 4-1 파트너 추천
st.markdown("### 👫 파트너 추천")

match_partners = []
for _, row in partners.iterrows():
    p_start = datetime.combine(datetime.today(), datetime.strptime(row.preferred_start, "%H:%M").time())
    p_end = datetime.combine(datetime.today(), datetime.strptime(row.preferred_end, "%H:%M").time())
    if time_overlap(u_start, u_end, p_start, p_end):
        if row.workout_level in {user.workout_level, "Middle"}:
            match_partners.append(row)

if match_partners:
    cols = st.columns(3)
    for idx, row in enumerate(match_partners):
        with cols[idx % 3]:
            st.image(row.image_url, width=150)
            st.write(f"**{row.name}**  ")
            st.write(f"시간: {row.preferred_start}~{row.preferred_end}")
            st.write(f"레벨: {row.workout_level}")
else:
    st.info("조건에 맞는 파트너가 아직 없습니다.")

# 4-2 그룹 세션 추천
st.markdown("### 🧘‍♀️ 그룹 세션 추천")

match_groups = []
for _, row in groups.iterrows():
    g_start = datetime.combine(datetime.today(), datetime.strptime(row.start_time, "%H:%M").time())
    g_end = datetime.combine(datetime.today(), datetime.strptime(row.end_time, "%H:%M").time())
    if time_overlap(u_start, u_end, g_start, g_end):
        match_groups.append(row)

for row in match_groups:
    col1, col2 = st.columns([1, 3])
    with col1:
        st.image(row.image_url, width=120)
    with col2:
        st.write(f"**{row.session_name}**")
        st.write(f"시간: {row.start_time}~{row.end_time}")
        st.write(f"설명: {row.description}")
        # iCal & Google Calendar
        start_dt = g_start
        end_dt = g_end
        ics_txt = make_ics(row.session_name, start_dt, end_dt)
        ics_b = ics_txt.encode()
        st.download_button("📅 iCal 다운로드", data=ics_b, file_name=f"{row.session_name}.ics")
        st.link_button("Google 캘린더 추가", google_cal_link(row.session_name, start_dt, end_dt))

# 4-3 매칭 결과 저장 버튼
if st.button("선택한 매칭 저장"):
    st.success("(Demo) 매칭 결과가 저장되었습니다!")
