# PSQI 기반 수면 질 예측 — 단계별 보완 계획

> **출처**: [`experiments/ML_보완논의.md`](ML_보완논의.md) — efficiency 단일 타깃의 한계 진단 및 PSQI 4 차원 분리 모델 제안.
> **본 문서의 목적**: 그 제안을 *실행 가능한 단계*로 분해 — *무엇을, 어떤 순서로, 어떻게 검증할지*까지 박제.
> **시점**: 2026-05-10. Phase 1~5 commit 완료(`21b6525`) 직후 후속 ML 작업.

---

## 0. 한 줄 요약

> efficiency 단일 회귀가 *수면 질의 한 측면*(C4 한 차원)만 본다는 한계를 **PSQI 4 차원(주관·잠복기·시간·효율) 분리**로 해소한다. 차원별 0~3 점수 × 4개 CatBoost → 합산 (0~12). **핵심 가치는 *information coverage*** — efficiency 모델이 못 하던 C1·C2·C3 차원을 *새로 예측 가능*하게 만든다. 두 모델은 *axis가 달라 RMSE 직접 비교 무의미* — 비교 프레임을 *RMSE 우열*에서 *각 차원이 naive baseline을 이기는가*로 옮긴다. 검증 PASS 후 **Phase F**에서 *positivity-constrained forward simulation*으로 *PSQI 합산 최소* 슬롯 추천 — 신규 회원은 4주 *exploration round-robin* 후 5주차부터 활성. 트레이너 카드는 *정형 데이터(HTML 직접) + 자연어 1단락(LLM)* 하이브리드. 마지막 **Phase G**에서 *진행 상태 추적 + 비동기 prediction job + 새로고침 무손실 복구*로 동기 호출의 8가지 단점을 푼다. 작업은 7 phase, *experiments 검증* 후 운영 path 통합.

---

## 1. 작업 목표 명시 (Acceptance Criteria)

### 1.1 핵심 산출물

| # | 산출물 | 위치 |
|---|------|------|
| 1 | 4 차원 점수(0~3) 산출 함수 — 데이터 → PSQI 매핑 | `experiments/lib/psqi.py` (신규) |
| 2 | 저녁 세분화 features 산출 함수 (`steps_evening_18_20`, `steps_evening_20_22`, 운동 종료 시각 기준) | `experiments/lib/features.py` (신규) — 22개 → **24개** |
| 3 | 4 차원별 CatBoost 학습 + holdout RMSE/MAE | `experiments/psqi_4dim_models.ipynb` (신규) |
| 4 | 4 차원별 SHAP top-k + dependence plot | 같은 노트북 |
| 5 | 차원별 naive baseline + 합산 naive baseline + multi-output baseline 비교 (efficiency 모델은 axis 다름이라 비교 안 함) | 같은 노트북 |
| 6 | Cold-start exploration round-robin 흐름 (4주, 주 단위 다른 시간대 권장) | `experiments/lib/exploration_phase.py` (신규) |
| 7 | Positivity-constrained forward simulation 추천 함수 | `experiments/lib/recommend_psqi.py` (신규) |
| 8 | 운영 path 통합 — `predictions`에 차원별 점수 JSON 컬럼 + PSQI 추천 슬롯 | `ai_service/sleep_coach_full_kr_v6.py` (Phase 6 후보) |
| 9 | 트레이너 카드 layout 변경 — 정형 HTML + 자연어 1단락 분리 | `streamlit_app/streamlit_fitbit.py` (Phase 6 후보) |
| 10 | 보완 후 리포트 — Before/After/Why | `experiments/PSQI_REPORT.md` |

### 1.2 통과 기준 (PASS condition)

| 기준 | 임계값 | 의미 |
|------|------|------|
| 4 차원 모델 모두 학습 성공 | 차원당 RMSE 산출 | 데이터 결측이 학습을 막지 않음 |
| ⭐ **C1·C2·C3·C4 *각각*이 차원별 naive baseline 이김** | 차원당 RMSE < `mean(해당 차원 점수)` | *information coverage* 입증 — efficiency 모델이 못 하던 3 차원의 예측이 *새로* 가능해짐 |
| 합산 점수 RMSE < 합산 naive baseline | 합산 RMSE < `mean(PSQI 합)` | 4 모델 합산이 단순 평균을 이겨야 의미 |
| 4 차원 SHAP이 *서로 다른 변수*를 top-1으로 잡음 | 4 차원 모두 동일 변수면 ❌ | 분리 모델의 *해석 분해* 가치 입증 |
| **Phase F 추천 슬롯이 *예측 PSQI 합산 ≥ 2점* 개선** | `predicted_total < current_total - 2` | 의미 있는 추천 — 단순 noise가 아닌 실 효과 |

> ⚠️ **삭제된 PASS 기준** — *합산 점수 RMSE 분포가 단일 efficiency 모델 대비 비교 가능*은 *axis 오인*으로 제거. efficiency 모델은 C4 한 차원, PSQI 모델은 4 차원 합 — 두 RMSE의 단위가 달라 *공정 비교 불가*. PSQI 분리의 가치는 *RMSE 우열*이 아니라 *information coverage* (예측 가능한 차원이 1 → 4로 늘어남) 임을 명확히 한다. *기존 모델을 이길 필요 없음* — 새 차원을 *추가*로 잡아 *수면 질을 더 잘 대표*하면 충분.

---

## 2. PSQI 4 차원 점수화 — 임상 기준 매핑

PSQI 원 척도는 7 component이지만, 본 프로젝트 데이터로 산출 가능한 *4개 핵심 component*만 사용 (component 5·6·7은 약물·낮졸림·코골이로 데이터 부재 — 후속).

