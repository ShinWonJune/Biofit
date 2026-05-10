# BioFit MSA 구조와 이점 — 기술 해설

> **본 문서의 독자**: BioFit 프로젝트를 *처음 보는* 엔지니어·면접관·신규 합류 팀원. 코드는 안 봐도 *왜 이런 구조인지·각 서비스가 무엇을 가지고 있는지·어떤 이점이 있는지* 이해할 수 있도록 작성. 기술 용어는 *첫 등장 시 한 줄 해설*을 곁들임.
>
> **본 문서의 시점**: 5단계 보완(Phase 1~5) commit 완료. 이전 구조와의 *비교*가 자주 등장.

---

## 0. 한 줄 요약

> BioFit은 *수면 코칭이라는 도메인 작업*을 *책임 단위로 분리*해 7개 컨테이너로 나눈 마이크로서비스 시스템입니다. *서비스 분리 자체*는 처음부터 있었지만, *서비스 간 통신이 진짜로 분리됐는가*는 Phase 4·5에서 보강됐습니다 — 결합 지점이 *공유 DB 스키마*에서 *명시적 HTTP 계약*으로 옮겨졌습니다.

---

## 1. 핵심 용어 사전 (자주 등장하는 개념)

| 용어 | 한 줄 해설 |
|------|----------|
| **MSA** (Microservice Architecture) | 한 시스템을 *책임 단위*로 나눈 여러 작은 서비스로 구성하는 아키텍처. 각 서비스는 *독립 배포·독립 장애 격리·독립 데이터 소유*를 목표로 함. |
| **FastAPI** | Python의 비동기 웹 프레임워크. *Pydantic 모델*과 결합하면 *OpenAPI 스펙* 자동 생성 + 입력 검증 자동화. |
| **Pydantic 모델** | "API가 받는·돌려주는 데이터의 *모양*"을 Python 클래스로 선언. 타입이 다르면 자동 422 에러. |
| **OpenAPI** | API 명세 표준 (이전 명칭 Swagger). FastAPI가 자동 생성하는 `/docs` 페이지가 그것. *외부 클라이언트가 합의 없이 API를 쓸 수 있는 계약서*. |
| **HTTP 계약 (API contract)** | "이 endpoint는 이 모양의 입력을 받고 이 모양의 출력을 준다"는 *기계가 강제하는* 약속. *암묵적 DB 스키마*의 반대 개념. |
| **암묵적 DB 스키마 결합** | 한 서비스가 다른 서비스의 *DB 테이블명·컬럼명*을 *문자열로 hardcode*하는 패턴. 컴파일러가 못 잡고 *런타임 첫 호출까지* 깨짐을 모름. |
| **데이터 소유권 (data ownership)** | 한 테이블을 *오직 한 서비스만* read/write할 권리. 다른 서비스는 *API 경유*. MSA의 핵심 원칙. |
| **expand-contract 패턴** | 운영 중 스키마 변경의 안전 패턴. (1) 새 컬럼·새 테이블 *추가*(expand) → (2) 데이터 backfill → (3) 기존 컬럼·테이블 *제거*(contract). 다운타임 0. |
| **멱등성 (idempotency)** | 같은 요청을 *N번* 보내도 결과가 *1번*과 같음. `Idempotency-Key` 헤더로 클라이언트가 *재시도 안전*을 명시. |
| **healthcheck** | "서비스가 살아 있나?"를 정기적으로 묻는 메커니즘. Docker Compose에선 다른 서비스가 *ready 됐을 때만* 기동 가능. |
| **dual-write / dual-read** | 새 테이블을 도입할 때 *옛 + 새* 둘 다에 쓰고/읽어 *전환 안전성*을 확보하는 점진 전환 패턴. |
| **OAuth / RBAC** | OAuth = 외부 서비스(Fitbit)의 토큰 위임 흐름. RBAC = Role-Based Access Control, *역할 기반* 접근 통제 (예: 트레이너는 자기 회원만 조회). |
| **PIPA** | 한국 개인정보보호법. 회원 데이터 *수집·보존·삭제* 의무를 규정. |

