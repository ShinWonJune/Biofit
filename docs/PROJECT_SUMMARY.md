# BioFit 프로젝트 요약 — 면접 숙지용

> **목적**: 면접 직전 30분에 한 번 훑어 *과거 구조 → 발견된 문제 → 보완 결과 → 면접 답변 키*를 한꺼번에 떠올리기 위한 단일 문서. 분석은 [`docs/project_analysis.md`](project_analysis.md), 단계별 상세는 [`phase1_improvement_report.md`](phase1_improvement_report.md) ~ [`phase5_improvement_report.md`](phase5_improvement_report.md) 참조.
>
> **본 문서의 시점**: 5개 phase 모두 commit 완료 (`21b6525`, 2026-05-09). 본 문서는 *결과물 회고* 관점.
> **작성자 역할**: Backend/DevOps — FastAPI 7개 컨테이너, Streamlit, PostgreSQL, Docker Compose, vLLM MSA 데이터 흐름 책임.

---

## 0. 한 줄 엘리베이터 답변 (가장 짧은 면접 답변)

> "BioFit은 컨테이너만 7개로 나뉘었지 사실상 *공유 PostgreSQL 위의 모놀리스*였습니다. 5단계로 (1) 모델 정직성(시계열 누수 제거 + train/test holdout), (2) 데이터 회귀 기반 운동 시간대 + 메타 추적, (3) Alembic + 정규화 expand + 멱등성, (4)·(5) 서비스 간 결합 지점을 *암묵적 DB 스키마*에서 *명시적 HTTP 계약 + Pydantic 모델*로 옮겨, 5개의 외부 결합 지점을 모두 HTTP 계약 위에서 작동하도록 만들었습니다."

---

## 1. 프로젝트 한 화면 정리

| 축 | 내용 |
|----|------|
| **이름** | BioFit (C&S 2025, GIST AI, Team G) |
| **도메인** | 한국어 wearable AI 수면·운동 코칭 프로토타입 |
| **목적 가설** | 수면 코칭 → 헬스장 회원 이탈률 감소 (인용: 153명 6주 관찰 *상관* 연구, 효율(피츠버그 수면 질 지수) 1점 ↓ → 이탈 위험 11% ↑) |
| **데이터 흐름** | Fitbit → PostgreSQL → CatBoost (수면 효율 회귀) → SHAP top-k → vLLM (한국어 코칭 메시지) → Streamlit 카드 |
| **부수 흐름** | preferred_slots 30분 이상 겹침 매칭 → 파트너·그룹 추천 (group_service) |
| **인프라** | 7개 컨테이너 (db, streamlit, streamlit-feedback, data, feedback-api, ai_service, group_service) + 1개 1회성 (migrate). vLLM은 외부 (`http://10.38.38.40:8004/v1`, `openai/gpt-oss-20b`) |
| **언어/프레임워크** | Python 3, FastAPI, SQLAlchemy/psycopg2, pandas, CatBoost, SHAP, Streamlit, Pydantic, Alembic |

---

## 2. 평가 프레임 — 면접관이 파고들 7축 + Q&A

| # | 축 | 핵심 질문 | 약점 위치 |
|---|----|----------|---------|
| 2.1 | 인과 vs 상관 | "수면 개선 → 이탈 감소"가 입증인가 가정인가? | §1, §4 |
| 2.2 | 모델 신뢰성 | 점수와 SHAP을 의사결정에 쓸 만큼 검증됐나? | §2 |
| 2.3 | 타깃 적합성 | `sleep_efficiency`만으로 "수면 질" 대표 가능? | §3 |
| 2.4 | 검증 디자인 | 통제군·실험군이 있나? | §4 |
| 2.5 | 운영 신뢰성 | 출력 검증·보안·법규로 운영 진입 가능? | §5 |
| 2.6 | 비즈니스 가정 | ROI 추정이 현실적인가? | §6 |
| 2.7 | **MSA 데이터 흐름** | **서비스 분리가 *진짜로* 됐나?** | **§9 (본 문서 핵심)** |

### 2.1 인과 vs 상관

**Q.** "수면 코칭 → 이탈 감소"가 *입증*인가 *가정*인가? BioFit으로 이탈을 X% 줄였다는 데이터가 있나요?

**A.** 본 프로젝트 데이터로는 *인과 미증명*입니다. 인용한 153명 6주 관찰 연구는 *상관* 결과 — *수면 효율이 이탈의 강력한 예측 인자(predictor)* 라는 결과는 도출했지만, *수면 코칭이 이탈을 줄인다*는 인과 효과는 RCT 또는 DiD 설계로 후속 검증 필요. README와 분석 §1·§4에 *"인과 검증 한계"* 박스로 명시 → 면접관이 파고들기 전에 *정직하게 선언*하는 패턴.