### 2.1 차원별 데이터 출처와 점수 매핑

| 차원 | 입력 데이터 | 0점 | 1점 | 2점 | 3점 |
|------|------------|-----|-----|-----|-----|
| **C1 주관적 수면의 질** | `feedback.sleep_score` 변경 필요: (0=최고/1=잘잤어/2=못잤어/3=최악) | sleep_score=0 |  sleep_score=1  | sleep_score=2 | sleep_score=3 |
| **C2 수면 잠복기** | `sleep_detail`의 첫 비-wake 시각 - 첫 wake 시각 (분) | < 16분 | 16~30 | 31~60 | > 60 |
| **C3 수면 시간** | `minutes_asleep` (분→시간 변환) | > 7h | 6~7h | 5~6h | < 5h |
| **C4 습관적 수면 효율** | `efficiency` (%) | > 85% | 75~84 | 65~74 | < 65 |

→ **합산**: `score_total = c1 + c2 + c3 + c4` ∈ [0, 12]. *낮을수록 수면 질 높음*.

### 2.2 측정 한계 — 1차는 *수용*, 후속 phase에서 *회원 입력으로 보강*

> *"단, 수면 잠복기를 위한 잠자리에 드는 시간을 fitbit wake 추즉할 수 있지만 정확한 값은 아님. 현재로써는 이대로 진행."* (사용자 결정 — 1차)

→ 1차 구현(Phase A.3)은 `sleep_detail`의 *첫 wake 누적*을 *잠복기로 근사*. 한계 인지.

→ Phase B 검증 결과 C2 차원이 *floor effect*(거의 0점에 몰림)로 baseline 미달. 분포 자체가 좁아 모델이 학습할 신호 부족이었고, *측정 정확도 한계*가 그 floor effect를 더 강화. 이를 풀기 위한 후속 phase를 §3 Phase A.4로 박제 — *회원 측 입력으로 침대 시각을 직접 수집*하여 잠복기 = (Fitbit이 인식한 첫 비-wake 시각) - (회원이 입력한 침대 누운 시각)으로 정확하게 산출.

### 2.3 결측 처리 정책

| 차원 | 결측 시 대처 |
|------|-----------|
| C1 (주관) | feedback 미입력 일자 = NaN. *학습에서 제외* (해당 일자 학습 데이터에서 drop) — *그 차원의 학습 데이터만 영향*, 다른 차원은 그대로 사용 |
| C2 (잠복기) | sleep_detail 미수집 시 = NaN. 같은 처리 |
| C3 (시간), C4 (효율) | sleep_summary는 거의 항상 존재. NaN ≈ 0건 가정 |

→ *4 모델이 서로 다른 학습 데이터 크기*를 가질 수 있음. 본 phase에선 *각 차원 독립 모델*이라 OK.

### 2.4 feedback.sleep_score 3단계 → 4단계 확장 (사용자 결정, *코드 변경 필요*)

**Before** (현재): `별로/보통/잘잤어!` → 0/1/2 (3단계)
**After**: `최고/잘잤어/못잤어/최악` → 0/1/2/3 (4단계, PSQI 다른 차원과 *동일 규모*)

**왜 변경**: PSQI C2·C3·C4가 모두 0~3 점수인데 C1만 0~2면 *합산 시 가중치 비대칭*. 0~3로 통일해 *동일 규모로 합산* 가능.

**코드 변경 범위**:

| 파일 | 무엇 |
|------|------|
| `streamlit_app/streamlit_feedback.py` | 입력 UI 3개 버튼 → 4개 버튼 (`최고`/`잘잤어`/`못잤어`/`최악`) |
| `feedback_api/main.py` | `sleep_score` 검증 로직 변경 — `0 ≤ score ≤ 3` |
| Alembic 마이그레이션 | `sleep_feedback` 테이블의 `sleep_score` CHECK 제약 갱신 |
| `ai_service`의 `read_feedback_db` | sleep_score를 features로 사용하던 곳은 *값 분포만* 영향 (정수 그대로 사용) |

**기존 데이터 마이그레이션 정책**: 변경 시점 이전 sleep_score(0/1/2)는 정확한 *4단계 매핑 불가능*. 두 옵션:

| 옵션 | 무엇 | trade-off |
|------|------|---------|
| **A (권장)** | 기존 0/1/2는 *학습에서 제외* (NaN 처리). 4단계 시작 후 데이터만 학습 | 정직, 다만 학습 데이터 일시 감소 |
| B | 보수적 매핑 — 0(별로)→3(최악), 1(보통)→2(못잤어), 2(잘잤어)→1(잘잤어). 0(최고)는 신규만 | 데이터 보존, *최고* 클래스 결측 |

→ **옵션 A** 채택. 정확성 우선.

**작업 시점**: Phase A 안에서 *선결 조건*. PSQI 점수화 함수가 4단계 sleep_score를 가정하므로 이 작업이 먼저 끝나야 다음 단계 진행 가능.

### 2.5 저녁 시간대 세분화 — 운동 *종료* 시각 기준

**왜 세분화**: 일반 회원의 운동 시간대 선택이 *저녁대에 집중*. 현재 `steps_evening(18–24)` 단일 binning은 *취침 직전 운동(20-22)*과 *충분한 여유 운동(18-20)*을 구분 못 함 → C2 잠복기 차원에 영향 큰 신호 손실.

**Before** (현재 22 features, `experiments/REPORT.md` §1.2):
```
운동 시간대 (7) — steps_morning, steps_afternoon, steps_evening(18–24), steps_night, last_active_hour, pre_sleep_steps_0_2h, pre_sleep_steps_2_4h
```

