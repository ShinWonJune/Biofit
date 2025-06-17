# feedback_api/Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY main.py .

RUN pip install --no-cache-dir fastapi uvicorn sqlalchemy psycopg2-binary

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