### 2.2 모델 신뢰성

**Q.** CatBoost RMSE 얼마이고, SHAP을 의사결정에 써도 되나요?

**A.**
- *수업 특성상* 머신러닝 정확도를 끌어올리기보다 *AI 서비스로서의 구조 확립*에 집중. 수면 질 예측 *로직 자체*는 단순 회귀로 두고 인프라·MSA 결합 지점에 시간 예산을 배분했습니다.
- 그래도 정직성은 확보 — Phase 1에서 시계열 누수 3종 제거(`shift(1).rolling`, `LEAK_VARS` 제외, `target.shift(-1)`) + 마지막 7일 holdout RMSE/MAE + `mean(last 7d)` baseline. legacy path RMSE 1.81, Phase 4 API path 3.80 — 둘 다 baseline 3.92를 이김.
- SHAP은 *모델이 그렇게 본 이유*이지 *인과*가 아님. 카드 표현을 *"이 변수가 efficiency를 낮췄습니다"* → *"가장 비중 두고 본 변수입니다"* 로 정정 (§2.2).

### 2.3 타깃 적합성

**Q.** `sleep_efficiency`만으로 "수면 질"을 대표할 수 있나요? 95% 효율인데 잘 못 잤다고 느끼는 사람이 있는데?

**A.** 단일 타깃 한계 인지. 피츠버그 수면 질 지수(PSQI) 임상 척도에 맞춰 4 차원(주관 / 잠복기 / 시간 / 습관적 효율)으로 분해, *각 차원별 CatBoost* 학습 후 합산하는 구조로 보완.

- *4 모델 분리*는 *해석 우위* (차원별 SHAP 분해 가능) 의도적 선택. 통계 효율 우위인 *multi-output regression*은 비교 baseline.
- 4 차원 *신뢰도가 비대칭* — 잠복기는 Fitbit이 *침대에 눕는 시각*을 정확히 못 줘 근사값, 주관은 feedback 입력률에 의존해 결측 다수. *신뢰도 가중 합산*은 후속 과제로 박제.
- 데이터 측 — `time_in_bed`, `minutes_asleep`, `efficiency`, `sleep_detail`(단계별 분 단위)가 이미 있어 4 차원 산출 가능. 잠복기만 Fitbit `wake` 단계 추정으로 *근사값*임을 정직하게 선언.

### 2.4 검증 디자인

**Q.** 통제군·실험군이 있나요? 추천 시간대를 따랐을 때 효율이 개선됐다는 데이터는?

**A.** 현재 단계에선 N=1 본인 데이터(520일). 비교군 데이터 부재가 한계.

후속 — *within-subject 4주 미니 실험* (2주 처치 + 2주 대조 + washout, 순서 랜덤화) 또는 1개 헬스장 ~60명 RCT. PPT의 *"달성 95%"* 는 *기능 구현 완성도*이지 *서비스 효과*가 아님을 README에 명시.

### 2.5 운영 신뢰성

**Q.** LLM 출력 검증·인증·법규 측면에서 운영 단계 진입 가능한가요?

**A.** 현재는 *프로토타입* 단계. 운영 진입에 필요한 항목을 분석 §5·§9에서 카테고라이즈하고 후속 phase로 박제:
- §5.1 LLM 출력 JSON schema + 폴백 (Phase 6 후보)
- §5.2 의료 면책 + 가드레일 (식단·운동 권고가 한국 의료법 영역과 겹칠 수 있음)
- §5.3 OAuth 서버측화 + RBAC (Fitbit token 평문 텍스트박스는 README가 인정하는 프로토타입 제약)
- §9.4 vLLM health/fallback, §9.6 멱등성 (Phase 3 도입), §9.8 OpenTelemetry (Phase 6 후보)
- §9.9 PIPA 데이터 라이프사이클 (회원 탈퇴 시 cascade 삭제 + 보존 기간 cron + 감사 로그)

### 2.6 비즈니스 가정

**Q.** PPT의 9개월 차 흑자 전환 — 이탈 감소 X% 가정이 깨지면 어떻게 되나요?

**A.** *민감도 분석 부재*가 한계. 이탈 감소 효과가 §1·§4에서 *미증명*이므로 ROI 가정 자체가 흔들림. 후속 — *0/5/10/20% 4개 가정*에 대한 손익 분기 시뮬레이션으로 *"가정이 틀려도 흑자 가능한 영역"*을 표시. 1 헬스장 6개월 파일럿으로 실측 비용·효과를 모델에 보정.

### 2.7 MSA 데이터 흐름 (본 프로젝트 핵심 보완)