**After** (24 features):
```
운동 시간대 (8) — steps_morning, steps_afternoon, steps_evening_18_20, steps_evening_20_22, steps_night, last_active_hour, pre_sleep_steps_0_2h, pre_sleep_steps_2_4h
                                                  ↑ 운동 종료 시각 18-20시           ↑ 종료 20-22시 (취침 직전)
```

**산출 로직** (운동 *종료* 시각 기준 — 취침까지 거리에 직결):
```python
# 강도 기반 운동 day 식별 + 운동 종료 시각
df_min["is_workout_minute"] = df_min["steps"] >= STEPS_INTENSITY_THRESHOLD   # 또는 azm-기반
df_workout = df_min[df_min["is_workout_minute"]]
workout_end_hour = df_workout.groupby("date")["hour"].max()                  # 그 day의 마지막 운동 시각

# 종료 시각이 18-20에 포함되는 day의 steps 합 (저녁 일찍)
df["steps_evening_18_20"] = df_min.loc[
    df_min["date"].isin(workout_end_hour[(workout_end_hour >= 18) & (workout_end_hour < 20)].index)
    & df_min["hour"].between(18, 20)
].groupby("date")["steps"].sum()

# 종료 시각이 20-22에 포함되는 day (취침 직전)
df["steps_evening_20_22"] = df_min.loc[
    df_min["date"].isin(workout_end_hour[(workout_end_hour >= 20) & (workout_end_hour < 22)].index)
    & df_min["hour"].between(20, 22)
].groupby("date")["steps"].sum()
```

→ **가설**: C2 잠복기 모델이 `steps_evening_20_22`에 *강한 음의 SHAP*을 잡을 것 — 취침 직전 운동이 잠복기 길게 만든다는 수면 위생 권고와 일치.

**작업 시점**: Phase A.3에서 새 산출 함수 작성 + Phase B 학습 데이터에 이미 24 features로 진입.

---

## 3. 단계별 실행 계획 (7 phase, 누적 ~5주)

### Phase A — feedback 4단계 확장 + 저녁 세분화 features + PSQI 점수화 함수 + 침대 시각 수집 (~5.5일)

#### A.1 feedback.sleep_score 4단계 확장 (선결 조건, ~1일)

§2.4의 *코드 변경 범위* 적용:
- `streamlit_app/streamlit_feedback.py` UI 3 → 4 버튼
- `feedback_api/main.py` 검증 로직 0~3
- Alembic 마이그레이션 — `sleep_feedback.sleep_score` CHECK 갱신
- 기존 0/1/2 데이터 = *학습 제외 정책 (옵션 A)*

#### A.2 저녁 세분화 features 산출 함수 (~1일)

§2.5의 *산출 로직* 적용:
- `experiments/lib/features.py` 신규 — `compute_evening_split(activity_1min)` 함수
- `steps_evening_18_20` / `steps_evening_20_22` 컬럼 산출 (운동 종료 시각 기준)
- 회원 23RK3S 데이터로 분포 검증 — 두 새 컬럼이 *서로 다른 일자* 분포를 보이는지

#### A.3 PSQI 점수화 함수 (~2일)

**산출물**: `experiments/lib/psqi.py`

**구현**:
```python
def compute_psqi_scores(daily: pd.DataFrame, feedback: pd.DataFrame, sleep_detail: pd.DataFrame) -> pd.DataFrame:
    """일별 4 차원 점수 산출. NaN은 해당 차원만 결측 처리.
    feedback.sleep_score는 4단계(0~3) 가정 — A.1 선결.
    
    Returns: DataFrame with columns
        [user_id, date, c1_subjective, c2_latency, c3_duration, c4_efficiency, score_total]
    """
    # 각 차원 매핑 + 결측 정책
    ...
```

**검증**: 회원 23RK3S의 520일 데이터로 4 차원 점수 분포 확인. 차원별 결측률 보고. *기존 3단계 sleep_score 데이터*가 옵션 A로 제외된 *유효 일자 수* 박제.

#### A.4 침대 누운 시각 수집 (C2 잠복기 정확도 보강, ~1.5일)

**왜 필요한가**: Phase B 검증 결과 C2(잠복기) 차원이 baseline 미달. 분포가 *floor effect*(거의 0점에 몰림)인 본질적 원인 중 하나가 *측정 정확도 한계* — Fitbit의 *첫 wake 단계*를 *침대 누운 시각*으로 근사하는 방식은 *실제 누운 시각*을 짧게 잡는 경향이 있어 잠복기가 과소 추정됨.

**보강 흐름**: 회원 측 streamlit-feedback UI에 *"침대에 누웠어요" 버튼*을 추가해 *그 시점의 timestamp*를 서버에 박제. PSQI C2 산출 시 *Fitbit 첫 비-wake 시각 - 회원 입력 침대 시각*으로 정확하게 계산.

**코드 변경 범위**:

| 파일 | 무엇 |
|------|------|
| `streamlit_app/streamlit_feedback.py` | *"침대에 누웠어요"* 버튼 추가. 누르면 현재 timestamp + uid를 feedback_api로 POST |
| `feedback_api/main.py` | 새 endpoint `POST /bedtime-log`. 새 테이블 `bedtime_log(user_id, date, bedtime_at TIMESTAMPTZ)` |
| Alembic 005 마이그레이션 | `bedtime_log` 테이블 신규 생성 |
| `experiments/lib/psqi.py` | `estimate_latency_minutes()`를 *bedtime_log 우선, 없으면 sleep_detail wake 누적 fallback* 형태로 확장 |
| `experiments/lib/datasets.py` | `add_psqi_targets()`가 bedtime_log를 함께 로딩 |

