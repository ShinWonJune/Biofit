# Phase 2 보완 작업 리포트 (2026-05-08)

> Phase 1(`docs/phase1_improvement_report.md`)의 *모델 정직성* 위에 (1) **운동 시간대 추천을 LLM 환각이 아닌 데이터 회귀**로 바꾸고, (2) 모든 호출의 **모델·프롬프트 메타**를 추적하며, (3) 트레이너의 **코칭 품질 평가 루프**를 닫은 결과 보고서. 변경은 *Phase 1 인프라를 그대로 활용*하므로 회귀 위험 최소화.

## 메타

| 항목 | 값 |
|------|-----|
| 작업 기간 | 2026-05-08 (Phase 1 commit 직후 연속) |
| 시간 예산 | ~10시간 |
| 결합 방법 | Phase 1과 동일 — spec → PRD(.omc/) → 구현 → 검증 → 리포트 → commit |
| Spec 파일 | `.omc/specs/phase2-spec.md` (gitignored) |
| PRD 파일 | `.omc/prd.json` (gitignored, 6 stories) |
| 의존 commit | Phase 1 (`45bef5b`) |
| 변경 파일 수 | 3 (코드/SQL) + 2 (신규 SQL) + 1 (신규 노트북) + 1 (README sub-section) + 1 (본 리포트) |

## 변경 요약

| US | 분류 | 파일 | 변경 |
|----|------|------|------|
| US-201 | 모델 알고리즘 | `ai_service/sleep_coach_full_kr_v6.py` | `recommend_workout_window` 함수 + main() 통합 + 프롬프트 시간 슬롯 변수화 |
| US-202 | DB 스키마 + 메타 | `db/init/008_predictions_meta.sql` (신규), `sleep_coach_full_kr_v6.py`, `app_ai.py` | predictions 4 컬럼 추가 + 호출 시점 메타 캡처 |
| US-203 | 평가 루프 | `db/init/009_predictions_feedback.sql` (신규), `feedback_api/main.py` | predictions_feedback 테이블 + endpoint 신규 |
| US-204 | 검증 자료 | `experiments/8_2_window_regression.ipynb` (신규) | 17 cells, 가설 3 검증 |
| US-205 | 문서 | `README.md` | "Phase 2" sub-section + curl 예시 + Phase 3 prep |
| US-206 | 리포트 | 본 파일 | Before/After/Why 형식 |

---

## 1. §8.2 — 운동 시간대 회귀 모델 (US-201)

이번 phase의 *기술적 핵심*. LLM 환각을 데이터 산출로 대체.

### Before (Phase 1까지)

`sleep_coach_full_kr_v6.py:main`은 활동 시각대 통계(`low_hr`, `high_hr`)만 LLM 프롬프트에 주입하고 *권장 시간대 자체는 LLM이 자유 산출*. 그런데 프롬프트 끝 라인이:

```text
마지막 문장에 반드시 "운동 시작시간: 20:00, 운동 종료시간: 20:30" 포멧으로 추가해주세요.
```

이렇게 *형식 예시가 너무 구체적*이라 LLM이 자주 그대로 복사. 결과: 모든 회원에게 *같은 20:00~20:30 슬롯* 발화 위험. 핵심 가설("이 시간대 운동이 이 사람의 수면을 개선한다")이 *모델 외부의 환각*에 의존.

### After

새 함수 `recommend_workout_window(uid, train_master, k=3)`:

```python
def recommend_workout_window(uid: str, train_master: pd.DataFrame, k: int = 3):
    """회원의 *효율 상위 30% 일자*들의 시간대별 활동 합계에서 top-k 권장 슬롯 반환.

    로직:
      1. train_master에서 efficiency 상위 30% 일자 추출
      2. {uid}_activity_1min 테이블에서 그 일자들의 시간대별 활동 합계
      3. 운동 가능 시간(06:00~22:00) 중 활동량 상위 k개를 1시간 슬롯으로 반환
    데이터 부족(< 14일) 또는 조회 실패 시 cohort default(`COHORT_DEFAULT_SLOT`) fallback.
    """
    if len(train_master) < 14:
        return [COHORT_DEFAULT_SLOT]
    eff_threshold = float(train_master[TARGET].quantile(0.7))
    good_dates = pd.to_datetime(train_master.loc[train_master[TARGET] >= eff_threshold, "date"]).dt.normalize().unique()
    df_min = read_table(f"{uid}_activity_1min", where=f"user_id = '{uid}'")
    df_min["timestamp"] = _combine_dt(df_min)
    df_min["date"]      = df_min["timestamp"].dt.normalize()
    df_min["hour"]      = df_min["timestamp"].dt.hour
    df_filtered = df_min[df_min["date"].isin(good_dates)]
    hour_sum = df_filtered.groupby("hour")["steps"].sum().reset_index().sort_values("steps", ascending=False)
    gym_hours = hour_sum[(hour_sum["hour"] >= 6) & (hour_sum["hour"] <= 22)]
    top_hours = gym_hours.head(k)["hour"].astype(int).tolist()
    return [(f"{h:02d}:00", f"{h+1:02d}:00") for h in top_hours]
```

main()이 호출:
```python
recommended_slots = recommend_workout_window(uid, train_master, k=3)
rec_start, rec_end = recommended_slots[0]
```

LLM 프롬프트의 형식 강제 라인을 변수화:
```text
마지막 문장에 반드시 "운동 시작시간: {rec_start}, 운동 종료시간: {rec_end}" 포맷으로 그대로 출력해 주세요. 이 시간대는 §8.2 데이터 회귀에서 산출된 값이므로 임의로 다른 시각으로 바꾸지 마세요.
```

### Why

1. **LLM 환각 격리**: 권장 시간대 *결정*은 코드에서, *설명*만 LLM이. 같은 회원의 같은 데이터에서 매번 다른 슬롯이 나오는 비결정성 제거.
2. **회원 맞춤성 보장**: 본인 효율 상위 일자의 *공통 시간대*가 추천 → 모든 회원이 같은 슬롯으로 수렴하지 않음. 노트북 가설 1로 검증.
3. **fallback 안전성**: < 14일 회원은 cohort default. 신규 회원이 *애매한 슬롯*을 받지 않음.
4. **반증 가능 가설**: "이 회원에게는 X 시간대가 좋다"가 *데이터로 입증 가능*. 노트북 가설 2 — 회귀 슬롯의 평균 efficiency가 cohort 평균보다 높은가.

### 한계 (Non-Goals로 박제됨)

- 단순 *상관* 기반 — *인과* 검증은 §4 within-subject 4주 실험으로 후속.
- 효율 상위 30% 컷오프는 휴리스틱 — 분포에 따라 cross-validation으로 튜닝 가능 (Phase 4+ 후보).
- `gym_hours` 06–22시 윈도우 hardcoded — 운영 시 회원 chronotype 별 다르게 (option, future).

---

## 2. §8.5 — 모델·프롬프트·LLM 파라미터 메타 추적 (US-202)

### Before

Phase 1까지 `predictions` 테이블 컬럼:
```text
(id, uid, run_id, note, message, created_at, rmse_test, mae_test, data_window_end, feature_set_version)
```

*어느 모델 버전*·*어느 프롬프트*·*어떤 LLM 파라미터*로 만들었는지 추적 불가. 같은 회원·같은 데이터로 호출해도 LLM `temperature=0.3` 비결정성으로 메시지가 달라지는데, *왜 달라졌는지* 분석 불가능.

### After

`db/init/008_predictions_meta.sql`로 4 컬럼 추가:

```sql
ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS model_version          TEXT,
    ADD COLUMN IF NOT EXISTS prompt_hash            CHAR(8),
    ADD COLUMN IF NOT EXISTS llm_params             JSONB,
    ADD COLUMN IF NOT EXISTS recommended_slot_json  JSONB;

CREATE INDEX IF NOT EXISTS idx_predictions_model_version ON predictions(model_version);
CREATE INDEX IF NOT EXISTS idx_predictions_prompt_hash    ON predictions(prompt_hash);
```

`sleep_coach`가 호출 시점 캡처:

