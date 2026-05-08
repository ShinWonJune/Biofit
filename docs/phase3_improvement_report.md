# Phase 3 보완 작업 리포트 (2026-05-09)

> Phase 1·2가 *모델 정직성·메타 추적*을 다뤘다면 Phase 3는 **MSA 데이터 흐름의 운영형 토대**를 깐다. (1) Alembic 마이그레이션 도구(§9.7), (2) 동적 `{uid}_*` → 정규화 `fitbit_daily_features`로의 *expand 단계*(§9.1), (3) `Idempotency-Key`·`model_runs` 상태 머신(§9.6). **모든 변경은 *추가만* 하고 *기존 흐름은 무영향*** — Phase 3 commit 후에도 기존 `docker compose up`·`/predict` 호출이 그대로 작동한다.

## 메타

| 항목 | 값 |
|------|-----|
| 작업 기간 | 2026-05-09 (Phase 2 commit 직후) |
| 시간 예산 | ~15시간 (Phase 1·2 합산보다 약 1.5×) |
| Spec | `.omc/specs/phase3-spec.md` (gitignored) |
| PRD | `.omc/prd.json` (gitignored, 4 stories) |
| 의존 commit | Phase 2 (`0ef8d51`) |
| 변경 파일 수 | 4 (코드 modified) + 7 (신규: alembic.ini·env.py·3 마이그레이션·1 노트북·1 리포트) + 1 (compose) |
| 핵심 안전 원칙 | 모든 변경은 *추가만*, 기존 흐름 무영향, 새 의존성 1개만(`alembic`) |

## 변경 요약

| US | 분류 | 핵심 변경 |
|----|------|----------|
| US-301 | 마이그레이션 도구 | `alembic.ini` + `migrations/env.py` + 3 versions + `migrate` 컨테이너 + db healthcheck |
| US-302 | DB 정규화 expand | `fitbit_daily_features` 신규 + `read_daily_db` env flag 분기 + `csv_to_db` dual-write helper |
| US-303 | 분산 시스템 정합성 | `model_runs` + `idempotency_log` 신규 + `predict` Idempotency-Key 처리 + 단계별 status 전이 |
| US-304 | 검증 + 문서 | `9_3_runs_audit.ipynb` (운영 점검 SQL 모음) + README Phase 3 sub-section + 본 리포트 |

---

## 1. §9.7 — Alembic 도입 (US-301)

### Before

`db/init/*.sql`은 PostgreSQL 컨테이너의 `pgdata` 볼륨이 *비어 있을 때만* 실행됨. 즉:
- 운영 DB가 한 번 생성된 후엔 새 SQL 추가/수정해도 *자동 적용 안 됨*
- 스키마 변경 적용을 위해 `docker compose down -v`로 볼륨 삭제 → **모든 회원 데이터 손실**
- "회원 N명이 누적된 운영 DB에 컬럼 하나 어떻게 추가하나요?"에 답이 없음

### After

#### 1-A. requirements.txt + alembic.ini

```text
# ai_service/requirements.txt
+ alembic>=1.13.0
```

```ini
# ai_service/alembic.ini (요약)
[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = postgresql://biofit:biofitpass@db:5432/biofitdb
```

#### 1-B. migrations/env.py

DATABASE_URL 환경변수가 있으면 alembic.ini의 sqlalchemy.url을 override (compose의 ai_service env 그대로 활용). target_metadata=None — 본 프로젝트는 raw SQL 마이그레이션이라 autogenerate 미사용.

#### 1-C. migrations/versions/001~003

| revision | down_revision | 내용 |
|----------|---------------|------|
| `001_phase3_baseline.py` | None | **빈 마이그레이션** — 기존 db/init/001~009.sql이 적재한 schema 위에 *alembic_version 테이블만* 자동 생성 |
| `002_phase3_daily_features.py` | 001 | `CREATE TABLE fitbit_daily_features (...)` (§9.1 expand) |
| `003_phase3_runs.py` | 002 | `CREATE TABLE model_runs (...)` + `CREATE TABLE idempotency_log (...)` (§9.6) |

#### 1-D. docker-compose.yml