**fallback 정책**: 회원이 *버튼 안 누른 일자*는 기존 *sleep_detail wake 누적* 근사 그대로 사용. 즉 점진 전환 — 회원 입력 일자가 늘수록 C2 정확도 향상.

**검증 — Phase B 재학습**: A.4 적용 후 *충분한 입력 데이터*가 누적되면 Phase B 학습을 재실행. 가설 — *bedtime_log를 활용한 일자에서 C2 분포가 더 넓어져* baseline 이김 가능. 만약 여전히 미달이면 plan §4 Risks #2의 *ordinal classification* 또는 §5 *C2 차원 제외 + 3 차원 합산*으로 전환.

**시간 예산**: ~1.5일. UI 버튼 + endpoint + 테이블 + psqi.py 확장 + Phase B 재학습.

**작업 시점**: Phase B 결과(C2 baseline 미달) 후 *분기 결정*된 옵션. 학교 프로젝트 운영 미실시이므로 *코드 박제*까지만, 실측 데이터 누적은 별 환경에서.

### Phase B — 4 차원별 CatBoost + holdout 평가 (~3일)

**산출물**: `experiments/psqi_4dim_models.ipynb` (신규 노트북)

**구현 흐름**:
1. **24개 features** (저녁 세분화 적용 후, §2.5) + 4 차원 target 준비
2. 차원별 학습:
   ```python
   for dim in ["c1_subjective", "c2_latency", "c3_duration", "c4_efficiency"]:
       valid = df.dropna(subset=[dim])
       cat_dim = train_cat(valid, target=dim)   # holdout 7일 분리
       rmse[dim], mae[dim] = evaluate(cat_dim, valid)
   ```
3. 차원별 RMSE/MAE 표 + 합산 점수 RMSE

**비교 baseline (axis별로 분리)**:
| Baseline | axis | 산출 | 의미 |
|----------|------|------|------|
| ⭐ Naive (차원별) | C1·C2·C3·C4 *각각* | 차원당 `mean(차원 점수)` 4개 | *information coverage* 입증의 핵심 — 각 차원 모델이 단순 평균을 이겨야 |
| Naive (합산) | PSQI 합 (0~12) | `mean(PSQI 합)` 상수 | 4 모델 합산 결과가 단순 평균을 이겨야 |
| Multi-output regression | PSQI 합 + 차원별 | CatBoost `loss_function='MultiRMSE'` | 4 차원 동시 학습의 통계 효율 우위 — *기록만*, 우열 결정은 후속 |

> ⚠️ **삭제된 baseline** — *단일 efficiency 모델 변환*: efficiency 모델은 C1·C2·C3에 *어떤 정보도 없음*. 평균값을 박제해 합산 RMSE를 내는 비교는 *axis 다른 두 모델의 부정한 비교*. PSQI 분리의 가치는 *예측 가능한 차원이 1 → 4로 늘어남*(information coverage)이지 *같은 차원에서 더 정확한 것*이 아님. 기존 efficiency 모델을 *RMSE에서 이길 필요 없음*.

**합격 기준** (PASS condition):
- ⭐ C1·C2·C3·C4 *각각이* 차원별 naive baseline 이김 — *information coverage* 입증
- 합산 RMSE < 합산 naive baseline — 단순 평균보다 의미 있는 합산
- multi-output과의 차이는 *기록*만 — 현 phase에서 우열 결정 안 함 (*해석 우위*가 trade-off의 명분)

### Phase C — 차원별 SHAP 분석 (~2일)

**산출물**: 같은 노트북에 SHAP 섹션 추가

**핵심 질문 — 4 차원이 *서로 다른* 변수를 top-1으로 잡는가?**

가설:
| 차원 | 예상 top SHAP 변수 |
|------|-----------------|
| C1 주관 | sleep_duration_h, bedtime_hour (주관-객관 격차 변수) |
| C2 잠복기 | pre_sleep_steps_0_2h, last_active_hour, hf_mean (HRV) |
| C3 시간 | bedtime_hour, waketime_hour, sleep_duration_h |
| C4 효율 | steps_morning, hf_mean, azm_fatburn (현재 efficiency 모델 패턴) |

→ 4 차원이 다른 변수를 잡으면 *분리 모델의 가치 입증*. 같은 변수만 잡으면 *multi-output이 더 나음* 신호.

**시각화**:
- 차원별 `shap_bar_psqi_c{N}.png` 4개
- 차원별 dependence plot (top-3 변수)
- 4 차원 SHAP의 *변수 중복도* 매트릭스

### Phase D — LLM 프롬프트 변경 + 운영 path 통합 (~5일)

**experiments에서 검증된 후** 운영 코드 통합. *Phase 6 commit*으로 분리 가능.

#### D.1 `predictions` 테이블 schema 확장 (Alembic 마이그레이션)

```sql
ALTER TABLE predictions
    ADD COLUMN psqi_scores       JSONB,    -- {c1, c2, c3, c4, total}
    ADD COLUMN psqi_rmse_test    JSONB,    -- {c1, c2, c3, c4, total}
    ADD COLUMN psqi_mae_test     JSONB,    -- 같음
    ADD COLUMN psqi_baseline     FLOAT;    -- naive baseline RMSE
```

→ *기존 efficiency 컬럼 보존* (expand-contract 패턴). PSQI 산출 실패 시 NULL 허용.

#### D.2 `coach_main` 변경

