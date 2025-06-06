# data_service/csv_to_db.py
import os
import glob
import pandas as pd
import sqlalchemy
from pathlib import Path

# 반드시 환경변수에서 DATABASE_URL을 읽어야 함
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

engine = sqlalchemy.create_engine(DATABASE_URL)
CSV_DIR = Path("/app/fitbit_csv")  # FITBIT CSV가 이 위치에 저장됨

# CSV 파일명 별로 DB 테이블명을 지정할 수 있다.
# 예: heart_rate_1min.csv → uid_heart_rate_1min
# 여기서 uid는 CSV 내부 첫 번째 컬럼, 혹은 파일이름으로부터 파싱해야 함.
# 하지만 우리는 00-CallAPI.py가 CSV 안에 user_id 컬럼을 이미 포함해서 만든다고 가정.

def load_raw_csv_to_db():
    for csv_path in CSV_DIR.glob("*.csv"):
        fname = csv_path.stem  # ex) "heart_rate_1min"
        # CSV 내부에 "user_id" 컬럼이 들어있으므로, 첫 행에서 user_id 추출
        df_sample = pd.read_csv(csv_path, nrows=1, dtype=str)
        if "user_id" not in df_sample.columns:
            continue
        uid = df_sample["user_id"].iloc[0]
        table_name = f"{uid}_{fname}"
        df = pd.read_csv(csv_path)
        # DB에 replace 방식으로 저장 (이미 존재하면 덮어쓰기)
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists="replace",
            index=False,
            chunksize=500
        )
        print(f">> Raw CSV '{csv_path.name}' → '{table_name}' ({len(df)} rows)")

if __name__ == "__main__":
    load_raw_csv_to_db()
