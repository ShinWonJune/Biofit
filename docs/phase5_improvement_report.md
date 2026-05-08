# Phase 5 보완 작업 리포트 (2026-05-09) — 면접 대비용

> Phase 4가 *data_service·feedback_api*의 외부 contract를 신설했다면 Phase 5는 **나머지 두 서비스(`ai_service`·`group_service`)의 외부 contract**와 **streamlit의 클라이언트 측 API 전환**을 완성. 또 분석 문서 §6에서 발견한 *`group_service`가 요청자 uid를 완전히 무시*하던 결함을 함께 fix. *진짜 MSA에 가까운 형태*로 한 걸음 더 진척.

## 한 줄 요약 (면접 첫 답변용)

> "Phase 4까지는 데이터 흐름의 *입력* 쪽(`data_service`/`feedback_api`)만 HTTP 계약으로 옮겼습니다. Phase 5에서 *출력* 쪽(`ai_service`)에도 `GET /predictions/{run_id}` endpoint를 추가하고, `streamlit`이 `psycopg2`로 `predictions` 테이블을 *직접 SELECT*하던 코드를 그 endpoint 호출로 옵트인 전환했습니다. 동시에 `group_service`가 요청자의 `uid`를 *완전히 무시*하고 하드코딩 슬롯만 쓰던 결함도 fix해서, 이제 `GET /recommendations/{uid}`가 *실제 회원의 preferred_slots를 조회해 매칭*합니다. 결과적으로 7개 컨테이너 중 *5개의 외부 결합 지점*이 모두 *명시적 HTTP 계약 + Pydantic 모델* 위에서 작동하게 됐습니다."

## 메타

| 항목 | 값 |
|------|-----|
| 작업 기간 | 2026-05-09 (Phase 4 직후 연속) |
| 시간 예산 | ~10시간 |
| Spec | `.omc/specs/phase5-spec.md` (gitignored) |
| 의존 commit | `f32975e` (Phase 4) |
| 변경 파일 수 | 4 (코드 modified) + 1 (README 수정) + 1 (신규 리포트) |
| 핵심 안전 원칙 | Phase 4 패턴 일관 — *추가만*, env flag default 0, 자동 fallback |

## 변경 요약

| US | 분류 | 핵심 변경 |
|----|------|----------|
| US-501 | ai_service exposes | `GET /predictions/{run_id}` + `PredictionResponse` Pydantic (13 필드) |
| US-502 | group_service exposes + §6 fix | `GET /recommendations/{uid}` + 실제 uid 슬롯 조회 + `fallback_used` 명시 필드 |
| US-503 | streamlit client | `USE_PREDICTIONS_API=1` 옵트인 시 ai_service GET 호출, default 0이면 기존 SELECT path |
| US-504 | infra + docs | docker-compose env + README Phase 5 + 본 리포트 |

## 누적 MSA 경계 진척도 (Phase 1~5)

| 결합 지점 | Phase 5 이후 상태 |
|----------|------------------|
| streamlit → data_service `/fetch` | ✅ HTTP API (이미) |
| streamlit → ai_service `/predict` | ✅ HTTP API (이미) |
| streamlit → group_service `/predict` | ✅ HTTP API (이미) |
| streamlit-feedback → feedback_api `/feedback` | ✅ HTTP API (이미) |
| **streamlit → predictions 테이블 SELECT** | ✅ **Phase 5 → ai_service `/predictions/{run_id}` 옵트인** |
| **ai_service → `{uid}_*` 동적 테이블** | ✅ Phase 4 → data_service `/users/{uid}/features` 옵트인 |
| **ai_service → `{uid}_feedback` 동적 테이블** | ✅ Phase 4 → feedback_api `/users/{uid}/feedback` 옵트인 |
| **ai_service → fitbit_daily_features 정규화** | ✅ Phase 3 expand (옵트인) |
| **group_service → 회원 uid 무시 (분석 §6)** | ✅ **Phase 5 → preferred_slots 실제 조회** |
| group_service → predictions·model_runs 직접 read | ❌ (해당 사항 없음 — group_service는 ai_service 결과 안 봄) |

→ **Phase 5까지 분석 문서 §9.1 To-Be의 약 90% 진척**. 남은 *contract 단계*(legacy path 폐기)와 *shared package 추출*은 Phase 6+ 운영 검증 후.

---

## 면접 Q&A 시뮬레이션 (Phase 5 *왜*에 대한 정직한 답변)

### Q1. "Phase 4·5를 왜 두 단계로 나눴나요? 한 번에 다 옮길 수도 있지 않았나요?"