**Q.** MSA라 하셨는데 왜 사실상 모놀리스에 가깝다고 했나요? 무엇을 어떻게 바꿨나요?

**A.** 분석 §9.1의 4 깨짐 시나리오 — 새로고침으로 상태 분실, `data_service` 컬럼 rename 시 *런타임 첫 호출 KeyError*, 회원 200명 시 1,800개 동적 테이블, `efficiency` 단위 변경 시 *조용한* 데이터 오염. 결합 지점이 *DB 스키마*였습니다.

Phase 4·5에서 *암묵적 DB 스키마 → 명시적 HTTP 계약 + Pydantic 모델*로 이동:
- `data_service GET /users/{uid}/features` (Phase 4) — `FeatureRow` 18 필드
- `feedback_api GET /users/{uid}/feedback` (Phase 4) — `FeedbackRow`
- `ai_service GET /predictions/{run_id}` (Phase 5) — `PredictionResponse` 13 필드
- `group_service GET /recommendations/{uid}` (Phase 5) — `RecommendationResponse` + `fallback_used` 명시 필드
- `streamlit` 옵트인 시 `psycopg2` SELECT를 ai_service GET 호출로 전환 (Phase 5)

→ 7개 컨테이너 외부 결합 지점 8개 중 8개 ✅. 분석 §9.1 To-Be 90% 진척.

---

## 3. 과거 구조 — 무엇이 어떻게 *깨져* 있었나

> 컨테이너만 분리됐지 *결합 지점은 공유 DB 스키마*. 모놀리스의 단점(런타임까지 못 잡음)과 MSA의 단점(독립 배포·장애 격리 부재)을 *함께* 가진 상태.

### 3.1 As-Is 호출 흐름 (Phase 1 이전)

```text
트레이너 화면 (Streamlit)
  ├─ POST data_service /fetch          → CSV 8개를 {uid}_{suffix} 동적 테이블로 적재
  ├─ POST ai_service /predict          → {uid}_*를 *문자열로 hardcode* 직접 SELECT
  │                                      → CatBoost 학습 → SHAP → vLLM → predictions INSERT
  │                                      → 응답에 message_preview만, 본문은 streamlit이 *DB SELECT 재조회*
  └─ POST group_service /predict       → uid 무시, hardcoded CURRENT_USER_SLOTS만 사용 (분석 §6 결함)

회원 피드백 화면 (streamlit-feedback)
  └─ POST feedback_api /feedback       → {uid}_feedback 동적 테이블 INSERT
```

### 3.2 As-Is의 결정적 결함 — 4 시나리오

| # | 시나리오 | 깨짐 모드 |
|---|---------|---------|
| 1 | 브라우저 새로고침 | 진행 상태가 streamlit `session_state`에만 존재 → DB에 데이터 있는데 [AI 추론] 버튼이 *비활성화*. 서버 측 상태 0. |
| 2 | `data_service` 팀이 컬럼 rename | `ai_service`가 *런타임 첫 호출*에서 `KeyError`. CI는 통과. *MSA의 핵심 가치인 독립 배포가 정반대로 깨짐*. |
| 3 | 회원 200명 도달 | `pg_class` 카탈로그에 약 1,800개 테이블. `pg_dump`·모니터링·ORM reflection 모두 비례해 무거워짐. |
| 4 | `efficiency` 단위 변경 (`[0,1]` → `[0,100]`) | LLM 프롬프트가 *조용히* "예측 효율 8245%"를 받음. 런타임 에러 없이 데이터 오염. |

### 3.3 모델 측 결함 (Phase 1·2가 다룸)

| 결함 | 발견 위치 | 결과 |
|------|---------|------|
| **시계열 누수 — rolling이 *오늘* 포함** | `add_roll7` (`rolling(7).mean()` without shift) | 행 t의 rolling feature에 target의 정보가 새어듦 |
| **시계열 누수 — 동일 측정 사건 변수** | `stage_deep`, `stage_light`, `stage_rem`, `stage_wake`, `time_in_bed`, `wake_count`가 features에 잔존 | 모델이 *항등식*을 외움 |
| **시계열 누수 — target이 오늘 시점** | `cat.predict(X.tail(1))` | forecast가 아니라 *현재 정합* |
| **train/test 분리 0** | 학습 직후 같은 데이터 마지막 행 예측 | 일반화 오차 추정 0건 — RMSE 답할 수 없음 |
| **운동 시간대 LLM 환각** | 프롬프트 끝의 `"운동 시작시간: 20:00, 운동 종료시간: 20:30"` 형식 강제 | LLM이 그대로 복사 → 모든 회원에게 동일 슬롯 |
| **재현성 0 — 메타 미저장** | `predictions(id, uid, run_id, note, message, created_at)` | 어떤 모델·프롬프트·LLM 파라미터로 만들었는지 0건 |
| **품질 평가 루프 미설정** | `predictions.message`가 적재되지만 thumbs up/down 0 | 토큰 비용은 추적, 가치는 미추적 |