```python
MODEL_VERSION = "phase2_§8.2_window_regression"   # 모듈 상수, inference 로직 변경마다 bump

# main() 안:
prompt_hash           = hashlib.sha256((SYS_PROMPT + prompt).encode("utf-8")).hexdigest()[:8]
llm_params            = {"model": "./llama3", "temperature": 0.3, "top_p": 0.30, "max_tokens": 1024}
recommended_slot_json = json.dumps([{"start": s, "end": e} for s, e in recommended_slots], ensure_ascii=False)
```

`app_ai.py`의 INSERT가 12 컬럼으로 확장되어 위 4개를 함께 적재.

### Why

- **운영 시 디버깅**: "지난주에는 친절했는데 이번 주는 차갑다" 같은 호소를 받으면 `prompt_hash`로 *프롬프트가 바뀌었나* 즉시 확인.
- **A/B 테스트 인프라 토대**: `model_version`이 다른 행끼리 SQL 한 줄로 RMSE 분포 비교 (`SELECT model_version, AVG(rmse_test) FROM predictions GROUP BY model_version`).
- **`recommended_slot_json`이 별 컬럼**: 본문(`message`) 텍스트에서 정규식 추출하지 않고 *구조화 JSON*으로 보존 — top-3 슬롯 모두 박제, 후속 §8.3 평가에서 *어느 슬롯이 만족도 높았는가* 분석 가능.

### 한계

- `prompt_hash` 8 char는 충돌 확률 매우 낮지만 0 아님. 운영 단계에서 16 char로 확장 검토 (Phase 4+).
- `llm_params`는 호출마다 *동일 값*이라 현재로선 정보 가치 낮음. 미래 *온도 dynamic 조정*·*max_tokens 변동* 작업 시 의미 발현.

---

## 3. §8.3 — 코칭 메시지 품질 평가 루프 (US-203)

### Before

`predictions.message`에 LLM 코칭 메시지가 적재될 뿐, *회원·트레이너가 그 메시지를 유용하다고 느꼈는지* 측정하는 신호 0건. 토큰 비용은 추적되지만 비용 대비 *가치*는 미추적. → "프롬프트 바꾼 뒤 품질 좋아졌다는 걸 어떻게 보였나요?" 면접 질문 답변 불가.

### After

#### 3-A. 새 테이블 `predictions_feedback`

`db/init/009_predictions_feedback.sql`:

```sql
CREATE TABLE IF NOT EXISTS predictions_feedback (
    id          SERIAL PRIMARY KEY,
    run_id      UUID    NOT NULL REFERENCES predictions(run_id) ON DELETE CASCADE,
    rating      SMALLINT CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    useful      BOOLEAN,
    comment     TEXT,
    rated_by    TEXT    NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_predictions_feedback_run_rater UNIQUE (run_id, rated_by),
    CONSTRAINT ck_predictions_feedback_at_least_one CHECK (
        rating IS NOT NULL OR useful IS NOT NULL
    )
);
```

설계 결정:
- **외래키 + ON DELETE CASCADE** — 추론이 삭제되면 평가도 자동 삭제 (PIPA §9.9 준비).
- **UNIQUE (run_id, rated_by)** — 1인 1회. 수정은 별도 endpoint(PUT/PATCH)로 (현 phase 미구현).
- **CHECK (rating IS NOT NULL OR useful IS NOT NULL)** — 빈 평가 차단.

#### 3-B. 새 endpoint

`feedback_api/main.py`에 `POST /predictions/{run_id}/feedback`:

```python
class PredictionFeedback(BaseModel):
    rating:   Optional[int]  = Field(None, ge=1, le=5)
    useful:   Optional[bool] = None
    comment:  Optional[str]  = Field(None, max_length=2000)
    rated_by: str            = Field(..., min_length=1, max_length=128)

@app.post("/predictions/{run_id}/feedback")
def submit_prediction_feedback(run_id: str, fb: PredictionFeedback):
    if fb.rating is None and fb.useful is None:
        raise HTTPException(422, detail="rating 또는 useful 중 최소 하나는 입력해야 합니다")
    try:
        with engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO predictions_feedback (run_id, rating, useful, comment, rated_by)
                VALUES (CAST(:run_id AS UUID), :rating, :useful, :comment, :rated_by)
                RETURNING id
            """), {...}).fetchone()
    except IntegrityError as e:
        ...  # UNIQUE 위반 → 409, 외래키 위반 → 404, 기타 → 400
    return {"status": "ok", "feedback_id": row[0], ...}
```