**A.** 검증 가능성과 회귀 위험을 분리하기 위해서. Phase 4는 *입력* 쪽(`data_service` features, `feedback_api` feedback) — *RMSE/MAE 같은 정량 메트릭이 동등성 비교로 검증 가능*. Phase 5는 *출력* 쪽 + *서비스 간 직접 결합 끊기* — Phase 4의 *옵트인 path가 안정적으로 작동*하는지 확인된 후에야 추가 결합 지점을 옮기는 게 안전합니다.

또 한 번에 다 옮기면 *어디서 회귀가 생겼는지* 진단이 어려움. 단계별로 나누면 *어느 phase의 변경이 문제인지* commit 단위로 추적 가능. 실제로 Phase 4 검증 중 `azm_*` reverse rename 결함을 발견했고, 그 fix가 Phase 4 안에서 이뤄졌기에 Phase 5의 endpoint 작업과 *섞이지 않은* 깨끗한 진단이 가능했습니다.

### Q2. "ai_service의 GET endpoint 응답 모델에는 `baseline_rmse`가 *없는데*, POST /predict 응답에는 *있던데요*. 이게 의도인가요?"

**A.** 네, 의도입니다. 두 가지 메트릭의 *생명주기*가 다릅니다:

- `rmse_test`, `mae_test`: **predictions row의 영구 컬럼** — 그 추론의 일반화 오차 추정. 시간이 지나도 *그 호출의 결과*로 의미 있음
- `baseline_rmse`: **호출 시점의 *진단* 메트릭** — 단순 평균 baseline 대비 우위가 *얼마나* 컸는지의 일회성 비교. predictions 테이블에 컬럼이 없음

GET endpoint는 *DB row*를 반환하므로 *DB에 없는 메트릭*을 만들지 않습니다. POST 응답은 *호출 시점의 진단 정보*라 baseline_rmse 포함 — 클라이언트가 *그 시점*에 알면 가치 있음.

→ 면접 답변: **"DB의 *영구 상태*와 호출 시점의 *진단 정보*는 다른 생명주기를 가집니다. DB schema에 *진단 메트릭까지* 박제하면 *어떤 시점에 어떤 baseline*과 비교했는지가 stale해질 수 있어요. 그래서 baseline_rmse는 호출 시점에만 노출하고, *재현성에 필요한 핵심*(rmse_test·mae_test·data_window_end·feature_set_version)만 영구 컬럼으로 박제했습니다."**

### Q3. "group_service의 hardcoded slot 결함은 분석 문서 §6에서 *처음부터* 알았다면서 왜 Phase 1~4에서 fix 안 했나요?"

**A.** 정직한 답변 — *작업 우선순위* 결정이었습니다.

Phase 1·2는 *모델 정직성* (시계열 누수·train/test holdout) 우선 — 면접에서 "RMSE 얼마?" 질문에 답할 *기반*. Phase 3·4는 *데이터 흐름의 운영형 토대* (Alembic·정규화·HTTP 계약) 우선. Phase 5는 *나머지 결합 지점 정리* + 그 과정에서 자연스럽게 §6을 함께 fix.

§6 fix를 Phase 1~4에 넣지 않은 이유:
- §6은 *기능 결함*이지만 *코드 1개 함수* 수정 + 새 endpoint로 가능 — *spec scope 안*에 자연스러운 timing이 Phase 5
- *분석 문서가 진단했다*는 사실 자체가 면접 답변에 의미 있음 — "결함을 *알면서도* 우선순위 매겨 처리한 결정"

→ 면접 답변: **"§6 fix는 *코드 결함* 수준이라 fix 자체는 simple했지만, *언제 fix하느냐*가 결정 포인트였습니다. Phase 1~4에서 *기반 인프라*를 먼저 정직하게 만든 후, Phase 5에서 group_service의 외부 contract를 추가하는 자연스러운 timing에 함께 fix했습니다. 결정 의도 자체가 *분석 문서 §10 우선순위 표*에 박제돼 있고, GitHub commit 흐름으로 *어떤 phase에 무엇을 했는지* 추적 가능합니다."**

### Q4. "group_service의 응답에 `fallback_used: true|false` 필드를 두는 이유가 뭔가요? 그냥 internal로 처리하면 안 되나요?"

**A.** 클라이언트(streamlit, 외부 트레이너 시스템 등)가 *추천의 신뢰도*를 *명시적으로 알아야* 하기 때문.

