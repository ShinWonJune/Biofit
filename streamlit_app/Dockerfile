# streamlit_app/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install pandas SQLAlchemy psycopg2-binary ics

# 파이썬 라이브러리 설치
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 소스 코드 복사
COPY . /app

# fitbit_csv 폴더 생성 (Data Service가 실제로 여기에 CSV를 저장하도록 공유)
RUN mkdir -p /app/fitbit_csv

EXPOSE 8501

CMD ["streamlit", "run", "streamlit_fitbit.py", "--server.address=0.0.0.0", "--server.port=8501"]
