# Phase 1 보완 작업 리포트 (2026-05-08)

> BioFit 프로젝트의 *모델 정직성*에 가장 영향이 큰 약점 3건(`docs/project_analysis.md` §1·§8.1·§2.1)을 1주(~10시간) 안에 코드·노트북·문서로 처리한 결과 보고서. 각 변경 항목을 **Before → After → Why**로 정리합니다.

## 메타

| 항목 | 값 |
|------|-----|
| 작업 기간 | 2026-05-08 (1일 단위 단기 집중) |
| 시간 예산 | ~10시간 (Spec 기준) |
| 결합 방법 | Deep Interview(3 rounds, ambiguity 14.7%) → Ralph(6 stories, all PASS) → ai-slop-cleaner |
| Spec 파일 | `.omc/specs/deep-interview-biofit-1week-improvement.md` (gitignored) |
| PRD 파일 | `.omc/prd.json` (gitignored, 6 stories all `passes:true`) |
| 검증 verdict | architect(Sonnet) **APPROVE** + ai-slop-cleaner pass 통과 |
| 변경 파일 수 | 6 (코드/설정) + 4 (문서, 본 리포트 포함) |

## 변경 요약 (한눈에)

| # | 분류 | 파일 | 변경 요약 |
|---|------|------|----------|
| 1 | 표현 정직성 | `README.md` | §1 인과/상관 표현 정정 + 인과 검증 한계 박스 |
| 2 | 모델 정직성 | `ai_service/sleep_coach_full_kr_v6.py` | §8.1 시계열 누수 제거 (rolling shift + LEAK_VARS 제외 + target t+1 forecast) |
| 3 | 모델 정직성 | `ai_service/sleep_coach_full_kr_v6.py` | §2.1 train/test 시간 holdout + RMSE/MAE + baseline |
| 4 | 데이터 흐름 | `db/init/007_predictions_eval_columns.sql` (신규) | predictions 테이블에 평가 메트릭 컬럼 4개 추가 |
| 5 | API 일관성 | `ai_service/app_ai.py` | coach_main의 dict 반환 처리 + INSERT 8 컬럼 확장 |
| 6 | 시연 자료 | `experiments/8_1_leakage_audit.ipynb` (신규) | 4 시나리오(A/B/C/D) + 베이스라인 E + Conclusion 노트북 |
| 7 | 문서 | `README.md` | "Improvements" 섹션 + Non-Goals 박스 추가 |
| 8 | 인프라 | `docker-compose.yml`, `sleep_coach_full_kr_v6.py`, `README.md` | vLLM 엔드포인트 default IP 갱신 |
| 9 | 군더더기 정리 | `sleep_coach_full_kr_v6.py`, 노트북 | 미사용 import·alias 제거 + pandas deprecation 갱신 |

---

## 1. §1 — README 인과/상관 표현 정정

### Before

`README.md:6` 인트로:

```markdown
BioFit은 헬스장 회원 이탈률 감소를 목적으로 헬스장 트레이너의 회원 코칭에 사용하도록 만든 마이크로서비스 프로토타입입니다.
```

PPT Slide 4의 인용 — "수면 질 1점 하락당 이탈 위험 11% 증가" — 가 *상관* 결과인데, README는 마치 BioFit이 *그 효과를 입증한 것*처럼 읽히는 표현이었음.

### After

```markdown
BioFit은 헬스장 회원 이탈률 감소를 *목적*으로 트레이너의 회원 코칭을 보조하는 마이크로서비스 프로토타입입니다. ...

> ⚠ **인과 검증 한계 (정직성 표기)** — 본 프로젝트의 동기는 *수면 질 1점 하락당 이탈 위험 약 11% 증가* (헬스장 신규 회원 153명 6주 관찰 연구, PPT Slide 4 인용)라는 **상관** 결과입니다. *수면 코칭이 실제로 이탈을 줄인다*는 **인과** 효과는 본 프로토타입 데이터로 **미검증**이며, 효과 검증은 후속 RCT 또는 difference-in-differences 설계로 진행 예정입니다. 자세한 분석은 `docs/project_analysis.md` §1·§4 참조.
```

