# BioFit 🏋️‍♀️💤

> **AI Sleep & Workout Timing Coaching Platform for Gyms**
> Built as the C&S Project 2025 — Team G, GIST AI Graduate School.

BioFit은 헬스장 회원 이탈률 감소를 *목적*으로 트레이너의 회원 코칭을 보조하는 마이크로서비스 프로토타입입니다. 수면의 질 향상을 위한 회원별 맞춤 운동·수면 시간대 제안과 지난 일주일 간의 신체 상태 분석, 그리고 유사 운동 시간대 회원 간 그룹·파트너 추천을 한 서비스 안에서 제공합니다.

> ⚠ **인과 검증 한계 (정직성 표기)** — 본 프로젝트의 동기는 *수면 질 1점 하락당 이탈 위험 약 11% 증가* (헬스장 신규 회원 153명 6주 관찰 연구, PPT Slide 4 인용)라는 **상관** 결과입니다. *수면 코칭이 실제로 이탈을 줄인다*는 **인과** 효과는 본 프로토타입 데이터로 **미검증**이며, 효과 검증은 후속 RCT 또는 difference-in-differences 설계로 진행 예정입니다. 자세한 분석은 [`docs/project_analysis.md`](docs/project_analysis.md) §1·§4 참조.

---

## 핵심 기능 및 서비스 구조

### Front-End (Streamlit) 

- **트레이너용 상담 대시보드 (Streamlit, port 8501)** — 트레이너가 회원 ID와 Fitbit Access Token을 입력하면 한 화면에서 단계별 버튼으로 ① 데이터 수집·전처리(`data_service /fetch`) → ② AI 추론 실행 (`ai_service /predict`) → ③ 코칭 메시지 생성과 운동 파트너·그룹 세션 매칭(`group_service /predict`)을 진행합니다. 코칭 메시지는 운동·수면 시간대 제안과 지난 일주일 간의 신체 상태 분석 내용이 포함되며 카드 형태 HTML로 렌더링해 트레이너가 회원 대면 상담 시 그대로 보여줄 수 있도록 시각화하였습니다.
- **회원용 체감 수면 피드백 입력 UI (Streamlit, port 8502)** — 회원이 체감 수면 점수를 3단계(`별로` / `보통?` / `잘잤어!`)로 직접 입력합니다. 입력값은 `{uid}_feedback` 테이블에 적재되어, 다음 AI 추론 시 CatBoost 입력과 함께 LLM 프롬프트에 전달됩니다. 이를 통해 LLM이 회원의 객관적 Fitbit 효율값과 주관적 만족도 격차를 고려하여 메시지를 생성할 수 있도록 합니다.

### AI Inference

- **CatBoost + SHAP + LLM 파이프라인** — 일 단위 생체 데이터(심박·활동·수면 단계·HRV 등)로 수면 효율을 예측하고(CatBoost), 예측에 가장 크게 기여한 변수를 추출해(SHAP) 수면 효율에 가장 큰 영향을 미치는 변수를 도출합니다. 그 뒤, LLM 프롬프트에 주입한 뒤 한국어 코칭 메시지(`[summary]` 좋은 점·개선점 4~6문장 + `[plan]` 운동/환경/생활/식단 4줄 + 권장 운동 시간대)로 변환합니다.
- **자기 개선 코칭 루프** — 같은 회원의 **가장 최근 코칭 메시지**(`predictions.message`, `ORDER BY created_at DESC LIMIT 1`)를 다음 호출의 프롬프트에 주입합니다. LLM이 *지난 권장사항 이행 여부 및 효과*를 먼저 판단한 뒤 새로운 plan을 제시해, stateless한 LLM에 외부 메모리를 붙이는 구조입니다.
- **운동 파트너·그룹 세션 추천 (프로토타입)** — 운동 시간대가 30분 이상 겹치는 회원 간 *파트너 매칭* 및 *그룹 세션 매칭*을 통해 운동 유대감 형성으로 지속적 출석을 유도합니다. 매칭 알고리즘(`overlap()`)과 DB 스키마(`users`, `preferred_slots`, `group_sessions`, `match_history`)는 구현되어 있으나, 요청자 `uid`별 슬롯 동적 조회는 미구현(현재 하드코딩 슬롯 사용).

---

## Architecture

```
.
├── ai_service/            ← CatBoost + SHAP + vLLM(Llama 3) 코칭 메시지 생성
├── data_service/          ← (현재) CSV → DB 적재. Fitbit API 호출은 비활성
├── feedback_api/          ← 회원 체감 수면 점수 저장 (FastAPI)
├── group_service/         ← 파트너·그룹 매칭 (프로토타입, uid 미적용)
├── streamlit_app/         ← 트레이너 / 회원용 Streamlit UI
├── db/                    ← init SQL & seed CSVs (첫 기동 시 자동 적재)
├── docs/                  ← README_audit, 설계·발표 자료
├── docker-compose.yml
├── Dockerfile             ← Usage.md 가 요구하는 cs-project 단일 빌드용
└── README.md
```

