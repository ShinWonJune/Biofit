# data_service/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# 시스템 의존성 설치 (PostgreSQL client 라이브러리 등)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      gcc \
      libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 라이브러리 설치
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 애플리케이션 복사
COPY app.py /app/app.py

# Fitbit CSV를 저장할 디렉터리 생성
RUN mkdir -p /app/fitbit_csv

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
