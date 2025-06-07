# feedback_api/main.py

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, MetaData, Table, Column, String, Date, Integer
import os

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

engine = create_engine(DATABASE_URL)
app = FastAPI()

class Feedback(BaseModel):
    user_id: str
    date: str
    sleep_score: int

@app.post("/feedback")
def receive_feedback(fb: Feedback):
    metadata = MetaData()
    table_name = f"{fb.user_id}_feedback"

    feedback_table = Table(
        table_name,
        metadata,
        Column("user_id", String, nullable=False),
        Column("date", Date, nullable=False),
        Column("sleep_score", Integer, nullable=False),
        extend_existing=True  # 테이블이 이미 있다면 무시하고 덮어씀
    )

    # 테이블이 없으면 자동 생성
    metadata.create_all(engine, tables=[feedback_table])

    # 데이터 삽입
    insert_query = feedback_table.insert().values(
        user_id=fb.user_id,
        date=fb.date,
        sleep_score=fb.sleep_score
    )

    with engine.begin() as conn:
        conn.execute(insert_query)

    return {"status": "ok", "message": f"✅ {table_name} 테이블에 피드백 저장 완료"}