```python
# 기존: 단일 모델
cat = train_cat(train_master)
pred = float(cat.predict(X_inference.tail(1))[0])

# 신규: 4 모델 + 합산
psqi_models = {dim: train_cat_dim(train_master, dim) for dim in PSQI_DIMS}
psqi_preds = {dim: float(psqi_models[dim].predict(X_inference.tail(1))[0]) for dim in PSQI_DIMS}
psqi_total = sum(psqi_preds.values())
```

#### D.3 LLM 프롬프트 구조 변경

```text
[현재] SHAP top-6을 한 표로 주입
[보완] 차원별 SHAP top-3을 4개 표로 주입 + 각 차원 점수

PSQI 종합 점수: 7/12 (높을수록 수면 질 ↓)
- C1 주관:   2/3 (보통)        ← top SHAP: bedtime_hour
- C2 잠복기: 2/3 (31~60분)     ← top SHAP: pre_sleep_steps_0_2h
- C3 시간:   1/3 (6~7h)        ← top SHAP: sleep_duration_h
- C4 효율:   2/3 (75~84%)      ← top SHAP: steps_morning
```

→ LLM이 *가장 약한 차원*(점수 가장 높은 차원) 우선으로 코칭 메시지 생성.

#### D.4 옵트인 default 0 — 안전 패턴 일관

```yaml
# docker-compose.yml
ai_service:
  environment:
    USE_PSQI_MULTITARGET: "0"   # 1 = 4 차원 분리 모델, 0 = 기존 efficiency 단일 (default)
```

→ Phase 1~5와 같은 안전 원칙. 옵트인 검증 충분 후 default 1로 전환.

### Phase E — 검증 & 리포트 (~2일)

**산출물**: `experiments/PSQI_REPORT.md`

**구성** (Phase 1~5 리포트 패턴 일관):
- 메타 (작업 기간, spec, 의존 commit)
- 변경 요약 표
- Before/After/Why 박제 (4 차원 모델 / SHAP 분리 / LLM 프롬프트 / DB schema)
- 검증 결과 표 — RMSE 비교, baseline 우위, SHAP 분리도
- 면접 Q&A 시뮬레이션 (~5개)
- Non-Goals — multi-output 우위 시 전환 정책 / 신뢰도 가중 합산 / 잠복기 측정 보강 / 수면 시간·운동-수면 간격 grid (Phase F+1)

### Phase F — Constrained Forward Simulation 추천 (~5일, Phase A~E PASS 후)

**전제**: Phase B·C에서 4 차원 모델이 차원별 naive baseline을 모두 이김 (PASS condition).

#### F.1 Cold-start exploration round-robin (4주, ~1일 코드 작업)

**문제**: 신규 회원은 *positivity 영역* (시도해 본 시간대) 데이터가 0건. Forward simulation 후보가 없음.

**해결**: 첫 4주는 *exploration phase* — 회원에게 *주 단위로 다른 시간대* 운동을 권장해 데이터 균등 수집.

```python
# experiments/lib/exploration_phase.py (신규)
EXPLORATION_WEEKS = 4
EXPLORATION_SLOTS = [           # 주 단위 round-robin 슬롯
    ("morning", 8, 12),
    ("afternoon", 12, 18),
    ("evening_18_20", 18, 20),
    ("evening_20_22", 20, 22),
]

def recommendation_mode(uid, train_master) -> str:
    weeks_active = (today() - train_master["date"].min()).days // 7
    if weeks_active < EXPLORATION_WEEKS:
        # 주차 % 4로 round-robin
        slot = EXPLORATION_SLOTS[weeks_active % len(EXPLORATION_SLOTS)]
        return f"exploration", slot
    else:
        return "exploitation", forward_simulation_recommendation(uid)
```

→ 트레이너 카드에 *"이 회원은 cold-start n주차/4주. 추천은 데이터 수집 round-robin입니다"* 명시.

#### F.2 Positivity 영역 정의 + Realistic input 빌더 (~1일)

```python
# experiments/lib/recommend_psqi.py (신규)
MIN_DAYS_PER_SLOT = 5

def positivity_constrained_slots(uid, df_min) -> list[int]:
    """그 회원이 *5일 이상 시도해 본* 시간대만 후보."""
    candidates = []
    for h in range(6, 23):
        days = (df_min[df_min["hour"] == h].groupby("date")["steps"].sum() > THRESHOLD).sum()
        if days >= MIN_DAYS_PER_SLOT:
            candidates.append(h)
    return candidates

def build_realistic_input(uid, slot_hour, train_master) -> pd.DataFrame:
    """그 시간대에 운동한 *과거 day들의 features 평균*을 base로.
    
    이렇게 하면 features 간 conditional dependency가 자동 보존되어
    모델 입력이 학습 분포 안에 머무름 (외삽 회피).
    """
    past_days = train_master[train_master["main_workout_hour"] == slot_hour]
    return past_days[FEATURES].mean()
```

#### F.3 Constrained grid search — PSQI 합산 최소화 (~1일)

```python
def recommend_psqi_minimize(uid, available_slots, psqi_models, train_master):
    """가용 시간대 ∩ positivity 영역에서 PSQI 합산 *최소* 슬롯 top-3."""
    candidates = positivity_constrained_slots(uid, ...)   # 시도해 본 시간대
    feasible = [s for s in candidates if any(start <= s < end for start, end in available_slots)]
    
    if not feasible:
        return None, "회원 가용 시간대 안에 시도해 본 슬롯 없음. 새 시간대 시도 후 4주 후 재평가 권장."
    
    results = []
    for slot in feasible:
        X = build_realistic_input(uid, slot, train_master)
        psqi_preds = {dim: float(psqi_models[dim].predict(X)) for dim in PSQI_DIMS}
        total = sum(psqi_preds.values())
        results.append((slot, total, psqi_preds))
    
    results.sort(key=lambda r: r[1])     # 합산 *낮을수록* 수면 질 ↑
    return results[:3]
```