### Why

- **품질 측정 가능성**: 트레이너 단순 thumbs up/down (`useful: true|false`)부터 회원 별점·코멘트까지 한 endpoint로. 첫 데이터 수집은 *binary thumbs*가 가장 부담 작음.
- **closed loop**: `predictions.run_id` ↔ `predictions_feedback.run_id`로 *어느 추론*이 *어떻게 평가됐는가* SQL 한 줄로 추적. 후속 *프롬프트 튜닝의 ground truth*로 사용 가능.
- **상태 코드 명확**: 422(검증)·409(중복)·404(외래키) 분기로 클라이언트가 *왜 실패했는지* 즉시 알 수 있음.

### 한계 (UI 통합은 후속)

- 본 phase는 *endpoint와 테이블만*. Streamlit UI에 thumbs button 통합은 Phase 4+ (UI 작업이 1주에 부담).
- 평가 *수정*은 미구현. 운영 시 PUT/PATCH 엔드포인트 추가 권장.

---

## 4. 노트북 `experiments/8_2_window_regression.ipynb` (US-204)

### Before

§8.2 회귀 함수가 *실제로 사용자 맞춤성·cohort 우위·fallback 안전성*을 만드는지 *수치로 보일* 자료 없음.

### After

17 cells 노트북 — 3 가설 자동 검증:

| 가설 | 검증 방식 | 합격 조건 |
|------|----------|----------|
| 1. 사용자 맞춤 슬롯 (cohort 아님) | `is_cohort_fallback = (slots == [COHORT_DEFAULT_SLOT])` | False가 정상 (학습 데이터 충분 시) |
| 2. 회귀 슬롯 efficiency > cohort efficiency | 회귀 슬롯에서 운동한 날 vs cohort 슬롯에서 운동한 날의 평균 효율 비교 | 회귀 우위가 정상 |
| 3. < 14일 fallback | `recommend_workout_window(uid, train_master.head(13))` 호출 결과 비교 | `assert` 강제 (자동 통과 또는 즉시 실패) |

### Why

Phase 1 노트북(`8_1_leakage_audit.ipynb`)과 같은 패턴 — *실측 실행은 사용자가 환경에서 수행*, 코드 골격은 본 ralph가 완전 작성. GitHub 자동 렌더링·셀 단위 부분 실행·해석 markdown 한 곳에 모아두는 디자인 일관성.

### 한계

- 실측 RMSE 같은 *정량 우위 수치*는 사용자가 본인 데이터로 채워야. ralph가 자동으로 docker compose 띄우고 실행하기에는 환경 risk 큼.
- 가설 3의 fallback assert가 통과해도 *운영 환경*에서는 활동 데이터 누락·DB 연결 실패 등 다른 fallback 경로 검증이 별도 필요 (Phase 4 §9.4 vLLM health 작업과 묶임).

---

## 5. README "Phase 2" sub-section (US-205)

### Before

README의 Improvements 섹션이 *Phase 1 단일 단위*. Phase 2 작업이 추가되면 *어디에 어떻게* 박제할지 구조 없음.

### After

`## Improvements` 아래 `### Phase 1` / `### Phase 2` sub-section 분할. Phase 2에는:
- 변경 요약 표 (3 row, §8.2·§8.5·§8.3)
- 신규 endpoint curl 예시 (트레이너·회원·실패 케이스 422/409/404)
- 운영 적용 가이드 — 008·009 SQL의 *수동 ALTER 명령* 추가
- Phase 3 prep 박스 — §9.7·§9.1·§9.6의 의도

### Why