### 3.4 운영형 결함 (Phase 3 이후가 다룸)

| 결함 | 영향 |
|------|------|
| `db/init/*.sql`은 첫 부팅 1회만 실행 | 운영 DB 컬럼 추가 = `down -v` (모든 회원 데이터 손실) 또는 수동 SQL |
| 멱등성 0 / 부분 실패 미처리 | vLLM timeout 시 토큰 소비됨 + predictions INSERT 안 됨 → 정합성 깨짐 |
| 동기 호출 5분 블로킹 | 트레이너 UI 5분 멈춤 + worker 점유 + reverse proxy timeout + 토큰 누수 + 재시도 중복 |
| streamlit이 `predictions` 테이블 직접 SELECT | streamlit에 psycopg2 의존성 + 다른 서비스 DB로 *직접 침투*하는 결합 |

---

## 4. 5단계 보완 — 무엇을, 왜 그렇게 바꿨나

> 모든 phase의 안전 원칙: **추가만, 환경 변수 default 0, 자동 fallback** — 즉 commit 받아도 운영 동작은 변하지 않고, 옵트인 시에만 새 path 활성. expand-contract 패턴의 *expand 단계만* 진행 (contract는 Phase 6+).

### 4.1 Phase 1 (commit `45bef5b`) — 모델 정직성

| 항목 | Before | After | 면접 답변 키 |
|------|--------|-------|------------|
| §8.1 시계열 누수 | rolling 오늘 포함 + stage_* 잔존 + target 오늘 | `shift(1).rolling(7)` + `LEAK_VARS` 명시 제외 + `target.shift(-1)` (t+1 forecast) | "feature가 target과 같은 시점이면 학습이 의미 없다는 걸 *인지하고 제거*했습니다" |
| §2.1 train/test holdout | 없음 | 마지막 7일 holdout + RMSE/MAE + baseline `mean(last 7d)` | "단순 평균 baseline을 *정량적으로* 이기는지 입증" |
| §1 README 인과 표현 | "BioFit은 이탈률 감소를 *위해*" | "*목적*으로" + 인과 검증 한계 박스 (RCT/DiD 후속) | 인과/상관 구분 가능한 사람으로 인식 |
| predictions 메트릭 컬럼 | (id, uid, run_id, note, message, created_at) | + `rmse_test`, `mae_test`, `data_window_end`, `feature_set_version` | 호출 단위 회귀 추적 가능 |
| 노트북 8_1_leakage_audit | 없음 | 4 시나리오(A·B·C·D) + baseline E | 누수 제거 효과를 *수치*로 증명 |

**Phase 1의 핵심 메시지**: *누수 있는 모델이 만든 비현실적으로 낮은 RMSE에 회원 신뢰를 거는 대신, 정직한 일반화 오차를 측정.*

### 4.2 Phase 2 (commit `0ef8d51`) — 데이터 회귀 + 메타 추적 + 평가 루프

| 항목 | Before | After | 면접 답변 키 |
|------|--------|-------|------------|
| §8.2 운동 시간대 추천 | LLM이 환각으로 산출, 형식 강제로 모든 회원에 동일 슬롯 | `recommend_workout_window(uid, train_master, k=3)` — 회원의 효율 상위 30% 일자의 시간대별 활동 합계 → top-k. 데이터 부족 시 cohort fallback. 프롬프트는 변수화. | "추천 *결정*은 코드, *설명*만 LLM" — 비결정성·환각 격리 |
| §8.5 메타 컬럼 | 모델/프롬프트/LLM 파라미터 추적 0 | `model_version`, `prompt_hash` (8 char), `llm_params` (JSONB), `recommended_slot_json` (JSONB) | "프롬프트 바꾼 뒤 품질 좋아졌단 걸 어떻게 보였나요?" 답변 가능 |
| §8.3 평가 루프 | thumbs up/down 0 | `predictions_feedback (run_id FK CASCADE, rating 1-5, useful, comment, rated_by)` + `POST /predictions/{run_id}/feedback` (422/409/404 분기) | closed loop — 코칭 품질을 *데이터로* 측정 |
| MODEL_VERSION 상수 | 없음 | `"phase2_§8.2_window_regression"` (inference 변경마다 bump) | A/B 테스트 인프라 토대 |

### 4.3 Phase 3 (commit `25ff257` + `effce70`) — 운영형 토대

> 시간 예산 ~15h (Phase 1·2 합산보다 1.5×). *마이그레이션 도구 + DB 정규화 시작 + 분산 정합성*.