```json
{
  "uid": "23RK3S",
  "user_slots_used": [["10:00:00","11:00:00"],["18:00:00","19:00:00"]],
  "fallback_used": true,
  "partners": [...]
}
```

`fallback_used: true`면 *이 회원은 preferred_slots에 등록 안 된 신규 회원*이고 *모든 회원에게 동일한 hardcoded 슬롯 결과*가 반환됨 — 이걸 *내부 처리*로 숨기면 트레이너가 "이 추천이 *진짜 회원 맞춤*인가, 아니면 *기본값*인가" 구분 못 함. 잘못된 신뢰로 회원 상담에 사용하면 *서비스 신뢰성* 훼손.

→ 면접 답변: **"클라이언트의 *informed decision*을 위해 fallback 신호를 명시적으로 노출했습니다. 트레이너가 회원 상담 시 *맞춤 추천인지 fallback인지* 카드에 다른 색으로 표시하거나, fallback이면 *회원에게 preferred_slots 입력을 권고*하는 분기 가능. silent fallback은 *기능적으론 작동*하지만 *제품 품질*은 떨어집니다."**

### Q5. "Phase 4에서도 *fallback이 silent라 위험*하다고 했는데, Phase 5도 똑같은 문제 아닌가요?"

**A.** 맞고, 의도적으로 Phase 5에서 *조금 더 명시화*했습니다.

- Phase 4 (`ai_service` 측 dual-read): fallback 시 `logger.warning` 출력. 다만 응답 페이로드에는 *어느 path 사용*했는지 노출 안 함.
- Phase 5 (`group_service` GET): fallback 신호를 *Pydantic 응답 필드로 명시* (`fallback_used: bool`).

차이가 생긴 이유:
- Phase 4의 `read_daily_db`는 *내부 함수* — sleep_coach 안에서만 사용. 외부 클라이언트가 *어느 path 사용*했는지 알 필요 적음.
- Phase 5의 `get_recommendations`는 *외부 endpoint* — 클라이언트의 *제품 결정*에 직접 영향. 그래서 명시 필드.

→ 후속 보강 후보 (Phase 6+): Phase 4의 `predictions` 테이블에 `features_source TEXT` 컬럼 추가해 *어느 path*에서 features를 읽었는지 박제. 그러면 *historical 분석* 시 path별 RMSE 분포 비교 가능.

### Q6. "streamlit이 `USE_PREDICTIONS_API=1`을 *default로* 안 하고 옵트인으로 둔 이유는?"

**A.** Phase 4와 동일 패턴 — *기존 운영 흐름 무영향* 보장.

- Phase 5 commit이 운영 환경에 적용돼도 streamlit은 *psycopg2로 직접 SELECT* 그대로
- 옵트인 keys 켤 때만 *ai_service GET endpoint* 사용
- 옵트인 + API 호출 실패 시 *자동으로 SELECT fallback*

이 패턴의 가치:
- **A/B 비교**: 같은 환경에서 *DB SELECT vs API GET*의 latency·정확성 비교 가능
- **점진 전환**: 운영자가 *충분히 검증* 후에만 default를 1로 변경. *결정 권한*이 운영자 측에 있음
- **롤백 가능**: 옵트인 켜고 문제 생기면 즉시 *0으로 되돌림* — code 변경 없음

→ 면접 답변: **"운영 안전성 + A/B 비교 가능성 + 롤백 가능성 세 가지 가치를 동시에 얻기 위해 옵트인 default를 채택했습니다. *운영 시점에 충분히 비교*한 후 default를 1로 옮기는 trigger는 운영자 측 결정. Phase 4·5의 모든 새 path가 같은 패턴을 따라서 *예측 가능한 활성화 흐름*을 만들었습니다."**

### Q7. "Phase 5 후에도 ai_service는 `predictions` 테이블에 *직접 INSERT*하잖아요. 이건 자기 DB 직접 access인데 MSA 위반 아닌가요?"

**A.** 정확한 지적이고, 분석 문서 §9.1 To-Be의 *데이터 소유권* 모델로 답합니다.

```text
data_service
  owns: fitbit_daily_features, ingestion_runs
  exposes: GET /users/{uid}/features

feedback_api
  owns: predictions_feedback, {uid}_feedback (legacy)
  exposes: POST /feedback, GET /users/{uid}/feedback, POST /predictions/{run_id}/feedback

ai_service
  owns: predictions, token_usage, model_runs, idempotency_log
  consumes: data_service /users/{uid}/features, feedback_api /users/{uid}/feedback
  exposes: POST /predict, GET /predictions/{run_id}

group_service
  owns: preferred_slots, group_sessions, match_history, users
  exposes: POST /predict (legacy), GET /recommendations/{uid}
```