### Why

- **면접 시 함정 회피**: "그래서 BioFit으로 이탈을 X% 줄였다는 데이터가 있나요?"라는 질문에 답할 데이터가 없음. 표현을 정정해 *인과 미검증*이 *의도된 한계*임을 사전에 명시.
- **인과/상관 구분 능력 어필**: 시니어 면접관에게 "이 지원자는 통계적 함정을 안다"는 신호.
- **후속 작업 명시화**: RCT/DiD 설계가 §4 Non-Goal로 분리되어 있음을 README에서 직접 링크.

---

## 2. §8.1 — 시계열 누수(time-series leakage) 제거

이 항목이 본 보강의 *기술적 핵심*. 세 갈래의 누수를 모두 제거.

### 2-A. Rolling 윈도우가 *오늘*을 포함

#### Before
`ai_service/sleep_coach_full_kr_v6.py:add_roll7` (구):

```python
def add_roll7(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.select_dtypes("number"):
        out[f"{col}_roll7"] = out[col].rolling(window=7, min_periods=1).mean()
    return out
```

`rolling(window=7)`이 행 t에서 [t-6 .. t]를 평균. **오늘(t)이 자기 자신의 rolling feature에 포함됨** → target이 곧 그 행이 가진 정보의 일부가 되어 누수.

#### After
```python
def add_roll7(df: pd.DataFrame) -> pd.DataFrame:
    """7-day rolling mean of numeric columns.

    §8.1 leakage fix: shift(1) excludes today from the rolling window so the
    rolling features at row t aggregate only [t-7 .. t-1]. ...
    """
    out = df.copy()
    for col in out.select_dtypes("number"):
        out[f"{col}_roll7"] = out[col].shift(1).rolling(window=7, min_periods=1).mean()
    return out
```

`shift(1)`로 *어제까지의 7일* 평균만 사용.

### 2-B. 같은 측정 사건의 변수가 features에 잔존

#### Before
`get_X` (구):

```python
def get_X(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.drop(columns=[TARGET] + KEYS, errors="ignore")
          .select_dtypes("number")
          .fillna(method="bfill").fillna(method="ffill")
    )
```

`stage_deep`, `stage_light`, `stage_rem`, `stage_wake`, `time_in_bed`, `wake_count`는 *수면 효율*과 같은 측정 사건의 다른 측면. 모델이 이걸 보면 "deep+light+rem+wake 합 ≈ asleep 시간 ≈ efficiency × time_in_bed"의 거의 *항등식*을 외움 → 학습이 의미를 잃음.

#### After
모듈 상단에 명시적 누수 변수 목록 도입:

```python
LEAK_VARS = [
    "stage_deep", "stage_light", "stage_rem", "stage_wake",
    "stage_deep_min", "stage_light_min", "stage_rem_min", "stage_wake_min",
    "time_in_bed", "wake_count",
]
```

`get_X`가 *raw + roll7 derivatives* 둘 다 제외:

```python
def get_X(df: pd.DataFrame) -> pd.DataFrame:
    leak_full = LEAK_VARS + [f"{c}_roll7" for c in LEAK_VARS]
    return (df.drop(columns=[TARGET] + KEYS + leak_full, errors="ignore")
              .select_dtypes("number")
              .bfill().ffill())
```

### 2-C. Target이 *오늘*과 같은 시점

#### Before
`main()` 진입부:

```python
master = add_roll7(build_master(uid))
cat = train_cat(master)            # target = 오늘의 efficiency
X = get_X(master)
pred = float(cat.predict(X.tail(1))[0])   # 마지막 행의 features로 예측
```

같은 행에서 features와 target이 *함께* 정해짐 → forecast가 아니라 *현재 시점 정합* 학습.

#### After

