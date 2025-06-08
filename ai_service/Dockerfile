# ai_service/Dockerfile
FROM python:3.10-slim

# 1) Install system build-tools (gcc, g++, make) and CMake for llama-cpp-python
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libssl-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Copy & install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# 3) Copy application code and models
COPY . /app

EXPOSE 8000

# 4) Start FastAPI
CMD ["uvicorn", "app_ai:app", "--host", "0.0.0.0", "--port", "8000"]