| 항목 | Before | After | 면접 답변 키 |
|------|--------|-------|------------|
| §9.7 Alembic | `db/init/*.sql`이 첫 부팅 1회만 실행 → 운영 DB 컬럼 추가 = 데이터 손실 | `alembic.ini` + `migrations/env.py` + 3 versions (001 baseline empty / 002 fitbit_daily_features / 003 model_runs+idempotency_log) + 1회성 `migrate` 컨테이너 + db healthcheck + `service_completed_successfully` 의존성 | "운영 DB 스키마 어떻게 바꾸시나요?" → up/down 페어 + expand-contract |
| §9.1 expand | 회원 200명 시 ~1,800개 동적 테이블 | `fitbit_daily_features (user_id, date, ...)` wide-format + `(user_id, date)` PK + `ON CONFLICT UPDATE`. `read_daily_db`에 `USE_NORMALIZED_FEATURES` 분기, `csv_to_db`에 `DUAL_WRITE_NORMALIZED` dual-write helper | expand-contract 패턴 정석 — 옵트인 default 0 |
| §9.6 멱등성 | 같은 입력 두 번 호출 = 두 번 학습 + 두 번 vLLM + 두 번 INSERT | `Idempotency-Key` 헤더 hit 체크 → 기존 응답 즉시 반환. `model_runs(run_id, status, current_step, error, retry_count)` 단계별 상태 머신 (`queued → running → succeeded/failed`) | AWS API Gateway·Stripe와 같은 패턴 |
| (post-verify) vLLM 모델 ID | `./llama3` hardcode | `LLM_MODEL = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-20b")` | 환경별 모델명 차이 흡수 |
| (post-verify) azm prefix | CSV `total/fatburn/cardio` vs DB `azm_total/...` 불일치 | `_DUAL_WRITE_COLUMN_RENAME` + `_apply_legacy_rename` 양방향 | Phase 3 latent defect를 Phase 4 검증에서 발견·즉시 수정 |

**Phase 3의 안전 속성**: env flag default 0 + 모든 처리 try/except로 감쌈 → *마이그레이션이 아직 적용 안 된 운영 DB*에서도 깨지지 않음.

### 4.4 Phase 4 (commit `f32975e`) — 입력 쪽 HTTP 계약

> *결합 지점이 암묵적 DB 스키마 → 명시적 HTTP 계약 + Pydantic*.

| 항목 | Before | After | 면접 답변 키 |
|------|--------|-------|------------|
| data_service exposes | `/fetch`만 | `GET /users/{uid}/features?window=N` (max 1000) + `FeatureRow` Pydantic 18 필드 | OpenAPI 자동 생성 → 외부 클라이언트가 *별도 합의 없이* 같은 계약 사용 |
| feedback_api exposes | `/feedback`만 | `GET /users/{uid}/feedback` + `FeedbackRow` Pydantic | 같은 패턴 |
| ai_service consume | `read_table('{uid}_*')` 직접 SELECT | 3-tier `read_daily_db`: `USE_DATA_SERVICE_API` > `USE_NORMALIZED_FEATURES` > legacy. `_fetch_features_via_api` helper. 자동 fallback + `logger.warning` | "data_service팀이 컬럼 바꿔도 ai_service가 깨지지 않습니다" |
| 검증 결과 | 동등성 검증: rmse=1.81 (legacy) vs 3.80 (API path) | 차이 원인 = *minute-level + sleep_detail 누락* (Phase 4 spec scope 한계). 둘 다 baseline 3.92 이김 | "옵트인 path가 baseline은 이긴다는 사실 자체가 옵트인 의미를 입증" |
| 검증 도구 | 별도 도구 없음 | `window=1000` 파라미터 — 23RK3S 데이터가 2024-01-01~2025-05-20인데 `CURRENT_DATE - 7d`는 빈 결과 → 마지막 N일 정렬로 fix | *실제 데이터 분포에 맞춘 SQL* |

**Phase 4의 trade-off 결정 (Q5)**: shared `biofit-contracts` 패키지 vs. 인라인 복제 — *2명 monorepo 환경에선 인라인 복제 + `@contract` 주석*이 정직. trigger는 100명 회원 또는 5명 팀.

### 4.5 Phase 5 (commit `21b6525`) — 출력 쪽 + 클라이언트 측 + §6 fix

> 7개 컨테이너 외부 결합 지점 8개 중 8개 ✅ (5개가 Phase 4·5에서 신규 HTTP 계약).