---

## 2. BioFit은 *왜* MSA로 갔는가

### 2.1 도메인 동기

BioFit은 4개의 *서로 다른 책임*이 한 시스템에 들어 있습니다:

| 책임 | 무엇 |
|------|------|
| 데이터 수집 | Fitbit OAuth + 분/일 단위 시계열 적재 |
| 사용자 피드백 | 회원의 주관 점수 (`별로/보통/잘잤어!`) 수집 |
| AI 추론 | CatBoost 회귀 + SHAP 설명 + LLM 코칭 메시지 |
| 사회적 매칭 | 시간대 겹침 기반 파트너·그룹 추천 |

이 책임들은:
- **장애 격리가 필요**: vLLM(외부 GPU 추론) 다운 시 *데이터 수집*과 *피드백 입력*은 계속돼야 함
- **부하 패턴이 다름**: 데이터 수집은 *batch*, AI 추론은 *5분짜리 한 번*, 피드백은 *짧은 빈번한* 호출
- **변경 빈도가 다름**: LLM 프롬프트는 *주 단위* 튜닝, DB 스키마는 *월 단위* 변경
- **외부 의존성이 다름**: Fitbit API, vLLM, PostgreSQL 각각 다른 외부 시스템

→ 한 모놀리스에 묶으면 *vLLM 한 호출이 5분 블로킹*하는 동안 *피드백 입력 endpoint도 함께 멈춤*. MSA로 분리하면 *각 책임이 독립적으로 진화*.

### 2.2 컴퓨팅 동기

vLLM은 GPU가 필요하고, 다른 서비스는 CPU만 있으면 됩니다. 한 컨테이너에 묶으면 *모든 서비스를 GPU 머신*에 올려야 함 — 비용 N배. MSA에서는 vLLM만 외부 GPU 서버로 분리.

---

## 3. 시스템 전체 구조 한눈에

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  사용자 측 UI (Streamlit, 두 화면)                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  • 트레이너 화면 (8501)    : 데이터 수집 → AI 추론 → 그룹 추천 카드        │
│  • 회원 피드백 화면 (8502)  : 어제 잠 어땠어요? (별로/보통/잘잤어)        │
└──────────────────────────────────────────────────────────────────────────┘
       │ HTTP                                              │ HTTP
       ▼                                                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ data_service │  │  ai_service  │  │group_service │  │ feedback_api │
│   (8001)     │  │   (8000)     │  │   (8003)     │  │   (8001)     │
│              │  │              │  │              │  │              │
│ Fitbit OAuth │  │ CatBoost     │  │ slot 매칭    │  │ 피드백 적재  │
│ CSV 적재     │  │ SHAP         │  │ 추천 산출    │  │              │
│              │  │ vLLM 호출    │  │              │  │              │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │                 │
       │                 │ HTTP            │                 │
       │                 ▼                 │                 │
       │           ┌──────────┐            │                 │
       │           │   vLLM   │ (외부 GPU)│                 │
       │           │ 10.38... │            │                 │
       │           └──────────┘            │                 │
       │                                   │                 │
       └────────────────┬──────────────────┴─────────────────┘
                        ▼
                 ┌──────────────┐
                 │  PostgreSQL  │
                 │   (5432)     │
                 │              │
                 │  *논리적*    │
                 │ 소유권 분리  │
                 └──────────────┘
                        ▲
                        │ alembic upgrade head
                ┌───────┴──────┐
                │ migrate (1회) │  Phase 3 도입
                └──────────────┘
