# C&S Project 2025 - Team G

## BioFit

*This repository is a collection of prerequisites and guidance for team project activities.


## Directory Structure

The directory structure below must be followed, and must be periodically updated in order to be recognized for contributions in external activities such as presentations.

```
.
├── ./ai_service
│   ├── ./ai_service/catboost_info
│   │   ├── ./ai_service/catboost_info/learn
│   │   └── ./ai_service/catboost_info/tmp
│   ├── ./ai_service/@eaDir
│   ├── ./ai_service/logs
│   ├── ./ai_service/models
│   │   └── ./ai_service/models/@eaDir
│   └── ./ai_service/__pycache__
├── ./data_service
│   ├── ./data_service/@eaDir
│   ├── ./data_service/fitbit_csv
│   │   └── ./data_service/fitbit_csv/@eaDir
│   └── ./data_service/__pycache__
├── ./db
│   ├── ./db/@eaDir
│   └── ./db/init
│       └── ./db/init/@eaDir
├── ./docs
│   └── ./docs/@eaDir
├── ./@eaDir
├── ./feedback_api
├── ./group_service
│   └── ./group_service/__pycache__
├── ./llama3
└── ./streamlit_app

```

## Guidelines
실행 방법: 방법은 두가지 입니다. 

1. github 에서 데이터를 다운받아서 진행하면 모델을 수동으로 받아 진행해야 합니다.
```
unset DOCKER_HOST
docker compose down
docker compose up --build
```

2. Docker 방식

```
docker login                    # (이미 되어 있으면 생략)
docker pull suhho/teamg:streamlit
docker pull suhho/teamg:data
docker pull suhho/teamg:streamlit-feedback
docker pull suhho/teamg:feedback-api
docker pull suhho/teamg:ai-service
docker pull suhho/teamg:group-service

docker compose up -d
```

# BioFit 🏋️‍♀️💤

**BioFit** is an end-to-end wearable-data platform that

* ingests raw Fitbit data & user feedback,
* runs ML / LLM pipelines to generate personalised sleep-activity coaching,
* recommends workout partners / group sessions,
* serves the results through a Streamlit front-end.

---

🗂 Repository Layout
.
├── ai_service/            ← CatBoost & Llama 3 inference
├── data_service/          ← Fitbit fetch / preprocessing
├── feedback_api/          ← store user feedback (FastAPI)
├── group_service/         ← partner / group recommendation
├── streamlit_app/         ← Streamlit front-end
├── db/                    ← init SQL & seed CSVs
├── docker-compose.yml
└── README.md              ← (this file)



# 1) clone & cd
git clone https://github.com/your-org/biofit.git
cd biofit

# 2) build & run all services
docker compose up --build -d

# 3) open in browser
#    • Main UI        : http://localhost:8501
#    • Feedback UI    : http://localhost:8502
#    • Data-service   : http://localhost:8000/docs
#    • Partner API    : http://localhost:8003/docs



🌐 Docker Hub Images

docker login
docker compose pull
docker compose up -d

| Service            | Docker Hub Tag                   | Port |
| ------------------ | -------------------------------- | ---- |
| db (Postgres 13)   | `postgres:13`                    | 5432 |
| streamlit          | `suhho/teamg:streamlit`          | 8501 |
| streamlit-feedback | `suhho/teamg:streamlit-feedback` | 8502 |
| data\_service      | `suhho/teamg:data`               | 8000 |
| feedback\_api      | `suhho/teamg:feedback-api`       | 8001 |
| ai\_service        | `suhho/teamg:ai-service`         | 8002 |
| group\_service     | `suhho/teamg:group-service`      | 8003 |

🔧 Environment Variables
| Variable (service)                         | Default                                            | Description                               |
| ------------------------------------------ | -------------------------------------------------- | ----------------------------------------- |
| `DATABASE_URL` (all)                       | `postgresql://biofit:biofitpass@db:5432/biofitdb`  | Postgres connection URI                   |
| `MODEL_PATH` (ai\_service)                 | `/app/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf` | Llama 3 GGUF path in container            |
| `WINDOW` (ai\_service)                     | `7`                                                | rolling-window days for CatBoost features |
| `DATA_SERVICE_URL` (streamlit)             | `http://data:8001/fetch`                           | internal API endpoint                     |
| `FEEDBACK_API_URL` (streamlit-feedback)    | `http://feedback-api:8001/feedback`                | feedback endpoint                         |
| `OPENAI_BASE` / `OPENAI_KEY` (ai\_service) | see `.env` example                                 | vLLM / OpenAI-compatible proxy            |

💽 Initial Database
All tables are boot-strapped via ./db/init/*.sql at first run

📊 Monitoring Token Usage
ai_service logs token counts per request:
```
[TOKENS] 23RK3S | prompt=836 | completion=162
```

MIT License
© 2025 BioFit Development Team


| Made with CatBoost + Llama 3

## Q&A

Please use the `Issues` function to raise inquiries.