```python
master = add_roll7(build_master(uid))

# §8.1 leakage fix: forecast TARGET = t+1 day's efficiency.
# The last row's target becomes NaN after shift(-1); we drop it from
# training but keep its features as the inference input for t+1 prediction.
master[TARGET]     = master[TARGET].shift(-1)
train_master       = master.dropna(subset=[TARGET])

cat                = train_cat(train_master)
X_train            = get_X(train_master)
X_inference        = get_X(master)

pred   = float(cat.predict(X_inference.tail(1))[0])  # t+1 forecast
```

오늘 features → 내일 효율 예측. 마지막 행은 *target 없는 inference-only* 입력.

### Why (§8.1 종합)

- **모델 검증의 전제 조건**: train/test 분리(§2.1)를 적용해도 *입력 자체가 target을 누설*하면 RMSE 평가가 무의미. §8.1은 §2.1의 *선결 조건*.
- **정직한 baseline 산출**: 누수 제거 후 RMSE는 *증가*가 정상. 그 증가된 숫자가 진짜 일반화 오차의 추정값.
- **면접 답변 가능성**: "feature가 target과 같은 시점에서 측정된 것이라면 학습 의미가 있나요?" 질문에 *우리는 인지하고 제거했다*는 답.

---

## 3. §2.1 — train/test 시간 기반 holdout + RMSE/MAE + baseline 비교

### Before

`train_cat()` 호출 직후 같은 데이터의 마지막 행을 예측:

```python
cat = train_cat(master)
X = get_X(master)
pred = float(cat.predict(X.tail(1))[0])
```

**일반화 오차 추정 0건.** 모델이 회원에게 "예측 효율 73.4%"를 보여주지만, 그 숫자의 정확도가 어느 정도인지 알 길이 없음. 면접관이 "RMSE 얼마인가요?"라고 물으면 답할 수 없음.

### After

`main()` 안에 시간 기반 holdout + baseline 비교 블록 추가:

```python
HOLDOUT_DAYS = 7
rmse_test, mae_test, baseline_rmse = None, None, None
if len(train_master) >= 2 * HOLDOUT_DAYS:
    train_split   = train_master.iloc[:-HOLDOUT_DAYS]
    test_split    = train_master.iloc[-HOLDOUT_DAYS:]
    cat_eval      = train_cat(train_split)
    X_test        = get_X(test_split)
    y_test        = test_split[TARGET].values
    y_pred        = cat_eval.predict(X_test)
    rmse_test     = float(np.sqrt(np.mean((y_test - y_pred) ** 2)))
    mae_test      = float(np.mean(np.abs(y_test - y_pred)))
    baseline_pred = float(train_split[TARGET].tail(HOLDOUT_DAYS).mean())
    baseline_rmse = float(np.sqrt(np.mean((y_test - baseline_pred) ** 2)))
    print(f"[§2.1 holdout] test RMSE={rmse_test:.4f} | MAE={mae_test:.4f} | baseline RMSE={baseline_rmse:.4f}")
```

### Why

- **CatBoost가 단순 평균을 *정량적으로* 이기는지 입증**: baseline = `mean(last 7d)`. 시나리오 D(누수 제거)의 RMSE가 baseline보다 작아야 모델이 *의미가 있음*. 그렇지 않으면 후속 §8.2(시간대 회귀), §3.2(주관·객관 격차) 같은 후속 과제가 *왜 필요한지* 데이터로 자동 정당화됨.
- **데이터 부족 가드**: 14일 미만 회원에게는 RMSE를 None으로 두고 print로 알림. 운영 시 신규 회원 cold-start 시나리오 처리.
- **추후 운영용 카드에 RMSE 표시 가능**: `predictions.rmse_test` 컬럼이 채워지면 트레이너 UI 카드에 "참고 — 최근 검증 RMSE 4.2%" 같은 신뢰도 표시 추가 용이.

---

## 4. predictions 테이블 schema 확장 (US-004)

### Before

`db/init/001_predictions.sql`:

