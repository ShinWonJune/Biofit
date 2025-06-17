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

🗂 Repository Layout
```
.
├── ai_service/            ← CatBoost & Llama 3 inference
├── data_service/          ← Fitbit fetch / preprocessing
├── feedback_api/          ← store user feedback (FastAPI)
├── group_service/         ← partner / group recommendation
├── streamlit_app/         ← Streamlit front-end
├── db/                    ← init SQL & seed CSVs
├── docker-compose.yml
└── README.md              ← (this file)
```

# Git Build

1) clone & cd \
[git clone https://github.com/GIST-AI-Creative-Project-2025Spr/team-g.git](https://github.com/GIST-AI-Creative-Project-2025Spr/team-g.git) 
```
cd biofit
```
2) build & run all services 
```
docker compose up --build -d
```
3) open in browser 
```
• Main UI        : http://localhost:8501 
• Feedback UI    : http://localhost:8502 
• Data-service   : http://localhost:8000/docs 
• Partner API    : http://localhost:8003/docs
```
# Docker Build

🌐 Docker Hub Images

```
docker login                    
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
| Variable (service)          | Default                                           | Description                                |
| --------------------------- | ------------------------------------------------- | ------------------------------------------ |
| `DATABASE_URL` (all)        | `postgresql://biofit:biofitpass@db:5432/biofitdb` | Postgres connection URI                    |
| `OPENAI_BASE` (ai\_service) | `http://llm-proxy:8282/v1`                        | **vLLM / OpenAI-compatible** REST endpoint |
| `OPENAI_KEY` (ai\_service)  | `token-abc123`                                    | Server `--api-key` value                   |
| `WINDOW` (ai\_service)      | `7`                                               | rolling-window days for CatBoost features  |

```
OPENAI_BASE:  http://llm-proxy:8282/v1 
OPENAI_KEY:   token-abc123              
```


💽 Initial Database \
All tables are boot-strapped via ./db/init/*.sql at first run

📊 Monitoring Token Usage \
ai_service logs token counts per request:
```
[TOKENS] 23RK3S | prompt=836 | completion=162
```

MIT License \
© 2025 BioFit Development Team


| Made with CatBoost + Llama 3

## Q&A

Please use the `Issues` function to raise inquiries.