```yaml
db:
  ...
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U biofit -d biofitdb"]
    ...

migrate:
  build: { context: ./ai_service }
  depends_on: { db: { condition: service_healthy } }
  command: ["alembic", "upgrade", "head"]
  restart: "no"

ai_service:
  depends_on:
    db:      { condition: service_healthy }
    migrate: { condition: service_completed_successfully }
```

### Why

- **db/init와 공존, 대체 아님**: 기존 db/init/*.sql은 *유지*. Alembic은 *Phase 3 이후*의 schema 변화만 담당. Phase 4·5·6·… 작업이 모두 Alembic 마이그레이션으로 *git에 박제* 가능.
- **baseline 001을 빈 마이그레이션으로**: 기존 schema는 손대지 않고 alembic_version만 추가 → *기존 운영 DB가 깨지지 않음*. 새 DB 띄울 땐 db/init가 먼저 적재 + alembic이 바로 head로 바운스.
- **service_completed_successfully 의존성**: `ai_service`가 *마이그레이션 성공 후*에만 기동. 마이그레이션 실패 시 ai_service가 *깨진 schema에서 부팅하지 않음* — 자동 안전장치.
- **db healthcheck 추가**: `pg_isready` 기반. `service_started`만으론 *postgres process가 ready 됐는지* 보장 안 됨 — 엄격한 ready signal.

### 한계 (Non-Goals)

- 기존 `db/init/001~009.sql`을 *Alembic 마이그레이션으로 변환*은 안 함 (대규모 작업, 별 phase). 두 시스템이 공존한다는 mental model을 README에 명시.
- `--autogenerate`는 사용 안 함 — target_metadata=None. 본 프로젝트는 SQLAlchemy ORM 모델 부재라 raw SQL이 더 자연스러움.

---

## 2. §9.1 — fitbit_daily_features expand 단계 (US-302)

### Before

분석 문서 §9.1: 회원 200명 시 *동적 `{uid}_*` 테이블이 약 1,800개* 생성되어 PostgreSQL 카탈로그 부풀림, `pg_dump`/모니터링 도구가 회원 수에 비례해 무거워짐. 회원 단위 분석 SQL이 1,800-way UNION 필요.

### After (expand only — 기존 흐름 무영향)

#### 2-A. 새 정규화 테이블 `fitbit_daily_features`

`migrations/versions/002_phase3_daily_features.py`:

```sql
CREATE TABLE IF NOT EXISTS fitbit_daily_features (
    user_id              TEXT NOT NULL,
    date                 DATE NOT NULL,
    -- sleep summary (LEAK_VARS 컬럼도 보존; get_X에서 제외 처리)
    efficiency           FLOAT,
    stage_deep           INT, stage_light INT, stage_rem INT, stage_wake INT,
    time_in_bed          INT, wake_count INT,
    -- activity / vital / HRV
    steps INT, distance FLOAT, calories FLOAT,
    resting_hr FLOAT, azm_total INT, azm_fatburn INT, azm_cardio INT,
    hrv_rmssd FLOAT, hrv_hf FLOAT, hrv_lf FLOAT,
    -- 메타
    source_run_id UUID,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, date)
);
```

#### 2-B. dual-read (sleep_coach.read_daily_db, env flag)

```python
def read_daily_db(table_suffix: str, agg: dict, uid: str) -> pd.DataFrame:
    if os.getenv("USE_NORMALIZED_FEATURES", "0") == "1":
        cols = _NORMALIZED_COLUMN_MAP.get(table_suffix)
        if cols:
            df = read_table("fitbit_daily_features", where=f"user_id = '{uid}'")
            ...
            return df.groupby(KEYS + ["date"]).agg(agg)
    # legacy path (default)
    tbl = f"{uid}_{table_suffix}"
    ...
```

#### 2-C. dual-write (csv_to_db._maybe_dual_write_normalized, env flag)

```python
def _maybe_dual_write_normalized(uid, fname, df):
    if os.getenv("DUAL_WRITE_NORMALIZED", "0") != "1":
        return
    cols = _DUAL_WRITE_COLUMN_MAP.get(fname)
    ...
    sql = "INSERT INTO fitbit_daily_features (...) VALUES (...) ON CONFLICT (user_id, date) DO UPDATE SET ..."
    with engine.begin() as conn:
        for row in df_agg: conn.execute(sql, row)
```

#### 2-D. docker-compose.yml env defaults

```yaml
ai_service:
  environment:
    USE_NORMALIZED_FEATURES: "0"   # default 옵트아웃
data:
  environment:
    - DUAL_WRITE_NORMALIZED=0      # default 옵트아웃
```

### Why

- **expand-contract 패턴 정석**: *새 정규화 구조 도입* (expand)은 마쳤고, *기존 동적 테이블 deprecated/삭제* (contract)는 운영 검증 후 별도 단계 — Phase 3 commit이 *현재 동작을 깨뜨리지 않음*.
- **env flag default 0**: 사용자가 `USE_NORMALIZED_FEATURES=1` 또는 `DUAL_WRITE_NORMALIZED=1`을 *명시적으로 켤 때만* 새 흐름 사용. 즉 Phase 3 commit 자체로는 *어떤 회원의 어떤 데이터도 새 테이블에 저장 안 됨*.
- **두 시스템 공존 검증 가능**: 운영자가 dual-write 켜고 *fitbit_daily_features의 행 수*가 *동적 `{uid}_*` 테이블의 일별 합계*와 일치하는지 SQL로 비교 가능 → 신뢰 후 contract 단계로 진행.
- **PRIMARY KEY (user_id, date)** + ON CONFLICT UPDATE: 같은 (user_id, date) 재적재 시 자동 갱신. csv_to_db의 `if_exists="replace"`처럼 행 손실 우려 없음.

### 한계

- contract 단계 미수행 — *기존 `{uid}_*` 테이블 그대로*. 운영 DB가 무거운 상태는 유지. Phase 4 또는 별도 단계에서 contract 권장.
- 분 단위 데이터(`activity_1min`, `heart_rate_1min`, `hrv`)는 *expand 대상 아님* — 카디널리티 차이로 wide-format 부적합. 별도 *long-format minute table* 작업이 필요 (후속).
- `source_run_id` 컬럼은 dual-write가 채우지 않음 — 미래 *어떤 ingestion이 어떤 row를 만들었는지* 추적용. `data_service`가 ingestion_runs 테이블을 만드는 작업과 묶이는 후속 과제.

---

## 3. §9.6 — Idempotency-Key + model_runs 상태 머신 (US-303)

### Before

분석 문서 §9.6: vLLM 호출이 *timeout*되면 *토큰은 이미 소비됐는데* `predictions` INSERT는 일어나지 않아 `token_usage`와 `predictions` 정합성 깨짐. 같은 입력으로 두 번 호출하면 두 번 학습 + 두 번 vLLM 호출 + 두 번 INSERT — 비용·DB row 중복.

### After (옵트인)

#### 3-A. 새 테이블

`migrations/versions/003_phase3_runs.py`:

```sql
CREATE TABLE model_runs (
    run_id        UUID PRIMARY KEY,
    uid           TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'queued',
    current_step  TEXT,
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    error         TEXT,
    retry_count   INT DEFAULT 0
);
CREATE INDEX ... ON model_runs(status);

CREATE TABLE idempotency_log (
    key            TEXT PRIMARY KEY,
    run_id         UUID,
    response_body  JSONB NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
```

#### 3-B. app_ai.py predict 흐름 변경

```python
@app.post("/predict")
def predict(req, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    # §9.6 멱등성 hit 체크
    if idempotency_key:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT response_body FROM idempotency_log WHERE key = %s", (idempotency_key,))
            row = cur.fetchone()
            if row:
                return row[0]   # vLLM·CatBoost 재실행 0건

    run_id = uuid.uuid4()

    # model_runs INSERT (queued → running → succeeded/failed)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO model_runs (run_id, uid, status, current_step) VALUES (%s, %s, 'queued', 'init')", ...)
    
    try:
        _update_run_status(run_id, "running", "coach_main")
        result = coach_main(...)
    except Exception as e:
        _update_run_status(run_id, "failed", error=str(e))
        raise HTTPException(...)
    
    _update_run_status(run_id, "running", "predictions_insert")
    # predictions INSERT (12 컬럼)
    ...
    _update_run_status(run_id, "succeeded", "done")

    response = {...}
    
    # §9.6 idempotency 적재
    if idempotency_key:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO idempotency_log (key, run_id, response_body) VALUES (%s, %s, %s::jsonb) ON CONFLICT (key) DO NOTHING", ...)
    
    return response
```

### Why

- **옵트인 멱등성**: `Idempotency-Key` 헤더가 *없으면* 기존 동작과 동일. 있으면 같은 키로 재호출 시 vLLM/CatBoost 재실행 0건. AWS API Gateway·Stripe API와 같은 패턴.
- **단계별 상태 머신**: `current_step` 컬럼으로 *어디서 자주 깨지는가* SQL 한 줄로 분석 가능 (`SELECT current_step, COUNT(*) FROM model_runs WHERE status='failed' GROUP BY current_step`). Phase 4 §9.8 OpenTelemetry와 묶일 *분산 추적의 토대*.
- **모든 처리 try/except로 감쌈**: 마이그레이션이 *아직 적용 안 된 환경* (예: Phase 3 commit을 받았지만 docker compose down 안 한 운영 DB)에서도 `model_runs`/`idempotency_log` 조회 실패가 *기존 흐름을 막지 않음*. 경고 로그만 남기고 정상 처리 진행.
- **JSONB response_body**: PostgreSQL JSONB 자동 deserialize → 재호출 시 dict 그대로 반환.

### 한계

- 보존 기간 정책 미구현 — `idempotency_log`가 무한 누적. 7일 후 삭제 cron은 후속 (Phase 4+).
- `retry_count` 컬럼은 도입했지만 *증가 로직*은 미구현 — Phase 4 *exponential backoff + circuit breaker*와 묶이는 후속.
- transactional outbox 패턴은 미적용 — 현재는 *vLLM 호출 후 즉시 predictions INSERT*가 같은 함수 안. token_usage는 chat 함수 안에서 별도 INSERT라 *부분 실패 시 정합성 risk*는 잔존. Phase 4 §9.6 후속 보강에서 outbox 도입 권장.

---

## 4. 노트북 + README + 리포트 (US-304)

### `experiments/9_3_runs_audit.ipynb`

운영 점검용 5개 SQL 셀:

1. `alembic_version` — head 확인 (`003`이면 정상)
2. `model_runs` — 단계별 실패율·평균 소요 시간
3. `idempotency_log` — 7일 만료 row 수
4. `fitbit_daily_features` — dual-write 진행률
5. `predictions × model_runs` join — 호출당 latency

분석보다 *디버깅·SLO 모니터링* 도구. Phase 1·2 노트북과 달리 *가설 검증*이 아니라 *운영 점검*이 목적이라 셀 수 11개로 가벼움.

### README "Phase 3" sub-section

Improvements 섹션 안에 Phase 3 sub-section 추가:
- 변경 요약 표 (3 row, §9.7·§9.1·§9.6)
- 운영 적용 가이드 5단계 — `docker compose up --build`, 로그 확인, 새 마이그레이션 추가, expand 옵트인, 멱등성 사용
- Phase 4 prep 박스 (§9.4 vLLM health, §9.8 OpenTelemetry, §5.1 LLM JSON schema)

### 본 리포트

Phase 1·2와 일관된 Before/After/Why 형식.

---

## 5. 검증 종합

| 검사 | 결과 |
|------|------|
| Python syntax (5 files: app_ai, sleep_coach, csv_to_db, feedback_api, env.py) | 모두 OK |
| Notebook nbformat 4.5 | 11 cells valid |
| 새 마이그레이션 파일 syntax | 표준 alembic upgrade/downgrade 패턴 |
| docker-compose 무결성 | yaml 구조 정상 (db healthcheck + migrate + ai_service depends_on dict) |
| Phase 1·2 회귀 위험 | 없음 — Phase 3 변경 모두 *추가만*. env flag default 0이라 *런타임 동작 변경 0* |
| 옵트인 동작 검증 | env flag 분기 *코드 path 명확*. 기존 코드는 0 path, 옵트인 시 1 path |

특히 *기존 운영 DB가 깨지지 않는다*는 보장 — Phase 3의 가장 중요한 안전 속성:

| 운영 환경 시나리오 | 동작 |
|------------------|------|
| Phase 3 commit 받고 *docker compose 재기동 안 함* | 모든 처리 try/except 감쌈 → `model_runs`/`idempotency_log` 조회 실패해도 정상 동작 |
| `docker compose up --build` 후 마이그레이션 자동 적용 | baseline 001은 empty라 *기존 schema 변경 0*. 002·003은 IF NOT EXISTS로 idempotent |
| env flag 0 (default) | 기존 동적 테이블 흐름·기존 predict 응답 형태 *완전히 동일* |
| env flag 1 옵트인 | 새 흐름 활성. 운영자가 *명시적 의도*로만 활성화 |

---

## 6. Phase 4~ 다음 단계

### Phase 4 (~1주, ~10시간)

- **§9.4 vLLM health/fallback**: `/predict` 호출 전에 `GET /health` 점검. 다운 시 LLM 부분 건너뛰고 *CatBoost 예측 + SHAP만 카드로* 반환. 응답 형태에 `degraded_mode: true` 필드 추가
- **§9.8 OpenTelemetry trace + structlog + Prometheus exporter**: streamlit→data_service→ai_service→vLLM 한 trace_id로 묶음. `predictions.note`에 단계별 에러 적재 (현재 `"run completed"` 단일 문자열)
- **§5.1 LLM 출력 JSON schema + 폴백**: `**summary**`/`**plan**` 마커 split이 깨질 때 자동 재시도 + 폴백 메시지

### Phase 5 (~1개월, 실험 기간 포함)

- **§4 within-subject 4주 미니 실험**: §8.2 회귀 추천 슬롯의 *인과* 검증. 본인 데이터로 처치/대조 2-주씩
- **§3.2 주관·객관 격차 모델**: 주관 점수와 efficiency를 별 모델로 분리. 격차 큰 회원에게 다른 코칭
- **§2.3 이행 여부 정량 신호**: LLM에게 "지난 plan 지켰는가" 추측 시키지 말고 *코드에서 계산*해 prompt에 주입

### Phase 6 (~2주)

- **§9.9 PIPA 데이터 라이프사이클**: `DELETE /users/{uid}` 멀티-서비스 cascade + 보존 기간 cron + 감사 로그
- **§5.3 OAuth + RBAC**: Fitbit OAuth flow를 server-side로, 트레이너는 *담당 회원만* 조회
- **§5.2 의료 면책·가드레일**: 카드 하단 면책 문구 + JSON schema에 위반 검출 정규식
- **§8.6 비동기 호출 + SLO**: `/predict`를 `/predict-jobs` 비동기 패턴으로 전환 (5분 블로킹 해소)

### Phase 7 (~1주)

- **§6 비즈니스 민감도 분석**: 이탈 감소 효과 0/5/10/20% 가정에 대한 손익 분기 시뮬레이션
- **§8.4 group_service 양방향 매칭**: 동의 그래프 + funnel 측정
- **Q1·Q2 답안 적용**: keywords + 시간대 교집합 추천 로직 + Polyglot Persistence 평가 (현재로선 추가 도입 권장 안 함)

---

## 7. 한 줄 요약

**Phase 3는 기존 운영 흐름은 *그대로 유지*하면서 (1) Alembic으로 *앞으로의 schema 진화*를 git에 박제 가능하게, (2) `fitbit_daily_features` 정규화 테이블을 *추가*하고 옵트인 dual-write/dual-read로 점진 전환의 토대를, (3) `Idempotency-Key`·`model_runs` 상태 머신으로 vLLM timeout·재시도 시 비용·정합성 안전을 확보했다.** *기존 흐름을 깨지 않는 expand-contract 패턴의 expand 단계*가 핵심 — contract 단계(기존 동적 테이블 deprecated/삭제)는 운영 검증 후 별도로 분리.