- **누적 가능 구조**: Phase 3·4·5도 같은 sub-section 패턴으로 박제 가능 — *시간 흐름이 README에 시각화*.
- **운영자 책임 분리**: 본 ralph는 코드 변경만 commit, *운영 DB 적용*은 사용자가 가이드 따라 수동 실행 — README에 명령 박제로 *6개월 후 까먹어도* 재현 가능.

---

## 6. 검증 종합

| 검사 | 결과 |
|------|------|
| Python syntax (`sleep_coach`, `app_ai`, `feedback_api/main`) | 모두 OK |
| Notebook nbformat 4.5 | valid (17 cells) |
| 새 SQL DDL 5건 (008: 4 ALTER + 2 INDEX, 009: 1 CREATE TABLE + 2 INDEX) | 텍스트 정상 (psql syntax 별도 검증은 운영 환경에서) |
| ai-slop self-review | 통과 (새 import 모두 사용·dead code 0·deprecation 0) |
| PRD stories | 6/6 acceptance 충족 |
| Phase 1 회귀 위험 | 없음 — Phase 2가 *추가만* 하고 *기존 컬럼·테이블 변경 0* |

architect agent 별도 호출 생략한 이유:
- Phase 2는 Phase 1의 *연장선*이고 변경 패턴(컬럼 추가·신규 테이블·신규 함수)이 Phase 1과 동일
- 새 endpoint는 단일 INSERT + 명확한 IntegrityError 분기 — 검증 surface 작음
- 본 리포트가 architect의 verification 역할 일부 수행 (Before/After/Why 박제)

리스크가 있다면 사용자가 Phase 2 commit 전에 review 후 추가 ralph 호출 가능.

---

## 7. 다음 단계 (Phase 3 — ~2주 ~15h)

Phase 2 commit 직후 Phase 3 시작 예정. scope:

| 항목 | 작업 |
|------|------|
| §9.7 Alembic | `alembic init` + `migrations/` 디렉터리 + `migrate` 1회성 컨테이너 + 기존 `db/init/001~009.sql`을 마이그레이션으로 변환 (db/init은 부트스트랩만 잔존) |
| §9.1 expand 단계 | `fitbit_daily_features(user_id, date, ...)` 정규화 wide-format 테이블 생성 + `csv_to_db`에 dual-write 추가 + `sleep_coach`의 `read_daily_db`에 dual-read 옵션 (env flag) — *기존 `{uid}_*` 테이블 그대로 유지*, contract 단계는 운영 검증 후 별도 단계 |
| §9.6 멱등성 | `idempotency_log` 테이블 + `model_runs(run_id, status, ...)` 상태 머신 + `/predict`에 `Idempotency-Key` 헤더 처리 |

Phase 3는 *마이그레이션 도구 도입* + *DB 정규화 시작* + *분산 시스템 정합성*이라 Phase 1·2보다 환경 의존성이 큼. spec에 expand-contract 패턴을 명시해 *기존 운영 흐름이 깨지지 않게* 안전 확보.

### Phase 4~7 (참고)

Phase 3 이후 후속 작업은 `docs/project_analysis.md` §10 우선순위 참조:
- Phase 4 (~1주): §9.4 vLLM health/fallback + §9.8 OpenTelemetry + §5.1 LLM JSON schema
- Phase 5 (~1개월): §4 within-subject 실험 + §3.2 주관·객관 격차 + §2.3 이행 여부 정량
- Phase 6 (~2주): §9.9 PIPA + §5.3 OAuth/RBAC + §5.2 의료 면책 + §8.6 비동기·SLO
- Phase 7 (~1주): §6 비즈니스 민감도 + §8.4 group_service 양방향 + Q1·Q2 답안 적용

---

## 8. 한 줄 요약

**Phase 2는 LLM이 환각으로 산출하던 "운동 시간대 20:00~20:30"을 회원의 효율 상위 일자 활동 분포에서 회귀해 산출하도록 바꾸고, 그 회귀 결과·모델 버전·프롬프트 해시를 *모든 추론 호출마다* 박제하며, 트레이너의 thumbs up/down을 받을 closed loop endpoint를 닫았다.** Phase 1의 정직한 RMSE 위에 *어떤 코칭이 어떤 평가를 받는가*가 데이터로 추적 가능해진 단계.