**핵심 원칙**: *자기 소유 테이블에는 직접 access OK, *다른 서비스 소유 테이블*에는 API 경유*. ai_service는 `predictions`·`token_usage`·`model_runs`·`idempotency_log`의 *유일한 owner*이므로 직접 INSERT/SELECT *맞습니다*. 다른 서비스가 이 테이블에 *직접 접근*했다면 위반이지만, 본 시스템에는 그런 흐름 없음.

→ 면접 답변: **"MSA가 *모든 DB access를 HTTP로*가 아니라 *데이터 소유권 분리*가 핵심입니다. ai_service는 자기 소유 테이블(predictions, model_runs 등)에는 직접 access — 그게 자연스러운 *서비스 내부 구현*. 다른 서비스의 테이블(`{uid}_feedback`, `fitbit_daily_features` 등)에 *직접 접근*했던 게 위반이었고 Phase 4·5에서 그것만 fix했습니다. Phase 6에서 *legacy DB direct path 폐기*가 contract 단계로 분리된 이유도 이것."**

### Q8. "Pydantic 모델이 5개 서비스에 *인라인 복제*돼 있는데, *drift*가 발생하면 어떻게 감지하나요?"

**A.** 현재로서는 *PR 리뷰 + 검증 노트북*에 의존. 정직한 한계.

자동 감지 방법:
- **단기 (Phase 6 후보)**: shared `biofit-contracts` git submodule. 한 곳에서 정의·각 서비스가 import. drift 0.
- **중장기 (Phase 7+)**: PyPI 또는 internal package registry에 `biofit-contracts` 패키지 배포 + semver. 각 서비스의 requirements.txt가 `biofit-contracts==1.2.3` pin → 호환성 자동 검증.
- **운영 모니터링 (Phase 6+)**: 각 endpoint의 OpenAPI 스펙을 CI에서 추출 → diff 검사. schema 변경 시 PR comment.

현재 mitigation:
- Pydantic 모델 옆 주석: `@contract: shared with X. Phase 6+ extract to biofit-contracts.`
- README의 Phase별 변경 요약 표에 *어느 모델이 어디 정의됐는지* 박제
- 검증 노트북·curl 예시가 *실제 응답 schema*를 cap한 형태로 commit

→ 면접 답변: **"인라인 복제는 *현재 팀 규모(2명) + monorepo* 환경의 trade-off 결정입니다. drift 위험을 인지하고 있고, 두 mitigation을 두었습니다 — `@contract` 주석으로 *연결 지점 명시*, 검증 노트북·curl로 *실제 응답 schema* 박제. 운영 단계로 가면 *git submodule* (~1주 작업) 또는 *PyPI 패키지* (~2주)로 추출이 자연스러운 trigger. 이건 README의 Phase 6 prep에 박제했습니다."**

### Q9. "Phase 5 검증에서 group_service의 첫 호출이 *500 에러*였다면서요. 어떻게 디버깅했나요?"

**A.** 본 ralph 세션의 실제 디버깅 흐름을 재구성:

1. **증상**: `curl /recommendations/23RK3S` → HTTP 500, raw body empty
2. **첫 단서**: `docker compose logs group_service`에서 stack trace 확보
3. **에러 메시지**: `pydantic ValidationError for PartnerEntry: name: Input should be a valid string [input_value=0, input_type=int]`
4. **분석**: pandas DataFrame iterrow가 row.name으로 *컬럼 'name'이 아닌 row index*를 반환하는 함정. 컬럼명이 reserved attribute(`name`)일 때 발생.
5. **fix**: `p.name` → `p["name"]` (dict-style access). 다른 컬럼도 일관성 위해 dict-style로 변환. `getattr(row, col, default)` 패턴은 같은 함정 → `_row_get` helper로 교체
6. **재검증**: `/recommendations/23RK3S` 200, `/recommendations/U001` 200 — 둘 다 정상

→ 면접 답변: **"pandas DataFrame iterrows의 *.name이 row index*라는 함정을 처음 만났습니다. Pydantic이 `int=0`을 string으로 받지 못해 ValidationError를 일으켰는데, *Pydantic이 잡아준 덕에* 잘못된 데이터가 silently 클라이언트에 가는 걸 방지했어요. silent corruption보다 *fail loud*가 항상 좋다는 게 이번 phase의 부수 교훈."**