| Service              | 컨테이너 LISTEN | Role                                              |
| -------------------- | -------------- | ------------------------------------------------- |
| db (postgres:13)     | 5432           | 회원별 시계열 + 공통 메타데이터 영속화           |
| streamlit            | 8501           | 트레이너 대시보드 (데이터 수집·AI 추론·추천 트리거) |
| streamlit-feedback   | 8502           | 회원용 체감 수면 피드백 입력 UI                  |
| data_service         | 8001           | (현재) CSV → DB 적재. ⚠ Fitbit API 직접 호출은 비활성. |
| feedback_api         | 8001           | 사용자별 `{uid}_feedback` 테이블에 점수 저장     |
| ai_service           | 8000           | CatBoost 학습·예측, SHAP, LLM 코칭 메시지 생성·DB 저장 |
| group_service        | 8003           | 시간대 30분 이상 겹침 기준 파트너·그룹 매칭 (미구현) |



---

## Quick Start

```bash
git clone https://github.com/GIST-AI-Creative-Project-2025Spr/team-g.git
cd team-g
docker compose up --build -d
```

### Open in Browser

| URL                              | 용도                  |
| -------------------------------- | ------------------- |
| http://localhost:8501            | 트레이너 메인 UI    |
| http://localhost:8502            | 회원용 피드백 입력 UI |


---

## Usage Flow

```
트레이너 화면(8501)
  ① 회원 ID + Fitbit Access Token 입력
  ② [데이터 수집·전처리] 버튼  ─→  data_service /fetch
  ③ [AI 추론 실행] 버튼        ─→  ai_service /predict
        - CatBoost → SHAP → LLM
        - 가장 최근 코칭(predictions.message)을 prompt에 주입(자기 개선 루프)
  ④ [파트너·그룹 추천] 버튼     ─→  group_service /predict

회원 화면(8502)
  ① 회원 ID + 날짜 + 수면 점수(별로/보통?/잘잤어! → 0/1/2) 입력
  ② [입력] 버튼                ─→  feedback_api /feedback
        → {uid}_feedback 테이블에 적재
        → 다음 AI 추론 시 CatBoost 입력·LLM 프롬프트로 함께 사용
```

> ⚠ **`/fetch`의 실제 동작**: 현재 `data_service/app.py`의 Fitbit API 호출 블록(`00-CallAPI.py`)이 주석 처리되어 있어, `/fetch`는 `./fitbit_csv/`에 사전 준비된 CSV를 DB로 적재하는 단계만 실행합니다. Fitbit Access Token 입력은 받지만 외부 호출은 일어나지 않습니다. 활성화하려면 `data_service/app.py:47-62`의 `subprocess.run(["python3", "00-CallAPI.py", ...])` 블록의 주석을 해제하세요.

---

## Configuration

| Variable (서비스)              | Default                                             | 설명                                       |
| ----------------------------- | --------------------------------------------------- | ----------------------------------------- |
| `DATABASE_URL` (all)          | `postgresql://biofit:biofitpass@db:5432/biofitdb`   | Postgres 연결 URI                         |
| `WINDOW` (ai_service)         | `7`                                                 | CatBoost rolling-window 일 수             |
| `OPENAI_BASE` (ai_service)    | `http://10.38.38.40:8004/v1`                        | vLLM (OpenAI 호환) 추론 엔드포인트         |
| `OPENAI_KEY` (ai_service)     | `token-abc123`                                      | vLLM 서버의 `--api-key` 와 일치해야 함     |

> 운영 환경에 따라 `OPENAI_BASE` / `OPENAI_KEY` 값을 `docker-compose.yml`의 `ai_service.environment` 또는 별도 `.env` 파일로 주입하면 됩니다. 미지정 시 위 Default 값으로 폴백.

> 초기 DB 스키마는 `./db/init/*.sql`이 컨테이너 첫 기동 시 자동 적재합니다 (`predictions`, `users`, `preferred_slots`, `group_sessions`, `match_history`, `token_usage` + 더미 데이터). ⚠ 더미 사용자 `23RK3S`의 `feedback` 테이블은 `CHECK (sleep_score IN (0,1))` 제약이 걸려 있어 "잘잤어!"(=2) 점수 입력이 실패합니다. 신규 사용자는 `feedback_api`가 SQLAlchemy로 새 테이블을 만들 때 CHECK 없이 생성되므로 영향 없음.

---

## Token & Cost Monitoring

`ai_service`는 모든 LLM 호출의 토큰 수를 콘솔과 `token_usage` 테이블에 동시 기록합니다.