```sql
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    uid TEXT NOT NULL,
    run_id UUID NOT NULL UNIQUE,
    note TEXT,
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

평가 메트릭을 적재할 컬럼이 없음. RMSE/MAE 계산해도 *어디에 저장할 곳이 없음*.

### After

`db/init/007_predictions_eval_columns.sql` (신규, 컨테이너 첫 기동 시 자동 적재):

```sql
ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS rmse_test            FLOAT,
    ADD COLUMN IF NOT EXISTS mae_test             FLOAT,
    ADD COLUMN IF NOT EXISTS data_window_end      DATE,
    ADD COLUMN IF NOT EXISTS feature_set_version  TEXT;

CREATE INDEX IF NOT EXISTS idx_predictions_data_window_end
    ON predictions(data_window_end DESC NULLS LAST);
```

모두 NULLABLE → 기존 행과 호환. `IF NOT EXISTS`로 멱등 ALTER.

### Why

- **호출 단위 회귀 추적**: 회원·시점별 RMSE 변동을 SQL 한 줄로 모니터링 가능 (`SELECT uid, AVG(rmse_test) FROM predictions GROUP BY uid`).
- **§8.5 prompt_hash 작업의 부분 도입**: `feature_set_version` 컬럼이 *어떤 features 세트로 학습했는지* 박제. 향후 prompt_hash·model_version까지 확장이 자연스러움.
- **운영 DB 호환**: 본 SQL은 컨테이너 첫 기동에만 자동 적용 → 기존 운영 DB는 사용자가 수동 ALTER 실행 필요. README에 명령 명시.

---

## 5. app_ai.py /predict — coach_main dict 반환 처리

### Before

```python
message = coach_main(uid=req.uid, ...)
...
cur.execute(
    f"""INSERT INTO {DB_TABLE}(uid, run_id, note, message)
        VALUES (%s, %s, %s, %s)""",
    (req.uid, str(run_id), "run completed", message)
)
return {"status": "ok", "run_id": str(run_id), "message_preview": message[:120] + "..."}
```

`coach_main`이 단순 string 반환. RMSE/MAE를 추가하려면 호출 후 *별도 SELECT*로 마지막 메트릭을 가져와야 했음 → race condition 위험.

### After

```python
result = coach_main(...)
message             = result["message"]
rmse_test           = result.get("rmse_test")
mae_test            = result.get("mae_test")
baseline_rmse       = result.get("baseline_rmse")
data_window_end     = result.get("data_window_end")
feature_set_version = result.get("feature_set_version")