| 항목 | Before | After | 면접 답변 키 |
|------|--------|-------|------------|
| ai_service exposes | POST /predict만 | `GET /predictions/{run_id}` + `PredictionResponse` Pydantic 13 필드. JSONB 자동 deserialize + 방어적 `json.loads` | DB row 영구 컬럼만 노출 (baseline_rmse는 호출 시점 진단이라 GET에 없음) |
| group_service exposes + §6 fix | POST /predict가 uid 무시, hardcoded slot | `GET /recommendations/{uid}` — `preferred_slots`에서 *실제* 회원 슬롯 조회. `fallback_used: bool` 명시 필드. `_overlap_minutes` 30분 기준 | "silent fallback은 *기능적*으론 작동하지만 *제품 품질*은 떨어진다" |
| streamlit 클라이언트 | `psycopg2`로 `predictions` 직접 SELECT | `USE_PREDICTIONS_API=1` 옵트인 시 ai_service `GET /predictions/{run_id}` 호출. 실패 시 자동 SELECT fallback | "DB는 *절대* 직접 접근 안 함"이라는 To-Be 모델 진척 |
| 디버깅 일화 (Q9) | — | pandas `iterrows`의 `row.name`이 *컬럼 'name'이 아닌 row index*를 반환 → Pydantic ValidationError. `p["name"]` dict-style + `_row_get` helper로 fix | Pydantic + FastAPI의 type 강제가 *runtime first call*에서 결함을 잡아준 가치 |

---

## 5. 서비스 간 데이터 소유권 모델 (분석 §9.1 To-Be)

```text
data_service
  owns:     fitbit_raw, fitbit_daily_features, ingestion_runs
  exposes:  POST /fetch
            GET  /users/{uid}/features?window=N         ← Phase 4

feedback_api
  owns:     predictions_feedback, sleep_feedback, {uid}_feedback (legacy)
  exposes:  POST /feedback
            GET  /users/{uid}/feedback                   ← Phase 4
            POST /predictions/{run_id}/feedback          ← Phase 2

ai_service
  owns:     predictions, token_usage, model_runs, idempotency_log
  consumes: data_service /users/{uid}/features
            feedback_api  /users/{uid}/feedback
  exposes:  POST /predict (Idempotency-Key 헤더 지원)    ← Phase 3
            GET  /predictions/{run_id}                   ← Phase 5

group_service
  owns:     preferred_slots, group_sessions, match_history, users
  exposes:  POST /predict (legacy hardcoded slot 유지)
            GET  /recommendations/{uid}                  ← Phase 5 (§6 fix)
```

**핵심 원칙**: *자기 소유 테이블에는 직접 access OK, 다른 서비스 소유 테이블에는 API 경유.* ai_service가 `predictions`에 직접 INSERT하는 건 자연스러운 *서비스 내부 구현* — 다른 서비스가 그 테이블에 접근하는 게 위반이고, Phase 5에서 그것이 끊김.

---

## 6. 면접 답변 패턴 — 자주 나오는 10 질문 압축

| # | 질문 | 1줄 답변 키 |
|---|------|----------|
| 1 | "MSA라 하셨는데 왜 모놀리스에 가깝다고 했나요?" | 분석 §9.1의 4 깨짐 시나리오 (새로고침·rename·1800 테이블·단위 변경). 결합 지점이 *DB 스키마*였습니다. |
| 2 | "RMSE 얼마인가요?" | legacy 1.81, Phase 4 API path 3.80. 둘 다 baseline 3.92 이김. *Phase 1 holdout이 선결 조건*이었어요. |
| 3 | "feature와 target이 같은 시점이면 학습 의미 있나요?" | 인지하고 §8.1에서 제거 — `shift(1).rolling(7)` + `LEAK_VARS` + `target.shift(-1)`. |
| 4 | "운동 시간대를 어떤 알고리즘으로 뽑나요?" | LLM 환각 아님. §8.2 — 효율 상위 30% 일자의 시간대별 활동 합계 top-k. 데이터 < 14일은 cohort fallback. |
| 5 | "운영 DB 스키마 어떻게 바꾸시나요?" | Alembic + up/down 페어 + 1회성 migrate 컨테이너. NOT NULL 추가는 expand-contract 3 phase. |
| 6 | "vLLM timeout 시 토큰·결과 정합성?" | `Idempotency-Key` 헤더 + `model_runs` 단계별 상태 머신. 같은 키 재호출 시 vLLM/CatBoost 재실행 0. |
| 7 | "data_service팀이 컬럼 바꾸면?" | Phase 4 후엔 `FeatureRow` Pydantic 모델이 계약. Field 제약과 *함께* 갱신해야 PR 통과. OpenAPI도 자동 갱신. |
| 8 | "프롬프트 바꾼 뒤 품질 개선을 어떻게 입증?" | §8.5 `model_version` + `prompt_hash` + §8.3 `predictions_feedback` thumbs up/down. SQL 한 줄로 모델별 RMSE·평점 분포 비교. |
| 9 | "5분 동기 블로킹은 어쩔 건가요?" | §8.6 — `POST /predict-jobs` 202 + job_id, `GET /predict-jobs/{id}` 폴링, `BackgroundTasks` 또는 Celery+Redis. Phase 6 후보. |
| 10 | "회원 탈퇴 시 데이터 삭제 흐름?" | 현재는 *카탈로그 grep* 수준. Phase 6+에서 §9.2 정규화로 `WHERE user_id=?` 한 줄 + `DELETE /users/{uid}` cascade + 보존 기간 cron + 감사 로그. |