```
[TOKENS] 23RK3S | prompt=836 | completion=162
```

회원·시점·prompt/completion 토큰 수가 모두 적재되므로 *호출 단위*로 LLM 비용 추적이 가능합니다.

---

## Improvements

### Phase 1 (2026-05-08) — 모델 정직성

`docs/project_analysis.md`의 27개 약점 중 *모델 정직성*에 가장 영향이 큰 3건을 1주(~10시간) 안에 처리한 결과:

| § | 약점 | 변경 위치 | 검증 |
|---|------|---------|------|
| §1 | 인용 연구(상관)를 인과처럼 표현 | `README.md:6` 인트로 + 인과 검증 한계 박스 | 표현 정정 확인 |
| §8.1 | 시계열 누수 (rolling이 오늘 포함, 동일시점 features) | `ai_service/sleep_coach_full_kr_v6.py:add_roll7,get_X,main` (`shift(1)`, LEAK_VARS 제외, target `t+1` forecast) | [`experiments/8_1_leakage_audit.ipynb`](experiments/8_1_leakage_audit.ipynb) 4 시나리오 비교 |
| §2.1 | train/test 분리 부재 | `sleep_coach_full_kr_v6.py:main` 7-day holdout + RMSE/MAE + 단순 평균 baseline. `predictions` 테이블에 `rmse_test`/`mae_test`/`data_window_end`/`feature_set_version` 4 컬럼 추가 (`db/init/007_predictions_eval_columns.sql`) | 노트북 시나리오 D vs E (CatBoost vs baseline) |

### 산출물

- **PR 단위 변경 요약** — `git log` 또는 본 저장소의 [Improvements 작업 PR](.) (작성 시점 기준 사용자가 직접 PR 생성)
- **노트북** — [`experiments/8_1_leakage_audit.ipynb`](experiments/8_1_leakage_audit.ipynb) (시나리오 A/B/C/D + 베이스라인 E)
- **분석 문서** — [`docs/project_analysis.md`](docs/project_analysis.md) (전체 약점 27개 + 우선순위 §10)
- **이번 작업 spec** — [`.omc/specs/deep-interview-biofit-1week-improvement.md`](.omc/specs/deep-interview-biofit-1week-improvement.md) (deep-interview ambiguity 14.7%로 합의된 1주 작업 정의)

### Non-Goals — 의도된 후속 과제

본 1주 작업은 *모델 정직성*에만 집중했고 다음은 *명시적으로 제외*했습니다 (분석 문서의 우선순위 §10 참조):

- **§8.2 운동 시간대 추천을 코드 측 회귀로 전환** — 현재 LLM이 환각으로 시간대를 산출. 회원의 과거 (운동 시간대, 수면 효율) 쌍으로 회귀 모델 학습 필요. 코드 ~150줄·2일 작업 추정
- **§9.1 동적 `{uid}_*` 테이블 → 통합 `fitbit_daily_features`** — 회원 200명 시 PostgreSQL 카탈로그가 1,800개 테이블로 부풀음. 정규화 마이그레이션 필요
- **§9.6 멱등성 키·`model_runs` 상태 머신** — vLLM timeout 시 토큰만 차감되고 결과 누락되는 정합성 문제
- **§9.7 Alembic 도입** — 현재 `db/init/*.sql`은 첫 기동만 동작. 운영 DB 스키마 변경에 마이그레이션 도구 필요. 본 작업의 `007_*.sql`도 운영 DB에는 사용자가 수동 ALTER 실행 필요
- **§4 within-subject 4주 미니 실험** — *추천 시간대를 따랐을 때 효율이 개선되는가*의 인과 검증. 1주 작업으로 불가능

### 운영 환경 적용 가이드

```bash
# 1) 본 보강 변경을 받은 후
docker compose down
docker compose up -d --build

# 2) 기존 운영 DB는 db/init/007_*.sql이 자동 적용 안 됨 — 수동 ALTER:
docker compose exec db psql -U biofit -d biofitdb \
    -f /docker-entrypoint-initdb.d/007_predictions_eval_columns.sql

# 3) AI 추론 호출
curl -X POST http://localhost:8002/predict \
    -H 'Content-Type: application/json' -d '{"uid":"23RK3S"}'
# → predictions 테이블에 rmse_test/mae_test/data_window_end/feature_set_version이 채워짐

# 4) 노트북 실측 RMSE는 사용자 환경에서 직접 실행
DATABASE_URL=postgresql://biofit:biofitpass@localhost:5432/biofitdb \
    jupyter nbconvert --to notebook --execute experiments/8_1_leakage_audit.ipynb
```

### Phase 2 (2026-05-08) — 시간대 회귀 + 메타 추적 + 평가 루프

