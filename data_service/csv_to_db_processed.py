# data_service/csv_to_db_processed.py
import os
import pandas as pd
import sqlalchemy
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

engine = sqlalchemy.create_engine(DATABASE_URL)

# 전처리 결과 두 개의 CSV 경로
PROC_CSVS = [
    Path("daily_merged_filled-origin.csv"),
    Path("daily_merged_filled2_filled.csv")
]

def load_processed_csv_to_db():
    for csv_path in PROC_CSVS:
        if not csv_path.exists():
            print(f"Processed CSV가 없음: {csv_path}")
            continue
        df = pd.read_csv(csv_path)
        # 파일명에서 UID 추출: 첫 번째 열에 "user_id" 컬럼이 있다고 가정
        if "user_id" in df.columns:
            uid = df["user_id"].iloc[0]
        else:
            raise RuntimeError(f"{csv_path.name}에 user_id 컬럼이 없습니다.")
        table_base = csv_path.stem  # ex) "daily_merged_filled-origin"
        table_name = f"{uid}_{table_base.replace('-', '_')}"
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists="replace",
            index=False,
            chunksize=500
        )
        print(f">> Processed CSV '{csv_path.name}' → '{table_name}' ({len(df)} rows)")

if __name__ == "__main__":
    load_processed_csv_to_db()