---

## 7. 의도적으로 *안 한* 것 (Non-Goals — 면접에서 "왜 이건 안 했나요?" 답변)

| 항목 | 안 한 이유 | 언제 trigger |
|------|----------|------------|
| shared `biofit-contracts` 패키지 | 2명 monorepo에 운영 비용 과대. 인라인 복제 + `@contract` 주석으로 의도 박제 | 100+ 회원 또는 5+ 팀 |
| legacy DB direct path *폐기* (contract 단계) | 옵트인 검증 충분치 않음. expand만 진행 | dual-path 옵트인 운영 검증 후 |
| §8.6 비동기 prediction job (`/predict-jobs`) | 결합 지점 정리(*what*)와 호출 패턴(*how*)은 다른 axis | Phase 6 |
| §9.4 vLLM health/fallback | Phase 6 후보 | 동시 사용자 N>3 시점 |
| §9.8 OpenTelemetry + structlog + Prometheus | Phase 6 후보 | 운영 단계 진입 시 |
| §5.1 LLM JSON schema + 폴백 | Phase 6 후보 | LLM 형식 깨짐이 잦은 운영 신호 발생 시 |
| minute-level + sleep_detail 정규화 | Phase 4 RMSE 손실 원인이지만 daily expand로 충분히 baseline 이김 | Phase 6 |
| `predictions.features_source TEXT` | 옵트인 path 추적용. 현재는 logger.warning만 | Phase 6 |
| RCT / DiD 인과 검증 | 1주 코드 작업 범위 외 | Phase 7 (실험 기간 포함, 본인 데이터 4주 within-subject) |
| OAuth + RBAC + PIPA gap analysis | 인증 부재는 README가 인정하는 *프로토타입* 단서로 보호 | 운영 단계 진입 |

---

## 8. 누적 commit 흐름 (timeline 답변용)

```
21b6525  feat(phase 5)  — 나머지 서비스 MSA 경계 + §6 group_service uid fix
f32975e  feat(phase 4)  — MSA boundary hardening via HTTP API contracts
effce70  fix(post-verify) — LLM_MODEL_NAME env + azm CSV column rename for dual-write
25ff257  feat(phase 3)  — Alembic + fitbit_daily_features expand + idempotency/model_runs
0ef8d51  feat(phase 2)  — window regression + meta tracking + feedback loop
45bef5b  feat(phase 1)  — 시계열 누수 제거 + train/test holdout + 인과 표현 정정
```

각 commit은 *추가만*, env flag default 0, 자동 fallback. 어느 phase commit을 받아도 *기존 운영 동작이 깨지지 않음*이 보장.

---

## 9. 면접 마무리 한 줄

> "이 프로젝트는 *프로토타입* 단계로 인과 효과는 미증명이지만, 약점을 *분석 문서로 27개 카테고라이즈*하고 *5단계 commit으로 절반 가까이* 처리했습니다. 남은 절반은 *Phase 6+ 후속 과제로 박제*돼 있고, 각 phase의 trade-off 결정과 *왜 어떤 건 일부러 안 했는지*가 README와 phase별 리포트에 함께 적혀 있어 시니어 면접관에게 *겸손한 정직*의 시그널로 작동하도록 설계했습니다."

---

## 부록 — 기술 스택 cheat sheet

| 영역 | 도구 | 본 프로젝트에서 쓴 곳 |
|------|------|--------------------|
| 웹 프레임워크 | FastAPI | data, feedback-api, ai_service, group_service |
| UI | Streamlit | 트레이너용 (8501), 회원 피드백용 (8502) |
| DB | PostgreSQL 13 | 단일 컨테이너 공유 (Phase 5 까지는 *논리적 소유권* 분리만) |
| 마이그레이션 | Alembic | Phase 3 도입, baseline 001 empty + 002·003은 IF NOT EXISTS |
| ORM/드라이버 | SQLAlchemy + psycopg2 | data_service에 SQLAlchemy text(), ai_service는 psycopg2 직접 |
| 데이터 검증 | Pydantic | Phase 4·5에서 모든 endpoint에 response_model |
| ML | CatBoost (수면 효율 회귀), SHAP (top-k 기여 변수) | ai_service `coach_main` |
| LLM | vLLM (외부 GPU, OpenAI-compatible) | `openai/gpt-oss-20b`, temperature=0.3, top_p=0.30 |
| 컨테이너 | Docker Compose v3.9 | 7개 + 1개 1회성 migrate, db healthcheck + service_completed_successfully |
| 데이터 흐름 | Fitbit CSV → PostgreSQL → CatBoost+SHAP → vLLM → Streamlit 카드 | — |