Phase 1 모델 정직성 위에 (1) 운동 시간대 추천이 LLM 환각이 아닌 *데이터 회귀*에서 나오도록, (2) 모든 추론 호출의 *모델·프롬프트 메타*를 추적, (3) 트레이너의 *코칭 품질 평가 루프*를 닫음:

| § | 약점 | 변경 위치 | 검증 |
|---|------|---------|------|
| §8.2 | 운동 시간대를 LLM이 환각 (모든 회원 `20:00~20:30`) | `sleep_coach_full_kr_v6.py:recommend_workout_window` (효율 상위 30% 일자의 시간대별 활동 합계 → top-3 슬롯). 데이터 < 14일이면 cohort default `(18:00, 19:00)` fallback. LLM 프롬프트 시간 강제 라인이 회귀 결과를 *그대로 출력*하도록 변경. | [`experiments/8_2_window_regression.ipynb`](experiments/8_2_window_regression.ipynb) — 사용자 맞춤성·cohort 우위·fallback 가설 3개 |
| §8.5 | 모델 버전·프롬프트 해시·LLM 파라미터 미기록 → 재현성 0 | `predictions` 테이블에 4 컬럼 추가 (`model_version`, `prompt_hash CHAR(8)`, `llm_params JSONB`, `recommended_slot_json JSONB`) — `db/init/008_predictions_meta.sql`. 호출 시점 `MODEL_VERSION` 상수 + `sha256(SYS_PROMPT + prompt)[:8]` + `llm_params` JSON 캡처 | predictions row 마다 위 메타 채워져 호출 단위 추적 가능 |
| §8.3 | 코칭 메시지 품질 평가 신호 0 (closed loop 부재) | `predictions_feedback` 테이블 신규 (`db/init/009_predictions_feedback.sql`) — `(run_id, rating 1~5, useful, comment, rated_by)` + UNIQUE`(run_id, rated_by)`. `feedback_api`에 `POST /predictions/{run_id}/feedback` 신규 endpoint | curl 한 줄로 평가 적재. 1인 1회 강제, 외래키로 predictions 보장 |

#### 사용 예시 (Phase 2 신규 endpoint)

```bash
# 트레이너 thumbs up/down
curl -X POST http://localhost:8001/predictions/{run_id}/feedback \
    -H 'Content-Type: application/json' \
    -d '{"useful": true, "rated_by": "trainer-suh-01", "comment": "회원 만족도 높았음"}'

# 회원 별점 (1~5)
curl -X POST http://localhost:8001/predictions/{run_id}/feedback \
    -H 'Content-Type: application/json' \
    -d '{"rating": 4, "rated_by": "23RK3S"}'

# rating·useful 둘 다 미입력 시 422 / 동일 rated_by 재호출 시 409 / 존재하지 않는 run_id면 404
```

#### Phase 2 운영 적용 가이드 (Phase 1 위에 누적)

```bash
# 새 init SQL을 운영 DB에 수동 적용 (첫 기동 시는 자동)
docker compose exec db psql -U biofit -d biofitdb \
    -f /docker-entrypoint-initdb.d/008_predictions_meta.sql
docker compose exec db psql -U biofit -d biofitdb \
    -f /docker-entrypoint-initdb.d/009_predictions_feedback.sql

# 검증 노트북 (8_2_window_regression.ipynb)
DATABASE_URL=postgresql://biofit:biofitpass@localhost:5432/biofitdb \
    jupyter nbconvert --to notebook --execute experiments/8_2_window_regression.ipynb
```

#### Phase 3 prep — 다음 단계 (~2주, ~15시간 예산)

- **§9.7 Alembic 도입** — `db/init/*.sql`은 첫 기동만 동작 → 운영 DB 스키마 변경 자동화. `migrate` 1회성 컨테이너 추가
- **§9.1 통합 `fitbit_daily_features` (expand-contract의 expand 단계)** — 동적 `{uid}_*` 테이블이 회원 200명 시 1,800개. 정규화 wide-format 테이블 도입 + dual-write·dual-read 도입 (기존 테이블 *유지*하면서 점진 전환)
- **§9.6 멱등성 키 + `model_runs` 상태 머신** — vLLM timeout 시 토큰 누수·predictions 누락 방지

Phase 3 작업 시 본 Phase 2의 `predictions` 컬럼·`predictions_feedback` 테이블 모두 그대로 유지(외래키 호환).

---

## Team

| Member          | Role                                                                  |
| --------------- | --------------------------------------------------------------------- |
| Hongyiel Suh    | Team Co-Leader · Model Architect (기획·관리·모델 설계)               |
| WonJune Shin    | Team Co-Leader · Service Developer / Operator (기획·API 개발·운영·네트워크 설계) |

---

## License

MIT License © 2025 BioFit Development Team