**1차/2차 추천 흐름**:
- **1차**: 회원 가용성 *없이* — `available_slots = [(0, 24)]` → 회원에게 *최고 슬롯 + 예측 PSQI 합산* 표시
- **2차**: 회원이 *불가능*하다고 답하면 가용 시간대 입력 받아 재계산 → 교집합 안 top-3

#### F.4 트레이너 카드 — 정형 HTML + 자연어 1단락 분리 (~1일)

**왜 분리**: 분석 §5.1과 일관 — LLM이 *정형 데이터*를 출력에 포함하면 환각 위험(점수 잘못 적기, 표 깨짐). 분리하면 *자연어 단락만* LLM 검증 부담.

**Layout**:
```
┌─ 정형 영역 (HTML/Streamlit, LLM 안 거침) ─┐
│ PSQI 종합: 5/12 (현재 7/12 → -2 개선)    │
│ ┌─C1─┬─C2─┬─C3─┬─C4─┐                  │
│ │ 1  │ 1  │ 2  │ 1  │                  │
│ └────┴────┴────┴────┘                  │
│ 추천 슬롯: 18:00-19:00                  │
│ 차원별 SHAP top-3:                       │
│  · C2(잠복기): pre_sleep_steps_0_2h ...  │
│  · ...                                   │
├─ 자연어 해설 (LLM, 1단락) ─────────────┤
│ "최근 오전 활동량이 늘어 수면 잠복기가    │
│  길어졌어요. 18시 이후 운동으로 옮기면   │
│  잠복기가 짧아질 가능성이 큽니다."        │
└────────────────────────────────────────┘
```

**구현**:
- `streamlit_app/streamlit_fitbit.py:build_pred_card` 변경 — 정형은 `st.metric`/`st.dataframe`/`st.altair_chart`로 직접
- LLM 프롬프트 변경 — "1단락 한국어 해설만, 점수·표·숫자는 출력하지 마세요" 명시
- 분석 §5.1 (LLM JSON schema) 부담 ↓ — 자연어 단락만 검증

#### F.5 옵트인 + DB 컬럼 (~1일)

```yaml
# docker-compose.yml
ai_service:
  environment:
    USE_PSQI_FORWARD_SIM: "0"   # 1 = Phase F 추천 활성, 0 = legacy recommend_workout_window
```

```sql
-- Alembic 마이그레이션
ALTER TABLE predictions
    ADD COLUMN recommendation_mode    TEXT,         -- 'exploration' / 'exploitation'
    ADD COLUMN psqi_predicted_total   FLOAT,        -- 추천 슬롯의 예측 PSQI 합산
    ADD COLUMN recommended_slot_psqi  JSONB;        -- {slot, predicted_c1..c4, predicted_total}
```

### Phase G — 진행 상태 추적 + 비동기 prediction job + 새로고침 무손실 복구 (~5일)

**전제**: Phase F까지 PASS. 이 phase는 *추천 알고리즘과 분리된 axis* — *호출 패턴*과 *진행 상태 추적*을 다룬다.

**왜 이 phase가 필요한가**: 분석 §9.5의 동기 호출 8가지 단점과 §9.6 멱등성의 *진행 중 보호* 부재를 푼다. 현재 `ai_service`에 `model_runs` 테이블은 있지만 *외부 조회 endpoint가 없어* 진행 상태를 클라이언트가 알 길이 없다. 또 streamlit이 *새로고침되면 작업이 사실상 분실*된다 — 결과는 DB에 박제돼도 *그것이 어느 호출의 결과인지* 클라이언트가 모른다.

#### G.1 `data_service` ingestion_runs 테이블 + endpoint (~1일)

```sql
-- Alembic 마이그레이션
CREATE TABLE ingestion_runs (
    run_id          UUID PRIMARY KEY,
    user_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',   -- queued | running | succeeded | failed
    current_step    TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    date_start      DATE,
    date_end        DATE,
    row_count       INT,
    error_message   TEXT
);
```

- `data_service`의 `/fetch` 호출이 `ingestion_runs` row를 INSERT(`queued`) → 단계별 UPDATE → 완료 시 `succeeded`/`failed`
- `GET /ingestion-runs/{run_id}` — 단일 작업 상태 조회 (Pydantic 응답 모델)
- `GET /ingestion-runs?uid={uid}&status=running` — *그 회원의 진행 중 작업* 자동 복구용

#### G.2 `ai_service` model_runs 외부 조회 endpoint (~0.5일)

- 현재 `model_runs` 테이블은 *내부 추적용*만. 외부에 노출하는 endpoint를 추가.
- `GET /model_runs/{run_id}` — Pydantic `ModelRunStatus` 응답 (uid, status, current_step, started_at, finished_at, error)
- `GET /model_runs?uid={uid}&status=running` — *uid 기반 활성 job 자동 복구* endpoint

#### G.3 비동기 prediction job 패턴 (~2일)

- `POST /predict-jobs` → 즉시 `202 Accepted { job_id }` (100ms)
- 백그라운드 worker가 *기존 coach_main 흐름*을 비동기로 실행 (FastAPI BackgroundTasks 또는 Celery+Redis)
- `GET /predict-jobs/{job_id}` — 진행 상태 + (완료 시) `prediction_run_id` 반환
- 완료된 결과는 `GET /predictions/{prediction_run_id}` (Phase 5 endpoint) 로 회수
- 옵트인 default 0 — 기존 `POST /predict` 동기 흐름 그대로 유지