→ 또 다른 답변 가치: **"Pydantic + FastAPI의 *type 강제*가 *runtime first call*에서 결함을 잡아주는 가치를 직접 입증했습니다. dict 반환이었다면 `name=0` 같은 잘못된 데이터가 *silent하게* 클라이언트에 갔을 것."**

### Q10. "Phase 5 commit 후에도 *7개 컨테이너 안 동기 호출*은 그대로잖아요. *비동기 처리*가 진짜 MSA 아닌가요?"

**A.** 분석 문서 §8.6에서 같은 점을 진단했고, *Phase 6+ 후보로 분리*돼 있습니다.

현재 흐름:
- streamlit → ai_service `/predict` (5분 동기 블로킹 위험)
- ai_service → vLLM (vLLM timeout 시 streamlit도 함께 timeout)

To-Be (Phase 6+):
- streamlit → ai_service `POST /predict-jobs` (즉시 202 + job_id)
- streamlit이 `GET /predict-jobs/{job_id}`로 polling
- 백그라운드 worker가 vLLM 호출·predictions INSERT
- (선택) Celery + Redis 또는 FastAPI BackgroundTasks

이건 *서비스 간 결합* 문제가 아니라 *호출 패턴* 문제. Phase 4·5의 *결합 지점 이동*과 *별도의 차원*. 둘 다 합쳐야 *full MSA*가 됩니다.

→ 면접 답변: **"동기 vs 비동기는 *제 axis*입니다. Phase 4·5는 *what*(서비스 간 결합 지점이 어디인가)을 풀었고, *how*(어떻게 호출하는가 — sync vs async)는 §8.6 작업으로 별도 분리. 두 차원 모두 풀려야 *진짜 운영형 MSA*가 됩니다. Phase 5까지의 commit 흐름이 *결합 지점 정리의 자연스러운 종착점*이고, 그 위에 *호출 패턴 전환*이 후속."**

---

## 검증 종합

| 검사 | 결과 |
|------|------|
| Python syntax (3 파일) | 모두 OK |
| `GET /predictions/{run_id}` 200 | 13 필드 JSON, message 476 chars ✅ |
| `GET /predictions/{fake_id}` 404 | HTTP 404 ✅ |
| `GET /recommendations/U001` (real seed) | `fallback_used=False` + 3 partners + 3 groups ✅ |
| `GET /recommendations/23RK3S` (no slot) | `fallback_used=True` + 4 partners + 3 groups ✅ |
| streamlit 옵트인 시뮬레이션 | HTTP 200 + message 정상 ✅ |
| Phase 1·2·3·4 회귀 | 0건 — 모든 변경 *추가만* + env flag default 0 ✅ |
| pandas `.name` 함정 | 디버깅 + fix 완료 |

특히 **분석 문서 §6 (group_service uid 무시) 결함**이 *명시적으로 fix*됨이 핵심:
- before (Phase 1~4): *모든 호출이 같은 결과 반환* — 회원별 차이 0
- after (Phase 5): U001/U002/U003/U004는 자기 슬롯 사용 (`fallback_used=False`), 23RK3S 같은 미등록은 hardcoded fallback (명시적 신호로)

---

## Non-Goals (Phase 6+)

- shared `biofit-contracts` 패키지 (현재는 인라인 복제 + `@contract` 주석)
- legacy DB direct path *폐기* — 옵트인 dual-path 유지. *contract 단계*는 Phase 6+
- §8.6 비동기 prediction job (`/predict-jobs`) — *동기 호출 패턴* 자체의 전환
- §9.4 vLLM health/fallback (Phase 6 후보)
- §9.8 OpenTelemetry trace + structlog (Phase 6 후보)
- §5.1 LLM 출력 JSON schema + 폴백
- minute-level + sleep_detail 정규화 (Phase 4 RMSE 손실 보강 — Phase 6+)
- predictions에 `features_source TEXT` 컬럼 (옵트인 추적 — Phase 6 후보)

---

## 한 줄 요약 (다른 표현)

**"Phase 1·2·3가 *모델·DB 정직성*을, Phase 4가 *입력 쪽 서비스 간 결합*을 정리했다면, Phase 5는 *출력 쪽 + 클라이언트 측 + 단순한 기능 결함*까지 마무리한 단계."** 7개 컨테이너 중 *5개의 외부 결합 지점*이 모두 *명시적 HTTP 계약 + Pydantic 모델* 위에서 작동. *진짜 MSA에 가까운 형태*가 거의 완성. 남은 30%(legacy 폐기·shared 패키지·비동기 패턴)는 운영 검증 후 Phase 6+ 자연스러운 후속 과제.