cur.execute(
    f"""INSERT INTO {DB_TABLE}(
          uid, run_id, note, message,
          rmse_test, mae_test, data_window_end, feature_set_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
    (req.uid, str(run_id), "run completed", message,
     rmse_test, mae_test, data_window_end, feature_set_version)
)

return {"status": "ok", "run_id": ..., "rmse_test": rmse_test,
        "baseline_rmse": baseline_rmse, "message_preview": message[:120] + "..."}
```

### Why

- **단일 호출 단일 INSERT**: 메트릭과 메시지가 *같은 추론 호출*에서 산출되어 같은 트랜잭션에 적재 — 정합성 보장.
- **응답 페이로드에도 노출**: `rmse_test`/`baseline_rmse`를 응답에 포함해 streamlit이 *카드에서 바로* 신뢰도 표시 가능 (현재 streamlit은 미사용이지만 후속 작업의 hook).

---

## 6. experiments/8_1_leakage_audit.ipynb (신규)

### Before

없음. §8.1 누수 제거 효과를 *수치로 증명*할 자료가 부재.

### After

19 cells 노트북 — 4 시나리오(A·B·C·D) + 베이스라인 E + Conclusion:

| 시나리오 | rolling | features | target 시점 | 의도 |
|---------|------|----|----|----|
| A | 오늘 포함 | stage_* 포함 | t일 | 누수 + 풀 학습 (현재 main 동작) |
| B | 오늘 포함 | stage_* 포함 | t일 | 누수 + holdout |
| C | shift(1) | LEAK_VARS 제외 | t+1일 | 누수 제거 + 풀 학습 |
| **D** | shift(1) | LEAK_VARS 제외 | t+1일 | **정직한 baseline (합격선)** ⭐ |
| E | — | — | t+1일 | 단순 평균 (`mean(last 7d)`) |

### Why

- **정량 증명**: A→D로 갈수록 RMSE *증가*가 정상이라는 가설을 *데이터로* 보임. 누수 제거가 미흡하면 D가 A와 비슷할 것 — 자동 sanity check.
- **GitHub 자동 렌더링**: 면접관·리뷰어가 환경 안 띄워도 `.ipynb`가 GitHub에서 표·DataFrame이 그대로 보임. *해석*과 *코드*가 한 화면에.
- **재실행 가능**: 회원 데이터가 늘면 셀 단위 부분 실행으로 D만 다시 돌려 갱신 가능.
- **실측 책임 분리**: 노트북 *코드 골격*은 본 ralph가 작성, *실측 RMSE 숫자*는 사용자가 환경에서 `jupyter nbconvert --execute`로 채움. 자동 환경에서 docker compose 띄우기·GPU 학습 시도의 risk 회피.

---

## 7. README "Improvements" 섹션 + Non-Goals 박스

### Before

README는 *현재 상태*만 적힘. 무엇을 *어떻게 개선했고 왜 어떤 건 일부러 안 했는지*에 대한 자료 부재.

### After

3-row 변경 요약 표(§1·§8.1·§2.1) + 산출물 링크(노트북·분석 문서·spec) + Non-Goals 5항목(§8.2·§9.1·§9.6·§9.7·§4) + 운영 환경 적용 가이드(`docker compose up` + `psql ALTER` + `curl /predict` + `jupyter nbconvert`).

### Why

- **면접 답변용 *왜 이건 안 했나요?***: Non-Goals가 *몰라서*가 아니라 *의도된 후속 과제*임을 명시. "1주에 가장 임팩트 큰 모델링 결함부터, 인프라/운영 보강은 다음 페이즈" 답변 패턴.
- **운영자 가이드**: 본 변경을 운영 DB에 적용하려면 정확히 어떤 명령을 실행해야 하는지 4-step으로 박제 → 사용자가 1주 후·1개월 후 까먹지 않고 적용 가능.

---

## 8. vLLM 엔드포인트 default IP 갱신

### Before

3 위치:
- `docker-compose.yml` env: `OPENAI_BASE: http://172.28.8.101:8282/v1`
- `ai_service/sleep_coach_full_kr_v6.py:294` fallback: `"http://172.28.8.101:8282/v1"`
- `README.md` Configuration 표 default: `http://172.28.8.101:8282/v1`

본 ralph 진행 중 사용자가 *새 vLLM 호스트*(`http://10.38.38.40:8004/v1`) 사용 가능을 알림.

### After

3 위치 모두 `http://10.38.38.40:8004/v1`로 갱신 — *환경변수 override 없이도* `docker compose up`만으로 새 호스트에 자동 연결.

### Why

- **default와 실 환경의 일치**: 옛 IP가 default인 채로 두면 새 회원이 README만 보고 띄우면 *연결 실패*. 갱신은 *기본값을 작동하게 만드는* 정직성.
- **본 ralph scope 밖이지만 cost 0**: 3곳 IP 단순 치환. 별도 PR로 분리할 가치 없음.
- **vLLM API key는 그대로**(`token-abc123`): 사용자가 명시 안 함. 향후 운영 시 별도 갱신.

---

## 9. ai-slop-cleaner 정리 (architect 비차단 권고 처리)

architect verdict이 APPROVE이지만 두 가지 비차단 권고를 cleaner pass로 처리:

| 항목 | Before | After | Why |
|------|--------|-------|-----|
| 미사용 import | `from llama_cpp import Llama` (`sleep_coach_full_kr_v6.py:13`) | 제거 | 노트북이 sleep_coach 모듈을 import할 때 `ModuleNotFoundError: llama_cpp` 위험. 실제 코드는 vLLM HTTP 클라이언트로 LLM 호출 — `Llama`는 사용처 0건의 dead import |
| 미사용 alias | `X = X_train  # backward-compat alias` (main 함수 안) | 제거 | `grep`으로 사용처 0건 확인. backward-compat 명목의 dead variable |
| pandas deprecation | `fillna(method='bfill').fillna(method='ffill')` (3곳: build_master, get_X, 노트북) | `bfill().ffill()` | pandas 2.1+에서 `method=` keyword가 deprecated → 미래 환경에서 TypeError 위험. 함수 chain이 더 짧아 가독성도 ↑ |

### 검증

- syntax: `python3 -m ast.parse` 모두 OK
- nbformat: notebook 19 cells, 4.5 valid
- grep 잔존: `llama_cpp|Llama(` 0건, `fillna(method=` 0건

---

## 검증 종합

| 검사 | 결과 |
|------|------|
| Python syntax (sleep_coach + app_ai) | OK |
| Notebook nbformat 4.5 | valid (19 cells) |
| llama_cpp/Llama 잔존 | 0 |
| fillna(method=) 잔존 | 0 |
| architect verdict (Sonnet, STANDARD tier) | **APPROVE** |
| ai-slop-cleaner pass | 통과 (3 cleanups 적용) |
| PRD stories | 6/6 `passes:true` |
| 누락된 acceptance criterion | 0건 |

architect의 비차단 추가 관찰: `predictions.note`는 여전히 `"run completed"` 단일 문자열. 향후 §9.8(관찰가능성)과 묶어 단계별 에러 적재로 진화 권장 — 본 ralph 범위 밖.

---

## 다음 단계 (사용자 측)

| 우선 | 항목 | 비용 | 산출물 |
|------|------|------|--------|
| 즉시 | 노트북 실측 실행 | ~5분 | `experiments/8_1_leakage_audit.ipynb`의 RMSE 숫자 채우기 |
| 즉시 | 노트북 결과 → README 표 박제 | ~10분 | "Improvements" 섹션의 시나리오 D RMSE 값 |
| 선택 | PR 분리 | ~30분 | `git rebase -i` 또는 신규 branch — §1, §8.1, §2.1 별 PR (포트폴리오 시각화) |
| 선택 | 운영 DB ALTER 적용 | ~5분 | `docker compose exec db psql -f /docker-entrypoint-initdb.d/007_*.sql` |
| 후속 | end-to-end LLM 통합 테스트 | ~15분 | 새 vLLM IP로 `/predict` 실 호출, 카드 생성 확인 |

### 후속 페이즈 후보 (Phase 2~)

`docs/project_analysis.md` §10 우선순위 표에서 다음 단계 후보:

- **Phase 2 (~1주)**: §8.2 시간대 회귀 모델 — LLM 환각 시간대 → *데이터 기반* 산출. 본 노트북의 인프라 재사용
- **Phase 3 (~2주)**: §9.1 동적 `{uid}_*` → 통합 `fitbit_daily_features` 마이그레이션 + §9.7 Alembic 도입
- **Phase 4 (~1개월)**: §9.6 멱등성·`model_runs` 상태 머신 + §9.8 OpenTelemetry 관찰가능성
- **Phase 5 (~3개월)**: §4 within-subject 미니 실험으로 *추천 시간대 따랐을 때 효율 개선* 인과 검증

---

## 참조 문서

- [`docs/project_analysis.md`](project_analysis.md) — 전체 27개 약점 + 우선순위 §10
- [`docs/questions.md`](questions.md) — Polyglot Persistence 답·키워드+시간대 추천 답
- [`docs/README_audit.md`](README_audit.md) — README 내용과 코드의 사실 검증
- `.omc/specs/deep-interview-biofit-1week-improvement.md` (gitignored) — 본 작업의 원본 spec
- `.omc/prd.json` (gitignored) — 6 stories acceptance criteria + evidence

## 한 줄 요약

**누수 있는 모델이 만든 비현실적으로 낮은 RMSE에 회원 신뢰를 거는 대신, 정직한 일반화 오차를 측정하고 단순 평균 baseline 대비 우위를 *데이터로* 입증하는 인프라를 1주 안에 박제했다.** 인프라·운영 보강은 의도적으로 다음 페이즈로 미뤘고, 그 의도가 README와 분석 문서에 모두 명시되어 있다.