#### G.4 streamlit 폴링 패턴 + 새로고침 복구 (~1일)

- streamlit이 `POST /predict-jobs`로 작업 시작 → `job_id`를 `session_state`에 보관
- 2~3초마다 `GET /predict-jobs/{job_id}` 폴링 → 진행률·current_step 표시
- 완료 시 `prediction_run_id`로 결과 endpoint 호출 후 카드 렌더
- *네트워크 일시 끊김*: streamlit 메모리에 `job_id`가 남아 있으므로 네트워크 복구 후 *같은 job_id로 폴링 재개*. 서버 작업은 *연결과 무관하게* 백그라운드에서 계속 진행
- *페이지 새로고침* 자동 복구 흐름:
  - 페이지 로드 시 `GET /predict-jobs?uid={uid}&status=running` 호출
  - 진행 중 job 있으면 그 `job_id`로 폴링 재개 → *작업이 처음부터 다시 시작되지 않음*
  - 진행 중 job 없으면 `GET /predictions?uid={uid}&latest=true`로 *가장 최근 완료된 추론* 회수해 카드 렌더
  - 둘 다 없으면 [데이터 수집] 버튼부터

#### G.5 새로고침 무손실 보장의 한계 명시 (~0.5일)

- *완전 무손실*은 아님 — `BackgroundTasks` 기반에서 *컨테이너 재시작* 시 메모리 작업 유실. 단 *DB 상태는 그대로* 남으므로 `model_runs.status`가 `running`인 채로 영원히 멈춤
- 후속(Phase G+1): Celery+Redis 기반으로 *worker 재시작 시 작업 재개*. *running 상태로 N분 이상 정체*된 row를 *failed로 자동 마킹*하는 cron
- 본 phase는 *네트워크 끊김 + 새로고침* 두 시나리오의 *클라이언트 측 무손실*까지만 보장. *서버 재시작* 무손실은 후속

---

## 4. Risks & Mitigation

| # | Risk | Mitigation |
|---|------|----------|
| 1 | C1(주관) 차원 데이터 결측률 50%+ | feedback 입력 캠페인 + 결측 일자 학습 제외 (그 차원만) |
| 2 | C2(잠복기) 측정 한계로 모든 회원 점수 0~1에 몰림 (Phase B에서 실제 발현) | 1순위: Phase A.4의 *침대 누운 시각 회원 입력*으로 정확도 보강 → 분포 확장. 2순위: 분포가 여전히 좁으면 *ordinal classification*으로 task 변경. 3순위: §5 Non-Goals — *C2 제외 + 3 차원 합산* |
| 3 | 4 차원 모두 동일 변수만 SHAP top-1 | multi-output regression 우위 신호. 분리 모델 *명분* 약화 → 리포트에 정직하게 박제 |
| 4 | 합산 RMSE > naive baseline | 모델이 *학습할 신호가 없음*. 후속 — features 보강(취침 거리 binary, AZM 강도 등) |
| 5 | Phase D 운영 통합 시 기존 흐름 회귀 | 옵트인 default 0 + 자동 fallback (PSQI 실패 시 efficiency 단일로) |
| 6 | LLM 프롬프트 길이 폭증 | top-k=6에서 차원당 top-3=12로 *증가*. F.4 정형/자연어 분리로 LLM 부담 ↓ |
| 7 | Cold-start 4주 동안 회원 *비협조* (지정 슬롯 안 따름) | exploration UI에 *시도 안 했음* 체크. 데이터 부족 시 5주차 → 8주차로 자동 연장 |
| 8 | F.2 positivity 임계값 5일이 회원 데이터 양에 비례 안 함 | adaptive — `max(5, total_active_days * 0.05)` 식. 데이터 적은 회원은 cohort fallback |
| 9 | F.4 HTML/LLM 분리 시 LLM 1단락이 *정형 정보를 또 적음* (지시 무시) | 시스템 프롬프트에 *"숫자·점수·표 출력 금지"* 강제 + 출력 후 정규식 검증 |

---

## 5. Non-Goals (현 phase 외 — 후속 박제)

| 항목 | 왜 미룸 |
|------|--------|
| **Multi-output regression의 우위 시 전환** | 본 phase는 *해석 우위* 의도적 선택. 우열은 후속 운영 데이터로 결정 |
| **신뢰도 가중 합산** | 4 차원 *비대칭 신뢰도*(C1·C2 약함) 인지하지만 *가중치 학습*은 별 phase |
| **수면 시간 grid + 운동-수면 간격 grid** (Phase F+1) | Phase F는 *운동 시각만* grid (~17 case). 수면 시간·간격을 추가하면 차원 폭증(~1,500 case) — 4 모델 검증 후 추가 |
| **C2 차원 제외 + 3 차원 합산** (3순위 fallback) | Phase A.4 (침대 시각 수집)로도 C2 분포가 충분히 넓어지지 않을 시 마지막 옵션. PSQI score_total을 c1+c3+c4로 정의. 임상 척도와 어긋나지만 *측정 한계 정직 인정* |
| **PSQI 7 component 완전 도입** | C5(약물)·C6(낮졸림)·C7(코골이)는 데이터 부재. 헬스케어 파트너 연계 시 후속 |
| **회원별 *맞춤 가중치*** | 회원에 따라 잠복기보다 시간이 중요한 경우. 임상 표준은 단순 합 |
| **K-fold CV** | 단일 holdout의 분산 한계 인지하지만 *expanding-window CV*가 시간 일관성 보존 — 별 phase |
| **Causal inference (RCT, DiD, within-subject 실험)** | Forward simulation의 *상관 → 인과* 도약은 본 phase에서 미해결. 분석 §4의 within-subject 4주 실험과 결합 시 진정한 인과 추정 가능 |
| **Celery+Redis 기반 worker 재시작 무손실** (Phase G+1) | Phase G는 BackgroundTasks 기반이라 *컨테이너 재시작* 시 진행 중 작업 유실. *서버 재시작 무손실*은 별도 phase로 분리 |
| **OpenTelemetry 분산 추적** (Phase G+1) | model_runs·ingestion_runs로 *서비스별 진행*은 추적되지만, *trace_id로 streamlit→data→ai→vLLM 한 묶음*은 별도 phase |