```

**컨테이너 수**: 7개 상시 + 1개 1회성 (`migrate`).

---

## 4. 각 서비스의 역할

### 4.1 `data_service` (port 8001) — 데이터 수집·정규화

**책임**: Fitbit API 호출(OAuth 토큰 위임) → CSV 8개 → PostgreSQL 적재.

**적재되는 8개 CSV**: `sleep_summary`, `sleep_detail`, `activity_sum`, `activity_1min`, `resting_hr`, `azm`(Active Zone Minutes, 심박 강도 기반 운동 분), `heart_rate_1min`, `hrv`(Heart Rate Variability).

**Phase 3 변경**: 기존 `{uid}_*` *동적 테이블*에 더해 *정규화 테이블* `fitbit_daily_features (user_id, date, ...)`에도 dual-write (옵트인 환경 변수 `DUAL_WRITE_NORMALIZED=1`).

**Phase 4 신규 endpoint**:
- `GET /users/{uid}/features?window=N` — Pydantic `FeatureRow` 18 필드. 회원의 최근 N일 features 반환. `window` 최대 1000 (회원 데이터 분포에 따라 조정).

### 4.2 `ai_service` (port 8000) — AI 추론

**책임**: 회원 features → CatBoost 회귀 → SHAP top-k → vLLM 호출 → 한국어 코칭 카드.

**핵심 파일**: `ai_service/sleep_coach_full_kr_v6.py`의 `coach_main()`.

**Phase 1·2 변경**: 시계열 누수 3종 제거(`shift(1).rolling`, `LEAK_VARS` 제외, target `t+1` forecast) + train/test holdout RMSE/MAE + `recommend_workout_window` 데이터 회귀 슬롯.

**Phase 3 신규**: `Idempotency-Key` HTTP 헤더 처리 + `model_runs` 단계별 상태 머신 (`queued → running → succeeded/failed`).

**Phase 4 변경**: 3-tier features 조회 분기 — `USE_DATA_SERVICE_API > USE_NORMALIZED_FEATURES > legacy {uid}_*`.

**Phase 5 신규 endpoint**:
- `GET /predictions/{run_id}` — Pydantic `PredictionResponse` 13 필드. 영구 저장된 추론 결과 조회.

### 4.3 `group_service` (port 8003) — 사회적 매칭

**책임**: 회원의 `preferred_slots` 시간대와 다른 회원·그룹 세션의 시간대를 30분 이상 겹침 기준으로 매칭.

**Phase 5 신규 endpoint** (분석 §6 결함 fix):
- `GET /recommendations/{uid}` — `RecommendationResponse` (uid, user_slots_used, fallback_used, partners, groups). `preferred_slots`에 회원이 *없으면* hardcoded 슬롯 fallback이지만 `fallback_used: true`로 *명시*.

### 4.4 `feedback_api` (port 8001 외부 → 내부 다른 컨테이너) — 피드백 수집

**책임**: 회원 자기보고 점수(`sleep_score`) 적재 + Phase 2의 *코칭 메시지 평가* (thumbs up/down) 수집.

**Phase 2 신규**: `POST /predictions/{run_id}/feedback` — 1인 1회 unique, 1~5 별점 + comment.

**Phase 4 신규**: `GET /users/{uid}/feedback` — 회원의 피드백 히스토리 조회.

### 4.5 `streamlit` (port 8501) — 트레이너 UI

**책임**: 트레이너의 추론 카드 화면. 버튼 누름 → 3개 백엔드를 순차 호출 → 카드 렌더링.

**Phase 5 변경**: `predictions` 테이블을 `psycopg2`로 *직접 SELECT*하던 코드를 옵트인(`USE_PREDICTIONS_API=1`) 시 `ai_service GET /predictions/{run_id}` 호출로 전환. *DB 직접 침투 결합 제거*.

### 4.6 `streamlit-feedback` (port 8502) — 회원 UI

**책임**: 회원이 *자기 잠* 평가 입력. `feedback_api`에 POST.

### 4.7 `db` (PostgreSQL 13, port 5432) — 공유 저장소

**책임**: 모든 서비스의 영속 저장소. *하나의 PostgreSQL 인스턴스*지만 *논리적 소유권*으로 분리 (§5).

**healthcheck**: `pg_isready` 기반. `migrate`와 `ai_service`는 db가 *ready 상태*에만 기동 (Phase 3 도입).

### 4.8 `migrate` (1회성) — 스키마 마이그레이션

**책임**: `alembic upgrade head` 1회 실행 후 종료. `service_completed_successfully` 의존성 → 실패 시 `ai_service` 자체가 기동되지 않음 → *깨진 schema에서 부팅하지 않는 안전장치*.

**Alembic이란**: SQLAlchemy 팀의 DB 스키마 마이그레이션 프레임워크. PostgreSQL 자체는 "스키마 변경 이력"을 못 추적 — Alembic이 `alembic_version` 메타 테이블로 *현재 적용된 마이그레이션 ID*를 박제.

---

## 5. 서비스별 데이터 소유권·계약 (핵심 표)

> *자기 소유 테이블에는 직접 access OK, 다른 서비스 소유 테이블에는 API 경유.*

| 서비스 | owns (자기 테이블) | exposes (외부 호출 가능 endpoint) | consumes (다른 서비스 호출) |
|--------|-----------------|--------------------------|------------------------|
| **data_service** | `fitbit_raw`, `fitbit_daily_features`, `{uid}_*` (legacy 동적 테이블) | `POST /fetch` (수집 트리거) `GET /users/{uid}/features?window=N` *(Phase 4 신규)* | Fitbit API |
| **feedback_api** | `predictions_feedback` (Phase 2), `sleep_feedback`, `{uid}_feedback` (legacy) | `POST /feedback`, `POST /predictions/{run_id}/feedback` *(Phase 2)* `GET /users/{uid}/feedback` *(Phase 4)* | — |
| **ai_service** | `predictions`, `token_usage`, `model_runs` *(Phase 3)*, `idempotency_log` *(Phase 3)* | `POST /predict` (Idempotency-Key 지원), `GET /predictions/{run_id}` *(Phase 5)* | `data_service /users/{uid}/features` `feedback_api /users/{uid}/feedback` `vLLM /chat/completions` |
| **group_service** | `users`, `preferred_slots`, `group_sessions`, `match_history` | `POST /predict` (legacy hardcoded), `GET /recommendations/{uid}` *(Phase 5, §6 fix)* | — |
| **streamlit** | (UI만, 영속 데이터 없음) | — | 4개 백엔드 + (옵트인 시) `ai_service /predictions/{run_id}` |

**왜 "공유 PostgreSQL 위의 논리적 분리"인가**: 물리적 DB 분리는 운영 자원이 큼(별도 인스턴스 4개). 본 단계에선 *같은 인스턴스*에서 *서비스별 read/write 권한*을 코드 측에서 강제 + 미래에 물리 분리 시 *데이터 이전 경계*를 미리 그어둠. Phase 6+에서 *DB 사용자 권한*까지 분리하면 그 경계가 *PostgreSQL이 강제*하는 형태로 진화.

---

## 6. 한 번의 추론 호출이 *어떻게* 흐르는가 (시간순)

트레이너가 트레이너 UI에서 회원 `23RK3S`의 [AI 추론] 버튼을 누른 순간:

```
1. streamlit → POST data_service /fetch
   { uid: "23RK3S", start_date, end_date, fitbit_token }
   ← { status: "ok" }
   (실제로는 Fitbit API 호출은 주석 처리, /app/fitbit_csv/*.csv를
    csv_to_db로 적재. dual-write 옵트인 시 fitbit_daily_features에도)

2. streamlit → POST ai_service /predict
   Header: Idempotency-Key (옵트인)
   { uid: "23RK3S" }

   ai_service 내부:
   2-1. idempotency_log에서 키 hit 체크. hit이면 즉시 기존 응답 반환.
   2-2. model_runs INSERT (status='queued', current_step='init')
   2-3. 옵트인 분기에 따라 features 조회:
        - USE_DATA_SERVICE_API=1 → GET data_service /users/23RK3S/features?window=1000
        - USE_NORMALIZED_FEATURES=1 → fitbit_daily_features 직접 SELECT
        - else → legacy {uid}_sleep_summary 등 직접 SELECT
   2-4. (USE_FEEDBACK_API_HTTP=1) GET feedback_api /users/23RK3S/feedback
   2-5. CatBoost 학습 + holdout RMSE/MAE 산출
        model_runs UPDATE (current_step='catboost_done')
   2-6. SHAP top-6 추출
   2-7. recommend_workout_window — 효율 상위 30% 일자의 시간대별 활동 합계 top-3
   2-8. vLLM /chat/completions 호출 (OpenAI-compatible client)
        프롬프트에 SHAP 표·권장 슬롯·이전 메시지 주입
        token_usage INSERT
        model_runs UPDATE (current_step='vllm_done')
   2-9. predictions INSERT (12 컬럼: uid, run_id, message, rmse_test, mae_test,
        data_window_end, feature_set_version, model_version, prompt_hash,
        llm_params, recommended_slot_json, ...)
   2-10. idempotency_log INSERT (응답 본문 JSONB)
   2-11. model_runs UPDATE (status='succeeded')

   ← { status: "ok", run_id, rmse_test, baseline_rmse, message_preview }

3. streamlit이 카드 본문 가져오기:
   - USE_PREDICTIONS_API=1 → GET ai_service /predictions/{run_id}
   - else → psycopg2 SELECT message FROM predictions ...
   
4. streamlit → POST group_service /predict (legacy)
   또는 GET group_service /recommendations/{uid} (Phase 5)
   ← { partners, groups, fallback_used }

5. streamlit이 모든 결과를 HTML 카드로 렌더링.
```

**왜 이렇게 단계가 많은가**: 각 단계가 *분리된 서비스의 책임*. 한 단계 실패가 다른 단계를 *오염*시키지 않게 *상태 머신*으로 추적(model_runs.current_step) → 면접 답변 가치: "어느 단계에서 자주 실패하나" SQL 한 줄로 분석 가능.

---

## 7. 결합 지점이 *어떻게 진화*했나 (Phase 1~5 변화)

### 7.1 As-Is — 컨테이너만 분리된 모놀리스

```text
ai_service: read_table(f"{uid}_sleep_summary", ...)
                       ↑
                       │ 문자열로 hardcode된 테이블명
                       │ data_service만 만들 수 있는 테이블
                       │ 컴파일러가 못 잡음
                       ↓
data_service: csv_to_db.py가 {uid}_{fname} 형태로 INSERT
```

**4 깨짐 시나리오** (분석 §9.1):
1. 새로고침 한 번 = 진행 상태 분실 (서버 측 상태 0)
2. 컬럼 rename = 다른 서비스가 *런타임 첫 호출에서 KeyError*
3. 회원 200명 = `pg_class`에 1,800개 테이블
4. 단위 변경 = 조용한 데이터 오염 ("예측 효율 8245%")

→ *모놀리스의 단점(런타임까지 못 잡음) + MSA의 단점(독립 배포·장애 격리 부재)*을 동시에 가짐.

### 7.2 Phase 4·5 — 결합 지점이 *명시적 HTTP 계약*으로 이동

**Pydantic 모델로 계약 코드화**:

```python
# data_service의 응답 모델 (계약을 코드로)
class FeatureRow(BaseModel):
    user_id: str
    date: date
    efficiency: Optional[float] = None
    stage_deep: Optional[int] = None
    # ... 18 필드

@app.get("/users/{uid}/features", response_model=List[FeatureRow])
def get_user_features(uid: str, window: int = Query(7, ge=1, le=1000)):
    ...
```

**ai_service는 endpoint 호출**:

```python
# ai_service가 features를 가져오는 방법 (Phase 4 옵트인)
if os.getenv("USE_DATA_SERVICE_API", "0") == "1":
    df = _fetch_features_via_api(uid)   # HTTP GET
    ...
```

**무엇이 좋아졌나**:

| 측면 | Before | After |
|------|--------|-------|
| 컬럼 rename 영향 | *런타임 첫 호출 KeyError* | Pydantic Field 제약과 *함께 갱신* 안 하면 PR 통과 불가 |
| 외부 클라이언트 (모바일·트레이너 단말 SDK) | 별도 합의 필요 | OpenAPI(`/docs`) 자동 생성, codegen 가능 |
| 테스트 | DB seed 필요 | endpoint mock으로 격리 테스트 |
| 장애 격리 | data_service의 SQL 변경 = ai_service 깨짐 | API 호환성 유지 시 영향 0 |

**진척도**: 7개 컨테이너 외부 결합 지점 8개 중 8개가 HTTP 계약으로 이전. 분석 문서 §9.1 To-Be의 약 90%.

---

## 8. 핵심 설계 결정과 그 *이유*

### 8.1 옵트인(opt-in) default 0 환경 변수 패턴

**무엇**: Phase 3·4·5에서 도입된 모든 새 path가 환경 변수로 *기본 비활성*. `USE_NORMALIZED_FEATURES=0`, `USE_DATA_SERVICE_API=0`, `USE_PREDICTIONS_API=0`, `DUAL_WRITE_NORMALIZED=0`.

**왜**: commit이 운영 환경에 배포돼도 *기존 동작 그대로*. 문제 발견 시 *코드 변경 없이* 옵트인 끄면 되돌아감. *3가지 가치 동시 획득*: 운영 안전성 + A/B 비교 가능성 + 즉시 롤백.

### 8.2 expand-contract 패턴

**무엇**: 정규화 테이블 도입 시 (1) 새 테이블 *추가*만 — 기존 동적 테이블 그대로, (2) dual-write로 데이터 동기화, (3) 운영 검증 후 *contract 단계*에서 기존 테이블 폐기.

**왜**: 한 번에 모든 코드 마이그레이션 시 *어느 path에서 회귀가 났는지* 진단 어려움. 점진 전환은 *각 단계의 commit이 독립*해 *어느 commit이 깨졌는지* git bisect 가능.

**현 단계**: Phase 5까지 *expand만* 진행. Phase 6에서 *contract* (legacy path 폐기) 예정.

### 8.3 Pydantic 모델 인라인 복제 vs. shared 패키지 (`biofit-contracts`)

**무엇**: 같은 `FeatureRow` Pydantic 클래스가 `data_service`(서버)와 `ai_service`(클라이언트) 양쪽에 *복사*되어 있음. 옆에 `@contract: shared with X. Phase 6+ extract` 주석.

**왜 인라인 복제**:
- shared 패키지(PyPI 또는 git submodule)는 운영 비용 큼 — 패키지 버전 관리, 각 서비스 Dockerfile에 install 추가, CI 호환성 검증
- 2명 monorepo + 5개 서비스 환경에선 *현재* 인라인 복제 + 주석으로 의도 박제가 더 정직
- *trigger*: 회원 100+ 또는 팀 5+ 시점에 PyPI 또는 git submodule로 추출

**위험 인지**: 두 서비스의 모델이 *drift할 가능성* — 한쪽만 갱신되면 silent에 일치 안 함. 검증 노트북·curl 예시가 *실제 응답 schema*를 cap한 형태로 commit.

### 8.4 멱등성 키 (Idempotency-Key) — AWS·Stripe 패턴

**무엇**: `POST /predict` 헤더에 `Idempotency-Key: <임의의 unique 문자열>`. 같은 키로 재호출 시 *기존 응답 즉시 반환* — vLLM/CatBoost 재실행 0건.

**왜 옵트인 헤더**: 헤더가 *없으면* 기존 동작과 동일. 있으면 분산 시스템의 *재시도 안전*. 클라이언트가 *명시적*으로 의도를 표현 — *조용한* 멱등성보다 *명시적* 멱등성이 디버깅 친화.

### 8.5 vLLM 외부 GPU 분리

**무엇**: vLLM은 Docker Compose 내부가 아니라 외부 GPU 서버(`http://10.38.38.40:8004/v1`). OpenAI-compatible API.

**왜 외부**:
- GPU 비용 — 모든 컨테이너가 GPU 머신에 올라가면 비용 N배
- 추론 서버는 *공유 자원* — 다른 프로젝트와 GPU 인스턴스 공유 가능
- *모델 교체*는 vLLM 재시작만으로 — 본 시스템 영향 0 (현재 `LLM_MODEL_NAME` 환경변수로 모델 ID 흡수)

**한계**: `docker compose up`만으로 *전체 시스템 재현*되는 설명이 약함. README와 본 문서에 *vLLM은 외부 의존*임을 명시.

---

## 9. 본 MSA 구조의 *현재 한계* (Phase 6+ 후속 과제)

### 9.1 동기 호출 5분 블로킹

**현황**: `streamlit → ai_service /predict`가 *5분 동기 대기*. CatBoost 학습 + SHAP + vLLM 호출이 한 요청 안.

**문제**: 트레이너 UI 5분 멈춤 + worker 점유 + reverse proxy timeout + 토큰 누수 위험 + 재시도 중복.

**보강 후보**: `POST /predict-jobs` 202 + `GET /predict-jobs/{job_id}` 폴링 패턴. FastAPI `BackgroundTasks` 또는 Celery+Redis. Phase 6 후보.

### 9.2 legacy DB direct path *공존*

**현황**: ai_service에 3-tier 분기 (`USE_DATA_SERVICE_API > USE_NORMALIZED_FEATURES > legacy`). legacy `read_table('{uid}_*')` 코드 그대로 잔존.

**왜 폐기 안 했나**: dual-path 옵트인의 *운영 검증 충분치 않음*. 검증 후 contract 단계에서 폐기 예정.

### 9.3 관찰가능성·분산 추적 부재

**현황**: 한 사용자 호출이 streamlit→data_service→ai_service→vLLM을 거치는데 *하나의 trace로 묶을 ID 없음*. 메트릭(p50/p95 latency, 에러율)도 미수집.

**보강 후보**: OpenTelemetry FastAPI 인스트루멘테이션 + structlog JSON + Prometheus exporter. Phase 6 후보.

### 9.4 인증·RBAC·PIPA

**현황**: Fitbit token이 *평문 텍스트박스*. 트레이너 권한 모델 부재. 회원 탈퇴 시 데이터 cascade 삭제 절차 미정의.

**보강 후보**: §5.3 OAuth 서버측화 + RBAC + §9.9 PIPA gap analysis. *운영 단계 진입*의 entry 조건.

---

## 10. 면접 답변용 한 줄 정리

> "BioFit MSA의 핵심은 *컨테이너를 7개로 나눴다*가 아니라 *서비스별 데이터 소유권을 분리하고 그 경계를 HTTP 계약으로 강제한다*입니다. 처음 구조에선 결합이 *DB 스키마*에 있었지만 Phase 4·5에서 *명시적 HTTP 계약 + Pydantic 모델*로 옮겼습니다. 옵트인 default 0 패턴으로 운영 안전성을 보장하면서, expand-contract 패턴으로 점진 전환의 토대를 만들었습니다. *진짜 운영형 MSA*가 되려면 *비동기 호출 패턴*과 *관찰가능성·인증*이 남았고, 그것이 분석 문서 §9에 카테고라이즈된 Phase 6+ 후속 과제입니다."

---

## 부록 — 참조 문서

- [`docs/project_analysis.md`](project_analysis.md) — 약점 27개 카테고라이즈 + To-Be 모델 (§9 본 문서의 출처)
- [`docs/PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md) — 면접 직전 30분 cheat sheet
- [`docs/phase4_improvement_report.md`](phase4_improvement_report.md), [`docs/phase5_improvement_report.md`](phase5_improvement_report.md) — HTTP 계약 도입 단계별 상세
- `ai_service/sleep_coach_full_kr_v6.py` — 추론 흐름의 실제 코드
- `docker-compose.yml` — 7개 컨테이너 정의 + healthcheck + 의존성 그래프