## 10. 예상 질문 — 도메인 깊이 보강

> §6의 *MSA·운영* 답변 외에 *도메인·모델링* 깊이를 파고들 후속 질문 모음. 답변 키만 짧게.

### Q1. 수면 효율 예측의 타당성 — 현재 입력 변수가 *진짜로* efficiency를 설명하나요?

**A.** 현재 22개 features:
- *심박수·HRV* — `resting_hr`, `bpm`, `rmssd_mean`, `hf_mean`, `lf_mean`
- *운동량* — `steps`, `distance`, `calories`, `azm_total/fatburn/cardio`
- *운동 시간대 (7개)* — `steps_morning(06–12)`, `steps_afternoon(12–18)`, `steps_evening(18–24)`, `steps_night(00–06)`, `last_active_hour`, `pre_sleep_steps_0_2h`, `pre_sleep_steps_2_4h`
- *수면 시간대 (5개)* — `bedtime_hour`, `waketime_hour`, `bedtime_dev_min`, `waketime_dev_min`, `sleep_duration_h`

SHAP에서 **시간대 변수군이 mean|SHAP| 합의 55.2%** 차지 → "언제 활동·수면을 했는가"가 본 회원의 efficiency 변동의 가장 강한 신호. 누설 차단으로 `minutes_asleep`, `time_in_bed`, `stage_*`, `cnt_*`는 features에서 제외 (§8.1) — 그 결과 RMSE가 *나빠지는 게 정상*이고, 그 나빠진 RMSE가 진짜 일반화 오차의 추정값.

### Q2. PSQI 4 차원 분리 — 4 모델 분리 vs. multi-output regression?

**A.** 1차로 *4 모델 분리* (해석 우위) → 2차로 multi-output을 *비교 baseline*. 4 차원이 서로 *비독립*이므로 multi-output이 통계 효율은 우위지만 차원별 SHAP의 명료성이 떨어짐. *우리는 의도적으로 해석성을 우선*했다는 답변 패턴. Baseline은 *PSQI 합의 mean* (naive) — 분석 §2.1 패턴을 4 차원에 그대로 적용.

### Q3. 운동 시간대 변수가 중복되지 않나? — `recommend_workout_window` vs `pre_sleep_steps_*`

**A.** 부분적으로 겹침. 다만 *축이 다름*:
- `recommend_workout_window`: *벽시계 좌표* + *처방* + *운영 path* (LLM 프롬프트 주입)
- `pre_sleep_steps_*`: *취침 상대 좌표* + *진단* + *실험 path* (CatBoost feature)

→ 보강 후보 — `recommend_workout_window`의 `gym_hours` 필터를 *avg_sleep 기준 -2~-6h 윈도우*로 바꾸면 두 변수의 *축이 통일*돼 *추천*과 *SHAP 진단*이 서로의 검증이 됨. Phase 6+ 박제.

### Q4. 잠복기 측정의 한계 — Fitbit이 침대에 *눕은* 시각을 못 주는데?

**A.** 정직한 한계. 코드의 `sleep_time` (`read_sleep_window_db`)은 *Fitbit이 인식한 첫 비-wake 단계 시작*이라 PSQI의 *잠든 시각*에 가깝고, *침대에 눕은 시각*은 미보유. 보강 — feedback UI에 *"어제 침대에 누운 시각"* 한 문항 추가하면 회원 *주관 입력*과 결합해 *근사 잠복기* 산출 가능.

### Q5. 22개 features 중 *추가하면 좋을* 것?

**A.** AZM 강도 기반 binary feature:
- `exercised_morning/afternoon/evening` — `azm_*_min >= 10`인지의 0/1 (산책·자세변경 노이즈 제거)
- `hours_workout_to_bed` — *마지막 유의미 운동* (azm ≥ 10) ~ 취침 거리 연속 변수

Threshold 효과(*운동을 했는가*)와 부드러운 dose-response(*취침까지 거리*)를 추가로 잡음. 트레이너 카드의 actionable 메시지(*"오후 운동 0건 → 시도 권장"*) 생성에도 직접 도움. Phase 6+ 1일 작업.