---

## 6. 작업 순서 — 의존성 그래프

```
Phase A (4단계 sleep_score + 저녁 세분화 features + psqi.py)
    │
    ▼
Phase B (4 차원 CatBoost + holdout)
    │
    ▼
Phase C (차원별 SHAP) ───────► [검증 게이트 #1]
    │                           - 차원별 RMSE < naive baseline?
    │                           - 합산 RMSE < 합산 baseline?
    │                           - 4 차원 SHAP 분리?
    ▼                                  │
Phase D (운영 path 통합)         (PASS)│
    │                                  ▼
    ▼                          Phase F (Forward simulation)
Phase E (리포트)                   ├─ F.1 cold-start round-robin (4주)
    │                              ├─ F.2 positivity + realistic input
    ▼                              ├─ F.3 PSQI 합산 최소화 grid
[검증 게이트 #2]                   ├─ F.4 트레이너 카드 HTML/LLM 분리
    │                              └─ F.5 옵트인 + DB 컬럼
    ▼                                  │
Phase 6 commit                  [검증 게이트 #3]
                                추천 슬롯 PSQI 합산 ≥ 2점 개선?
                                       │
                                       ▼
                                Phase G (진행 추적 + 비동기 + 복구)
                                  ├─ G.1 ingestion_runs 테이블 + endpoint
                                  ├─ G.2 model_runs 외부 조회 endpoint
                                  ├─ G.3 비동기 prediction job
                                  ├─ G.4 streamlit 폴링 + 새로고침 복구
                                  └─ G.5 한계 명시
                                       │
                                       ▼
                                [검증 게이트 #4]
                                네트워크 끊김·새로고침 시 작업 무손실?
                                두 번 클릭 시 진행 중 보호?
                                       │
                                       ▼
                                Phase 6+ commit (Phase F+G 통합)
                                       │
                                       ▼
                                [후속] Phase F+1 (grid 차원 확장)
                                       Phase G+1 (Celery+Redis · OpenTelemetry)
```

→ Phase B·C·F·G는 *experiments에서만* 작업. 운영 path(Phase D / Phase 6+)는 *각 검증 게이트 PASS 후*에만 손댐. Phase 1~5의 *옵트인 default 0* 패턴 일관.

---

## 7. 면접 답변용 한 줄 (보완 후 가정)

> "efficiency 단일 회귀는 PSQI의 *한 차원*(C4)만 봅니다. 그래서 PSQI 4 차원(주관·잠복기·시간·효율)으로 분해해 각 차원에 별도 CatBoost를 학습·합산했습니다. **두 모델은 axis가 달라 RMSE 직접 비교는 무의미** — PSQI 분리의 가치는 *RMSE 우열*이 아니라 *information coverage* (예측 가능한 차원이 1 → 4로 늘어남)입니다. 검증 프레임도 *각 차원이 차원별 naive baseline을 이기는가* + *4 차원 SHAP이 분리되는가*로 둡니다. C1 규모 통일을 위해 feedback.sleep_score를 3 → 4단계로 확장했고, *취침 직전 운동*의 효과를 분리하기 위해 저녁 시간대를 *운동 종료 시각 기준 18-20·20-22*로 세분화했습니다 (24 features). 검증 PASS 후 **Phase F**에서 *Constrained Forward Simulation* — (1) cold-start 4주 *exploration round-robin*으로 데이터 균등 수집, (2) *positivity 영역*(시도해 본 슬롯)으로 외삽 회피, (3) *realistic input*(과거 평균)으로 conditional dependency 보존, (4) *4 모델 합산 최소화* 슬롯 추천. 트레이너 카드는 *정형 HTML + 자연어 1단락 LLM* 하이브리드로 환각 위험 분리. 마지막 **Phase G**에서 *진행 상태 추적 + 비동기 prediction job + 새로고침 무손실 복구* — `ingestion_runs`·`model_runs`를 외부 endpoint로 노출하고, `POST /predict-jobs` + 폴링 패턴으로 동기 5분 블로킹과 *두 번 클릭 시 새 호출 중복*과 *새로고침 시 작업 분실* 모두를 해소. 운영 path 통합은 옵트인 default 0 패턴 일관."

---

## 8. 한 줄 결론

**experiments에서 *4 단계 검증 게이트* 통과 시에만 운영 path 통합** — (#1) 4 모델 학습·SHAP 분리, (#2) 운영 통합 회귀 0, (#3) Phase F 추천 슬롯이 PSQI 합산 ≥ 2점 개선, (#4) Phase G에서 네트워크 끊김·새로고침·두 번 클릭 시나리오 모두 *작업 무손실*. 어느 게이트라도 실패하면 *왜* 안 됐는지가 면접 답변 가치 (*"multi-output 우위로 전환"* / *"SHAP이 분리되지 않아 features 보강 후속"* / *"positivity 영역이 좁아 cold-start 8주로 연장"* / *"BackgroundTasks로는 컨테이너 재시작 무손실 안 되어 Celery+Redis로 진화"*). 어느 결과든 정직한 ML 작업의 흐름.
