# BioFit 프로젝트 논리적 약점 분석 및 보완 제안

> 본 문서는 취업 전략 관점에서 BioFit(C&S 2025, Team G) 프로젝트를 *코드·README·PPT·실험 데이터*에 근거해 비판적으로 점검하고, 면접·포트폴리오 보강 시 면접관이 파고들 만한 약점과 그것을 메우기 위한 *구체적 실험 설계 또는 논리 보강*을 제안합니다. 각 섹션은 **약점 → 왜 문제인가 → 보완 방법** 순서로 구성됩니다.

## 평가 프레임

| 축 | 질문 | 본 문서에서 다룸 |
|----|----|----|
| 인과 vs. 상관 | "수면을 개선하면 이탈이 줄어든다"는 가설이 본 프로젝트 데이터로 *입증*되었는가, 단지 *가정*되었는가? | §1, §2.3, §4 |
| 모델 신뢰성 | 모델이 만든 점수와 SHAP 근거가 의사결정에 쓰일 만큼 검증되었는가? | §2 |
| 타깃 적합성 | `sleep_efficiency`가 정말 "수면 질"의 대리 지표인가? | §3 |
| 검증 디자인 | 효과를 측정할 통제군·실험군이 설계되어 있는가? | §4 |
| 운영 신뢰성 | 출력 검증·보안·법규 측면에서 운영 단계에 진입할 수 있는가? | §5 |
| 비즈니스 가정 | ROI 추정에 들어간 가정이 현실적인가? | §6 |

---

## 1. "수면 질 개선 → 이탈 감소" 인과 가설의 근거 빈약 🔴

### 약점

PPT Slide 4가 인용하는 "153명 6주 트레이닝, 수면 질 1점 하락당 이탈 위험 11% 증가"는 *관찰 연구*에서의 **상관**입니다. BioFit의 핵심 기획(수면 코칭으로 이탈을 줄인다)은 이를 **인과**로 가정하고 있으며, 본 프로젝트의 데이터로는 그 인과가 입증되지 않았습니다.

### 왜 문제인가

1. **역인과 가능성** — "이미 이탈 의향이 있는 회원이 헬스장 출석에 흥미를 잃어 일과가 흐트러져 수면이 나빠진다"는 반대 방향 설명이 가능합니다. 인용 연구는 이 방향성을 구분하지 못합니다.
2. **공통 원인(confounder)** — 스트레스, 과업 부하, 가정 사정 같은 변수가 *수면 질 하락*과 *헬스장 이탈*을 동시에 일으켰을 수 있음.
3. **모집단 차이** — 인용 연구는 *처음 6주 트레이닝을 시작한 153명*. BioFit은 *기존 회원 전체*에 적용. 효과 크기 전이가 보장되지 않음.
4. 면접관이 "그래서 BioFit을 써서 이탈이 X% 줄었다는 증거가 있나요?"라고 물으면 **답할 데이터가 없음**.

### 보완 방법

#### A. 작은 RCT 또는 준실험 설계

- **참가 헬스장 1곳, 회원 ~60명을 무작위 두 그룹으로**:
  - 처치군: 트레이너가 BioFit 카드를 보고 회원 상담
  - 대조군: 동일 트레이너가 평소 방식으로 상담
- **결과 변수**: 30/60/90일 출석률, 재등록률, NPS
- **분석**: ITT(Intent-to-treat) + per-protocol; 사전 등록(pre-registration)으로 p-hacking 방지

#### B. RCT가 어렵다면 difference-in-differences

- 같은 헬스장에서 BioFit 도입 전 6개월 vs. 도입 후 6개월의 이탈률 변화를 *다른 헬스장(미도입)*과 비교.
- 도입 시점이 자연 실험(자연스럽게 발생한 변화)에 가깝게 처리될 수 있다면 인과 추정 가능.

#### C. 만약 데이터 수집이 불가능하면

- **포트폴리오 표현 수정**: "수면 코칭으로 이탈을 줄입니다" → "수면 패턴 기반 트레이너 보조 도구를 *프로토타입* 수준에서 구현, 효과 검증은 후속 과제로 정의"
- 면접에서 "현재 단계는 인과 가설이 아니라 *서비스 가능성* 검증이며, 다음 단계에 RCT를 어떻게 설계할지 준비된다"고 답할 수 있게 됨.

---

## 2. 모델 검증의 부재 🔴

### 약점 2.1 — train/test 분리 없는 모델 학습

`ai_service/sleep_coach_full_kr_v6.py:180-186`:

```python
def train_cat(df: pd.DataFrame) -> CatBoostRegressor:
    model = CatBoostRegressor(iterations=500, depth=6, learning_rate=0.05, ...)
    model.fit(get_X(df), df[TARGET])
    return model
```

전체 데이터로 학습한 직후 같은 데이터의 마지막 행에 대해 예측합니다. 본질적으로 **암기 결과를 사용자에게 보여주는 셈**.

### 왜 문제인가

- "예측 효율 73.4%"라는 숫자가 LLM 프롬프트에 들어가지만, 그 숫자의 *일반화 오차(generalization error)*에 대한 어떤 추정도 없음.
- 회원이 적은 초반엔 모델이 거의 평균을 외움. SHAP이 산출하는 "기여 변수"도 의미가 약함.
- 면접관이 "RMSE/MAE 얼마인가요?"라고 물으면 답할 수 없음.

### 보완 방법

1. **시간 기반 holdout**: 마지막 7일을 test로 빼고 그 이전 데이터로 학습. RMSE/MAE를 `predictions` 테이블에 함께 기록.
2. **회원별 모델 신뢰도 게이트**: 학습 데이터 < N일이거나 검증 RMSE > τ이면 사용자에게 "데이터 누적 중, 정확도 낮음"으로 표시.
3. **글로벌 base 모델 + 회원별 fine-tune**: 신규 회원의 cold-start 성능 확보.
4. **베이스라인 비교**: 단순 평균 예측, 1주 평균 예측 대비 CatBoost가 얼마나 개선되는지 정량화.

### 약점 2.2 — SHAP를 "원인"처럼 표시

`sleep_coach_full_kr_v6.py:188-191`이 추출한 SHAP top-k 값을 LLM 프롬프트에 *지표 | 현재값 | 영향* 표 형태로 주입합니다. 트레이너 화면 카드에는 이 값이 그대로 또는 LLM 해설 형태로 노출됩니다.

### 왜 문제인가

SHAP은 **모델이 그렇게 본 이유**를 설명할 뿐, **그 변수가 실제로 수면에 영향을 미친 원인**은 아닙니다. 모델이 잘못 학습되어도 SHAP은 자신감 있는 해설을 제공합니다(garbage-in, confident-out).

### 보완 방법

- **표현 수정**: "이 변수가 수면 효율을 낮추었습니다" → "모델이 이번 예측에서 가장 비중을 두고 본 변수입니다"
- **모델 신뢰도 표시**: 검증 RMSE를 함께 표시. 예: "참고 — 최근 7일 검증 RMSE 4.2%"
- **인과 추론 보강(중장기)**: 동일 회원의 변수 *변화*와 *이후 효율 변화*의 관계를 시간 지연 회귀로 점검. 진정한 인과가 의심되는 변수만 코칭 대상으로.

### 약점 2.3 — 자기 개선 루프의 "이행 여부 판단"을 LLM에 위임

`FOLLOW_TMPL`은 LLM에게 "이번 데이터가 지난 코칭을 잘 지켰는지 여부를 먼저 한 문장으로 판단"하도록 요구합니다. 그러나 LLM은 *지난 코칭 텍스트*와 *이번 주 시계열*만 보고 "지켰는지"를 판단해야 하는데, 이는 본질적으로 ground truth 없이 *추측*입니다.

### 왜 문제인가

- LLM이 환각으로 "잘 지키셨네요"를 발화 → 트레이너가 회원에게 잘못된 칭찬 전달 → 신뢰 하락.
- 면접관이 "이행 여부를 어떻게 측정하나요?"라고 물으면 "LLM이 본문을 보고 추정합니다"는 답이 됨.

### 보완 방법

LLM에게 추측을 시키지 말고 **이행 여부를 정량 신호로 코드에서 추출**해 주입:

```python
adherence = {
  "exercise_window_match": is_actual_exercise_in_recommended_window(uid),
  "sleep_window_match":    is_actual_sleep_in_recommended_window(uid),
  "step_target_met":       weekly_steps >= recommended_steps,
}
```

이 dict을 프롬프트에 넣으면 LLM은 추측이 아니라 **사실 보고**를 기반으로 새 plan을 짤 수 있습니다.

---

## 3. 타깃 정의의 모호함 🟡

### 약점 3.1 — `sleep_efficiency`만으로 "수면 질"을 대표할 수 있는가

Fitbit의 `efficiency = time_asleep / time_in_bed`는 *침대에서 잠든 비율*입니다. 다음을 반영하지 못합니다:
- REM·deep·light 단계 분포
- 수면 단편화(awakenings)
- 수면 잠복기(sleep onset latency)
- 주관적 만족도

→ 95% 효율인데 "잘 못 잤다"고 느끼는 사람이 흔합니다.

### 보완 방법

- **다중 타깃**: efficiency + REM 비율 + 수면 잠복기 + 주관 점수의 가중 합 또는 multi-output regression.
- 또는 **주관 점수를 타깃**으로 옮기고 객관 지표는 features로. README의 Limitations에도 같은 방향이 적혀 있으므로 "다음 단계 작업"으로 명시 가능.

### 약점 3.2 — 주관 vs. 객관 격차 미모델링

체감 점수(`별로`/`보통?`/`잘잤어!` → 0/1/2)가 CatBoost의 *입력 feature* 중 하나로 들어갑니다. 그런데 *target*인 `efficiency`도 같은 날의 측정값. **같은 사건의 두 측정값이 둘 다 입력에 있으면 모델이 단순한 선형 매핑을 외워 SHAP의 정보가 무가치해질 수 있음**.

### 보완 방법

1. 주관 점수를 입력에서 빼고 *target*으로 옮긴다 (efficiency는 보조 features로).
2. 또는 별도 모델 두 개: ① 객관 모델, ② "주관-객관 격차" 모델. 격차가 큰 회원에게는 다른 코칭 메시지를 생성.

---

## 4. 비교군·검증 디자인 부재 🔴

### 약점

- 데모는 본인 1명의 520일 Fitbit 데이터(N=1)로 진행.
- "추천한 운동 시간대를 따랐을 때 효율이 개선되는가?"라는 핵심 질문에 답할 *비교군 데이터*가 없음.
- PPT Slide 31의 "달성 95%"는 *기능 구현 완성도*이지 *서비스 효과*가 아님.

### 보완 방법

#### A. within-subject 자기 통제 실험

같은 회원에게:
- 2주: 추천 시간대를 따른다 (treatment)
- 2주: 평소 시간대 유지 (control)
- 순서 랜덤화 + washout 1주

수면 효율의 차이를 paired t-test 또는 mixed-effect model로 비교. N=10 정도여도 effect size를 본 paper에 가까운 수준으로 추정 가능.

#### B. 기능별 ablation

"BioFit 카드 vs. 같은 데이터를 그냥 표로 보여줌"의 트레이너 사용성 비교 (사용자 만족도, 상담 시간, 발화량 등).

---

## 5. 운영·신뢰성·법규 약점 🟡

### 약점 5.1 — LLM 출력 검증 부재

`predictions.message`에는 LLM 원문이 그대로 적재됩니다. `streamlit_fitbit.py:74-127`의 `build_pred_card`는 `**summary**` / `**plan**` 마커로 split하므로, LLM이 형식에서 벗어나면 카드가 깨지거나 빈 셀을 보여줍니다.

### 보완 방법

- **structured output**: vLLM도 `response_format={"type": "json_object"}` 또는 grammar-constrained decoding 지원. Pydantic 스키마로 검증 → 실패 시 1회 재시도 → 폴백 메시지.
- **golden set 회귀 테스트**: 대표 입력 20개에 대해 LLM 출력 형식·금지어·길이를 정기 검사.

### 약점 5.2 — 의료 유사 조언과 책임 경계

`[plan]` 영역에 "운동/환경/생활/식단" 4줄을 요구합니다. *식단*은 한국 의료법상 의사·영양사 권한 영역과 겹칠 수 있고, 구체적 시간 권고가 운동 부상으로 이어진 경우 책임 소재가 모호.

### 보완 방법

- **면책 문구 자동 삽입**: 모든 카드 하단에 "본 제안은 일반적 권장이며 의학적 진단/치료가 아닙니다" 추가.
- **의료 경계 가드레일**: 시스템 프롬프트에 "약물·진단·식이요법 처방을 하지 말 것"을 명시. JSON 스키마에 위반 검출용 정규식.
- **risky 케이스 escalation**: 사용자 피드백이 1주 이상 "별로"가 지속되거나, HR 이상치 패턴 → 전문가 의뢰 권고로 전환.

### 약점 5.3 — 민감정보 처리·인증 미설계

- Fitbit Access Token을 평문 텍스트박스로 입력 받음 → 트레이너 화면이 노출되면 토큰 유출.
- 모든 회원의 시계열을 트레이너 한 명이 본문 그대로 조회 → PIPA(개인정보보호법) 민감정보 처리 동의·접근 통제 미설계.
- README가 인증 부재를 인정하므로 *프로토타입* 단서로 보호되지만, 면접에서 "운영 단계로 갈 때 어떻게 풀까요?"라는 질문이 나옴.

### 보완 방법

- **OAuth flow를 server-side로**: Fitbit OAuth redirect → ai_service가 토큰을 보관 → 트레이너 화면엔 토큰을 노출하지 않음.
- **트레이너 권한 모델**: 트레이너는 *자신이 담당하는 회원*만 조회. RBAC 매트릭스 + 감사 로그.
- **PIPA gap analysis** 1쪽 문서화: 동의 항목, 보존 기간, 파기 절차, 위탁 처리(vLLM 외부 서버) 고지.

---

## 6. 비즈니스 모델 가정의 단순성 🟡

### 약점

PPT Slide 26: 회원 200명 + 운동기구 50대 가정 → 9개월 차 흑자 전환. 그러나:

- **고장·유지보수**: ESP32+MPU6050 센서의 배터리 교체, 통신 끊김, 분실 등 비용 누락.
- **Fitbit 보유율**: 회원 중 *기존 워치 착용자 vs. 대여자* 비율을 어떻게 가정했는지 근거 없음.
- **이탈률 감소 효과**: BioFit이 "이탈을 X% 줄인다"는 가정에 의존하는데 §1·§4에서 본 대로 그 X가 미증명.
- **트레이너 학습 비용**: 트레이너가 BioFit 카드를 *상담에 효과적으로 활용*하기까지의 학습 곡선이 손익에 안 잡혀 있음.

### 보완 방법

- **민감도 분석 표**: 이탈 감소 효과를 0%, 5%, 10%, 20%로 변동시킬 때 손익 분기 시점이 어떻게 변하는지 시뮬레이션. *"가정이 틀려도 흑자 가능한 영역"*을 보임.
- **파일럿 1곳 실측**: 한 헬스장 6개월 운영 → 실제 비용·효과 기록 → 모델 보정.
- **Plan B / Plan C** 시나리오: Fitbit 미보유 회원이 50% 미만일 때, 운동 센서 설치율이 50% 미만일 때 등.

---

## 8. 재검토에서 추가로 발견한 약점

> 1차 작성 후 코드와 PPT를 한 번 더 훑어 *데이터 누수·서비스 핵심 가설·운영 사고 흐름*에서 추가로 빠뜨린 6개 약점을 보강합니다.

### 8.1 모델 평가의 시계열 누수(time-series leakage) 🔴

#### 약점

`build_master`는 `(user_id, date)` 단위로 일일 데이터를 합치고, target은 `efficiency`(=오늘의 효율)입니다. 그런데 **같은 날짜의 다른 변수들**(`stage_deep`, `stage_light`, `wake_count`, 수면 잠복기 등)이 모두 features로 들어갑니다. *오늘의 deep sleep 분*은 사실상 *오늘의 효율*과 거의 같은 사건의 다른 측면이라, 모델이 거의 자명한 매핑만 외워도 RMSE가 좋아 보입니다.

추가로 `add_roll7`이 산출하는 7-day rolling mean은 **오늘을 포함**합니다(`min_periods=1`). 즉 마지막 행의 rolling 값에 이미 target의 정보가 새어들어가 있음.

#### 왜 문제인가

- §2.1에서 train/test 분리를 도입해도 *입력 자체가 target을 누설*하면 평가가 무의미.
- 면접관이 "feature가 target과 같은 시점에서 측정된 거라면 학습 의미가 있나요?"라고 물으면 방어가 곤란.

#### 보완 방법

1. **타깃 시점 분리**: target을 `t+1일`의 효율 또는 `t일~t+6일`의 평균 효율로 미는 *forecast 문제*로 재정의. features는 `t-7~t일`의 시계열만.
2. **누설 변수 식별**: `efficiency`와 같은 측정 사건에서 파생된 변수(`stage_*`, `wake_count`, `time_in_bed`)를 features에서 제외. 외부 변수(steps, HRV, calories, 어제까지의 수면 패턴)만 사용.
3. **rolling 윈도우 보정**: `add_roll7`을 `df[col].shift(1).rolling(7)`로 변경해 오늘을 제외.

이 한 가지 변경만으로 모델이 학습할 만한 진짜 신호량이 드러나며 — 결과가 *나쁘게* 나올 수 있지만, **나쁜 결과가 정직한 baseline**입니다. 면접에서 "왜 이렇게 점수가 낮은가?"는 답할 수 있어도, "왜 이렇게 점수가 높은가?"의 누수 의심은 반박 불가입니다.

---

### 8.2 운동 시간대 추천의 알고리즘적 근거 부재 🔴

#### 약점

코드 흐름을 따라가 보면:
- `read_activity_hourly_db`가 회원의 *시간별 평균 활동량*에서 최저(`low_hr`)·최고(`high_hr`) 시각을 뽑아 프롬프트에 넣습니다.
- LLM이 그 정보를 보고 *권장 운동 시간대*를 자유롭게 산출합니다.
- 프롬프트 끝에는 **고정된 형식 강제**: `"운동 시작시간: 20:00, 운동 종료시간: 20:30"`.

그러면 LLM은:
1. 활동 시각대 통계와 SHAP top-k 변수를 보고
2. *논리적 추론으로* 권장 시간대를 산출하라는 임무를 받지만
3. 시작/종료 시각의 형식 예시(`20:00 / 20:30`)가 너무 구체적이라 자주 그대로 복사.

즉 **코칭의 핵심 결과물(운동 시간대)이 LLM의 환각에 의존**하며, *데이터 → 시간대*의 명시적 알고리즘이 없습니다.

#### 왜 문제인가

- 같은 사람의 다른 호출에서 시간대가 들쑥날쑥하거나, 다른 사람들에게 모두 같은 시간대(20:00~20:30)가 나올 위험.
- 핵심 가설("이 시간대 운동이 이 사람의 수면을 개선한다")이 모델 외부의 추측이라 *반증 불가*.
- 면접관이 "어떤 알고리즘으로 이 시간대를 뽑나요?"라고 물으면 답이 LLM뿐.

#### 보완 방법

1. **시간대 후보 → 수면 효율 회귀 모델**: 회원의 과거 `(운동 시간 분포, 그날 밤 수면 효율)` 쌍으로 회귀 학습. 새 회원은 cohort 평균으로 시작 → 데이터 누적되면 개인화.
2. **추천 결정은 코드에서, 설명만 LLM이**: 코드가 *권장 시간대 후보 3개*를 산출 → LLM은 그걸 *왜 권장하는지* 설명만. 형식 강제도 코드 측에서 후처리.
3. **검증**: 추천 시간대를 따른 회원의 수면 개선폭 vs. 따르지 않은 회원의 차이를 측정 (§4의 within-subject 실험과 묶을 수 있음).

---

### 8.3 코칭 메시지 품질 평가 루프 부재 🟡

#### 약점

- `predictions.message`에 코칭 메시지가 적재될 뿐, *회원이 그 메시지를 유용하다고 느꼈는지* 측정하는 신호가 없습니다.
- 트레이너가 카드를 회원에게 보여줬는지, 회원이 그것에 대해 어떤 반응을 보였는지의 데이터가 없음.
- 결과적으로 **데이터 기반으로 프롬프트/모델을 개선할 사이클이 닫혀 있지 않음**.

#### 왜 문제인가

- 면접관 단골 질문: "이 서비스가 좋은지 어떻게 측정하나요?" → 출석률(distal) 외에 코칭 메시지 품질의 *proximal* 지표가 없음.
- 토큰 비용은 추적하지만 비용 대비 *가치*는 추적하지 않음.

#### 보완 방법

1. **트레이너 thumbs up/down**: 카드 하단에 "이 메시지가 상담에 유용했나요?" 1-클릭 평가 → `predictions_feedback` 테이블에 적재.
2. **회원 follow-up**: 1주 뒤 회원 피드백 화면에 "지난주 받은 권장 사항을 시도해 보셨나요?" 한 문항 추가.
3. **golden set 사람 평가**: 한 달에 한 번, 트레이너 2~3명에게 무작위 5개 카드를 *블라인드*로 1~5점 평가시킴. 프롬프트 튜닝 시 회귀 검사 데이터로 사용.

---

### 8.4 group_service의 양방향 매칭·동의 흐름 부재 🟡

#### 약점

현재 `group_service`(구현되더라도)는 *나에게 어울리는 후보*를 일방적으로 산출합니다. 그러나 사회적 매칭은 본질적으로 *상호*적입니다:
- 상대방도 나를 받아들이는가?
- 양쪽 모두 동의가 있어야 실제 만남으로 이어지는가?
- 매칭 후 *연락 수단·약속 잡기*는 어떻게 처리되는가?

매칭 결과가 *목록*으로만 나오고 그 다음의 행동 흐름이 정의되지 않았습니다.

#### 왜 문제인가

- 매칭이 출석률을 높이는 건 *실제 만남이 일어났을 때*. 추천만 해두면 가설이 발현되지 않음.
- 면접관이 "매칭에서 만남까지 conversion이 얼마인가요?"라고 물으면 측정 자체가 안 됨.

#### 보완 방법

1. **상호 추천 그래프**: A→B 추천 *그리고* B→A 추천이 모두 발생할 때만 매칭 후보로 격상.
2. **단계별 동의 UI**: 트레이너가 "회원 A에게 회원 B를 제안하시겠습니까?" → A가 수락 → B에게 동의 요청 → B가 수락하면 연락처 교환.
3. **conversion funnel 측정**: 추천 → 트레이너 제안 → 회원 동의 → 첫 만남 → 4주 후에도 함께 운동 중. 각 단계 conversion 추적.
4. **그룹 세션은 capacity 관리 필요**: `group_sessions.capacity`만 정의되어 있을 뿐, 매칭 시 잔여 좌석 차감 로직 없음.

---

### 8.5 재현성·실험 추적의 부재 (MLOps) 🟡

#### 약점

`predictions` 테이블 스키마는 `(uid, run_id, note, message, created_at)`. 다음 정보가 빠져 있습니다:
- 사용된 **모델 버전**(CatBoost 하이퍼파라미터, 학습 데이터 윈도우)
- 사용된 **프롬프트 버전**(`SYS_PROMPT`, `FIRST_TMPL`/`FOLLOW_TMPL` 해시)
- 사용된 **LLM 모델·온도·top_p**
- 입력 데이터의 **스냅샷 식별자**(어떤 날까지의 데이터로 추론했는지)

LLM은 `temperature=0.3`로 비결정적입니다. 같은 회원·같은 데이터로 호출해도 결과가 다릅니다. 실험 후 *왜 결과가 바뀌었는지* 추적 불가.

저장소에는 `app-back.py`, `sleep_coach_full_kr_v6.bak.py` 같은 백업 파일이 git에 그대로 있어, 어느 버전이 어떤 결과를 만들었는지 코드 측에서도 모호.

#### 왜 문제인가

- 디버깅 시 "지난주에는 이런 메시지가 나왔는데 이번엔 다르다"의 원인 분석 불가.
- 면접관이 "프롬프트를 바꾼 뒤 품질이 좋아졌다는 걸 어떻게 보였나요?"라고 물으면 비교군 데이터 없음.

#### 보완 방법

1. **`predictions` 테이블 확장**:
   ```sql
   ALTER TABLE predictions
     ADD COLUMN model_version TEXT,
     ADD COLUMN prompt_hash CHAR(8),
     ADD COLUMN llm_params JSONB,
     ADD COLUMN data_window_end DATE;
   ```
2. **프롬프트 파일 분리**: `prompts/sleep_coach_v6.yaml` 등으로 외부화 → git tag로 버전 관리 → 호출 시 해시를 `prompt_hash`에 기록.
3. **temperature 0**: 운영 시연용 호출은 결정적으로(`temperature=0`), 실험용 호출만 `0.3` — 두 모드 구분.
4. **백업 파일 정리**: `*.bak.py`는 git에서 제거하고 git 히스토리로 추적 (이미 git이 있는데 굳이 파일 자체를 두는 건 노이즈).

---

### 8.6 운영 모니터링·SLO·폴백 부재 🟢

#### 약점

`token_usage` 테이블에 토큰이 기록되지만, 다음이 부재:
- 응답 시간(SLI)·에러율·가용성에 대한 *목표(SLO)*
- 회원당 일일 호출 한도, 토큰 한도, 비용 alert
- vLLM 서버가 다운되거나 timeout일 때의 **폴백 시나리오**(캐시된 마지막 메시지? 정중한 에러? 트레이너에게 알림?)

`streamlit_fitbit.py:171`은 `timeout=300`초로 호출하는데, 이는 *블로킹 5분*입니다. 트레이너가 카드를 띄우려다 5분 동안 화면이 멈춤.

#### 왜 문제인가

- 데모 환경에선 동작하지만 동시 사용자 N>3 시나리오에서 token 폭증·timeout 누적·트레이너 화면 멈춤이 동시에 발생.
- "운영 단계 진입 가능한가요?"라는 질문에 *기술적 답*이 없음.

#### 보완 방법

1. **비동기 호출**: AI 추론을 백그라운드 작업으로 큐잉(Celery, RQ, 또는 FastAPI BackgroundTasks). 화면은 즉시 "처리 중"을 보여주고 결과는 polling 또는 WebSocket으로.
2. **회원당 호출 한도**: 일일 1회 또는 6시간 1회로 제한. 초과 시 캐시된 결과 반환.
3. **vLLM 헬스체크 + 폴백**: `/predict` 호출 시 먼저 vLLM에 `GET /health`. 실패 시 LLM 부분만 건너뛰고 *CatBoost 예측 + SHAP 표*만 카드로 반환.
4. **메트릭 대시보드**: 응답 시간 p95, 에러율, 일일 토큰 비용, 회원당 호출 빈도 — Grafana나 Streamlit metric page.

---

## 9. MSA 구조와 서비스 간 데이터 흐름 설계 보완 🟡

> 이 섹션은 FastAPI, Streamlit, PostgreSQL, Docker Compose, vLLM 기반 MSA 구조를 *왜 이렇게 나눴는지*와 *서비스 간 데이터가 어떤 계약으로 흐르는지*를 면접/포트폴리오에서 설명할 수 있도록 보강합니다.

### 9.1 현재 구조는 "MSA"라기보다 Streamlit 중심 동기 오케스트레이션에 가까움

#### 약점

현재 호출 흐름은 다음과 같습니다.

```text
Streamlit(트레이너 UI)
  ├─ POST data_service /fetch  → PostgreSQL에 Fitbit 원천 테이블 적재
  ├─ POST ai_service /predict  → PostgreSQL에서 원천/피드백 조회 → CatBoost/SHAP/vLLM → predictions 저장
  └─ POST group_service /predict → PostgreSQL에서 users/preferred_slots/group_sessions 조회

Streamlit(회원 피드백 UI)
  └─ POST feedback_api /feedback → PostgreSQL에 {uid}_feedback 저장
```

#### 현재 구조가 실제로 작동하는 방식

현재 시스템에서 Streamlit은 단순 화면이 아니라 **사용자 입력 수집, 호출 순서 제어, 결과 조회, 카드 렌더링을 모두 담당하는 오케스트레이터**입니다. 트레이너가 화면에서 버튼을 누르면 Streamlit이 각 FastAPI 서비스를 순서대로 호출하고, 각 서비스는 다시 PostgreSQL을 공통 저장소로 사용합니다.

구체적으로는 다음 순서로 동작합니다.

```text
1. 트레이너가 uid, start_date, end_date, Fitbit token 입력

2. [데이터 수집·전처리 시작]
   Streamlit → data_service /fetch
   payload: { uid, start_date, end_date, token }

   data_service
     - token을 FITBIT_TOKEN 환경변수에 임시 주입
     - 현재는 Fitbit API 호출은 주석 처리되어 있음
     - /app/fitbit_csv/*.csv를 csv_to_db.py로 PostgreSQL에 적재
     - 테이블명은 CSV의 user_id와 파일명을 조합한 {uid}_{suffix}
     - 성공 시 { status: "ok" } 반환

   Streamlit
     - 응답이 ok이면 session_state.data_ready = True
     - session_state.last_uid = uid 저장

3. [AI 추론 실행]
   Streamlit → ai_service /predict
   payload: { uid }

   ai_service
     - uid만 받아 coach_main(uid)를 실행
     - PostgreSQL에서 {uid}_sleep_summary, {uid}_activity_1min,
       {uid}_feedback 등 uid 기반 동적 테이블을 직접 조회
     - CatBoost를 요청 시점에 학습
     - SHAP top-k를 계산
     - vLLM OpenAI-compatible endpoint를 호출해 코칭 메시지 생성
     - predictions 테이블에 { uid, run_id, message } 저장
     - { status: "ok", run_id, message_preview } 반환

   Streamlit
     - 응답의 message_preview를 사용하지 않고,
       다시 PostgreSQL predictions 테이블에서 최신 message를 직접 SELECT
     - message 문자열을 HTML 카드로 변환해 화면에 표시

4. [파트너·그룹 추천 보기]
   Streamlit → group_service /predict
   payload: { uid }

   group_service
     - 현재 uid 기반 개인 슬롯을 조회하지 않음
     - 코드에 고정된 CURRENT_USER_SLOTS와 DB의 preferred_slots/group_sessions를 비교
     - 시간대가 30분 이상 겹치는 파트너/그룹 반환

5. [숙면 피드백]
   회원용 Streamlit UI → feedback_api /feedback
   payload: { user_id, date, sleep_score }

   feedback_api
     - {user_id}_feedback 테이블을 동적으로 생성
     - sleep_score를 insert
     - 다음 ai_service /predict 호출 때 이 테이블이 feature/prompt 입력으로 사용됨
```

따라서 현재 구조의 핵심은 **API가 데이터를 직접 주고받는 구조가 아니라, 각 서비스가 PostgreSQL에 남긴 결과를 다음 서비스가 다시 읽는 구조**입니다. 이 방식은 데모 구현에는 단순하지만, 서비스 간 계약이 API 스키마가 아니라 "어떤 테이블이 어떤 이름으로 존재해야 한다"는 암묵적 규칙에 묶입니다.

표면적으로는 서비스가 분리되어 있지만, 실제 오케스트레이션 상태는 Streamlit 세션(`data_ready`, `last_uid`)에 있고, 각 백엔드 서비스는 공통 PostgreSQL의 테이블을 직접 읽고 씁니다. 즉 **서비스 간 API 계약보다 공유 DB 스키마가 결합 지점**입니다.

#### 왜 문제인가

추상적인 "결합도가 높다"는 표현이 아니라, 다음 4개 시나리오에서 코드가 구체적으로 깨집니다.

##### 시나리오 1 — 브라우저 새로고침 한 번이 곧 상태 분실

"데이터 수집 완료 → AI 추론 가능"이라는 진행 상태는 오직 Streamlit 클라이언트의 `session_state`에만 존재합니다 (`streamlit_fitbit.py:40-46, 158-160`):
```python
"data_ready": False,
"last_uid":   "",
...
st.session_state.data_ready = True
st.session_state.last_uid   = uid.strip()
```

트레이너가 [데이터 수집] 후 [AI 추론] 버튼을 누르기 *전에* 브라우저를 새로고침하거나 다른 페이지로 이동했다 돌아오면 `data_ready`는 `False`로 초기화됩니다. 그러면:

- DB에는 분명 회원 데이터가 적재되어 있는데(`{uid}_sleep_summary` 등 8개 테이블 존재), 서버 측에 "이 회원의 데이터가 준비됐는지" 묻는 API가 없으므로 Streamlit은 그 사실을 *알 수 없음*.
- [AI 추론] 버튼은 `disabled = (not data_ready or last_uid != uid)` 가드(`streamlit_fitbit.py:165-166`)에 걸려 *눌리지 않음*. 트레이너에게는 "왜 막혔는지" 단서가 없습니다.
- 트레이너가 [데이터 수집]을 한 번 더 누르면 `csv_to_db.py`가 `if_exists="replace"`로 동일 테이블을 다시 씁니다 — *데이터는 안 깨지지만* Fitbit API 재호출, 디스크 IO, 토큰 노출이 또 한 번 일어남.

→ MSA의 핵심 자산은 *서버 측 상태*인데, 본 시스템은 그것을 클라이언트(브라우저)에 위임했습니다.

##### 시나리오 2 — 동적 테이블명 변경 한 줄이 다른 서비스를 무음으로 깨뜨림

`data_service/csv_to_db.py:35`는 CSV 파일명을 그대로 테이블 suffix로 사용합니다:
```python
table_name = f"{uid}_{fname}"   # fname = CSV 파일 stem
```

`ai_service/sleep_coach_full_kr_v6.py:135-141`은 그 테이블명을 *문자열 리터럴*로 알고 있습니다:
```python
read_daily_db("sleep_summary", {"efficiency": "mean", ...}, uid)
read_daily_db("activity_sum",  {"steps":"sum", ...}, uid)
read_daily_db("resting_hr",    {"resting_hr":"mean"}, uid)
```

`data_service`팀이 다음 중 어느 하나만 해도:
- `sleep_summary.csv` 파일명을 `sleep_summary_v2.csv`로 변경
- 그 안의 `efficiency` 컬럼을 `sleep_efficiency_pct`로 rename
- 단위를 `[0,1]`에서 `[0,100]`으로 변경

→ `ai_service`는 *런타임에 첫 호출에서* `KeyError` 또는 `pandas.errors.UndefinedVariableError`로 죽습니다. PR 리뷰에서 grep 외에는 잡을 방법이 없고, contract test가 없으니 CI도 통과시킵니다. **마이크로서비스의 핵심 가치인 "독립 배포 가능성"이 정반대로 깨집니다** — `data_service`만 배포해도 `ai_service`가 망가집니다.

##### 시나리오 3 — 회원 200명이 되면 PostgreSQL 운영 도구가 N배 비례로 무거워짐

회원당 생성되는 테이블 수를 합산:

| 출처 | 회원당 테이블 수 |
|----|----|
| `data_service/csv_to_db.py` | 8 (sleep_summary, activity_sum, resting_hr, azm, heart_rate_1min, activity_1min, hrv, sleep_detail) |
| `feedback_api/main.py` | 1 (`{uid}_feedback`) |

회원 200명이면 PostgreSQL `pg_class` 카탈로그에 **약 1,800개 테이블**이 등록됩니다. PostgreSQL 엔진 자체는 견디지만:

- `pg_dump`/백업 시간이 카탈로그 크기에 비례 — 200명에서 5분 걸리던 게 1,000명이면 25분.
- DBA가 "이 컬럼에 인덱스가 빠진 테이블이 있는가?"를 점검할 때 1,800번 순회해야 함. 인덱스를 *전 회원에 일관되게* 만들어주는 도구를 직접 짜야 합니다.
- ORM(`SQLAlchemy`)이 metadata reflection을 하면 회원 수에 비례한 메모리 사용. 별도 처리가 없으면 첫 요청이 점점 느려집니다.
- 모니터링 도구(예: `pganalyze`, `pgwatch2`)의 대시보드가 회원 단위 분석을 못 함 — *모든 회원에 대한 sleep_summary 평균*을 구하려면 1,800개 테이블 UNION이 필요.

→ *기능*은 작동하지만, *운영 도구*가 한 자릿수 회원에서 두 자릿수 회원으로만 가도 깨집니다. 운영형으로 갈 수 없는 가장 직접적 이유입니다.

##### 시나리오 4 — 한 서비스 변경이 cascade로 다른 서비스 장애를 일으킴 (모놀리스의 단점 + MSA의 단점 동시)

서비스 간 결합 지점이 *API 계약*이 아니라 *DB 테이블 스키마*입니다:

- `data_service`가 `efficiency` 컬럼을 `[0,1]`에서 `[0,100]`으로 단위 변경 → `ai_service`의 `pred = float(cat.predict(X.tail(1))[0])`이 100배 큰 값을 LLM 프롬프트에 주입 → 코칭 메시지가 "예측 효율 8245%" 같은 값으로 나옴 (런타임 에러도 안 남, *조용한 데이터 오염*).
- `feedback_api`가 `sleep_score` 컬럼을 `int`에서 `text`로 바꿈 → `ai_service`의 `groupby(["user_id", "date"])["sleep_score"].mean()`이 `TypeError`로 죽음.

→ 이게 마이크로서비스의 가장 나쁜 실패 모드입니다. **모놀리스는 *컴파일 타임*에 타입 에러를 잡지만, 본 시스템은 *런타임 첫 호출*까지 모릅니다.** 동시에 마이크로서비스의 장점(독립 배포·독립 장애 격리)도 잃었습니다 — 모놀리스의 단점과 MSA의 단점을 *함께* 갖게 됩니다.

#### 보완 논리 — As-Is / To-Be

면접에서는 "현재는 데모 속도를 위해 DB 공유형 MSA로 구현했고, 운영형으로 전환할 때는 데이터 소유권과 계약을 분리한다"고 설명하는 것이 방어적입니다. 핵심 차이를 6개 축으로 정리하면:

| 축 | As-Is (현재) | To-Be (운영형) | 사용자 피드백 |
|----|----|----|----|
| 데이터 소유권 | 모든 서비스가 같은 PostgreSQL의 모든 테이블을 자유롭게 read/write | 서비스별 **owned 테이블 명시**. 외부 접근은 API로만 |-|
| 테이블 명명 | `{uid}_{suffix}` 동적 생성 (회원당 ~9개) | 정규화 공통 테이블 + `(user_id, date)` 복합 인덱스 | 제안하는 방식이, 각 데이터 종류 마다 사용자 table을 merge하여 데이터 종류 별 table을 만드는 것을 제안하는건가?|
| 서비스 간 계약 | 암묵적 DB 스키마 (테이블명·컬럼명·단위) | 명시적 API 계약 (예: `/users/{uid}/features?window=7`) + Pydantic 응답 스키마 | 암묵적 DB 스키마 라는게, 하드코딩 되어서 접근하는 상태를 뜻하는건가? |
| 진행 상태 보관 | Streamlit `session_state` (브라우저) | 서버 측 `ingestion_runs`, `model_runs` 테이블 |-|
| 호출 간 흐름 추적 | 호출 사이에 ID 단절 (data_service의 `/fetch` 응답에 ID 없음) | `feature_snapshot_id` → `prediction_run_id` → `recommendation_run_id` cascade | feature_snapshot_id가 무슨 테이블인가? feature_snapshot이 무엇인가?  |
| 결과 조회 | Streamlit이 `predictions` 테이블을 `psycopg2`로 직접 SELECT (`streamlit_fitbit.py:182-186`) | Streamlit이 `/predictions/{run_id}` API 호출, DB는 절대 직접 접근 안 함 |-|

##### 표 답변 — 사용자 피드백 응답

###### Q. "테이블 명명" — 각 데이터 종류마다 사용자 table을 merge해 데이터 종류별 table을 만드는 것을 제안하는 건가?

네, 정확합니다. 현재는 회원 200명이면 `sleep_summary`만 해도 200개(`23RK3S_sleep_summary`, `U001_sleep_summary` …)가 생깁니다. To-Be에서는 **데이터 종류당 단 1개의 공통 테이블**에 모든 회원의 행을 `user_id` 컬럼으로 구분해 적재합니다.

```sql
-- As-Is: 회원 200명 × 데이터 종류 8개 = 약 1,600개 테이블
CREATE TABLE "23RK3S_sleep_summary" (date DATE, efficiency FLOAT, ...);
CREATE TABLE "U001_sleep_summary"   (date DATE, efficiency FLOAT, ...);
...

-- To-Be: 데이터 종류당 1개, 총 8개 테이블
CREATE TABLE fitbit_sleep_summary (
  user_id   TEXT NOT NULL,
  date      DATE NOT NULL,
  efficiency FLOAT,
  stage_deep INT, stage_light INT, stage_rem INT, stage_wake INT,
  ...,
  PRIMARY KEY (user_id, date)
);
CREATE INDEX ON fitbit_sleep_summary (user_id, date DESC);
```

이 한 줄짜리 변경으로 얻는 것:

- 인덱스/제약조건/파티셔닝/백업 정책을 *한 번 정의하면 모든 회원에 일관 적용*. 회원이 늘어도 운영 도구 부담 일정.
- 다중 회원 분석 SQL이 자연스러움: `SELECT AVG(efficiency) FROM fitbit_sleep_summary WHERE date >= '2026-04-01' GROUP BY user_id`.
- 회원 삭제는 `DELETE FROM fitbit_sleep_summary WHERE user_id = ?` 한 줄(§9.9의 PIPA 대응이 자동 해결).
- 회원이 늘어도 `pg_class` 카탈로그가 부풀지 않음.

대용량 시계열(예: `fitbit_activity_minute`)은 **PostgreSQL 13의 declarative partitioning**을 쓰면 `(user_id)` 또는 `(date)` 단위로 파티션을 자동 분할해 조회 성능과 보존 정책을 모두 단순화할 수 있습니다.

###### Q. "서비스 간 계약" — "암묵적 DB 스키마"라는 게 하드코딩되어 접근하는 상태를 뜻하는 건가?

네, 두 가지 의미가 결합된 표현입니다.

1. **코드 차원의 하드코딩** — `ai_service/sleep_coach_full_kr_v6.py:135-141`이 `read_daily_db("sleep_summary", ...)` 처럼 테이블 suffix와 컬럼명을 *Python 문자열 리터럴*로 알고 있습니다. 어떤 컴파일러/타입 체커도 검증해주지 않습니다. `data_service`가 컬럼명을 바꿔도 *런타임 첫 호출까지 모릅니다*.

2. **조직 차원의 비공식 약속** — "data_service가 만드는 테이블은 이 이름·이 단위·이 컬럼이다"라는 합의가 **PR 리뷰·구두 합의·README 메모**로만 존재하고, *기계가 강제하는 계약*은 없습니다. 새 팀원이 모르고 컬럼을 바꿔도 막을 장치가 없습니다.

To-Be의 "명시적 API 계약"은 이 둘을 모두 *코드와 도구로 강제*하는 상태입니다.

```python
# data_service: Pydantic 응답 모델로 계약을 코드화
class FeatureRow(BaseModel):
    user_id: str
    date:    date
    efficiency: float = Field(ge=0, le=100, description="0~100 scale")
    steps:   int   = Field(ge=0)
    ...

@app.get("/users/{uid}/features", response_model=list[FeatureRow])
def get_features(uid: str, window: int = 7): ...
```

```python
# ai_service: 같은 Pydantic 모델을 import해서 사용
from data_service.contracts import FeatureRow
features: list[FeatureRow] = httpx.get(...).json()  # 타입 보장
```

이렇게 하면:
- `efficiency`의 단위(`[0,1]` vs `[0,100]`)가 `Field(ge=0, le=100)`으로 명문화됨.
- `data_service`팀이 단위를 바꾸면 *Pydantic 검증에서 실패*하거나 *공유 contracts 패키지 PR이 필요*해 ai_service팀 리뷰 없이 머지 불가.
- OpenAPI(Swagger) 스펙이 자동 생성되어 다른 서비스/외부 클라이언트가 같은 계약을 사용 가능.
- `schemathesis` 같은 도구로 *계약 위반 자동 테스트* 가능.

조직 규모가 작다면 처음에는 *공통 `contracts/` 디렉터리 + Pydantic*만으로 충분합니다. 더 커지면 Protocol Buffers / gRPC / OpenAPI codegen을 도입.

###### Q. "feature_snapshot_id"가 무슨 테이블인가? feature_snapshot이 무엇인가?

**feature snapshot**은 "특정 시점에 특정 회원에 대해 모델 추론 입력으로 사용한 feature 행 집합"의 *불변 식별자*입니다. 사진을 찍듯 "그 순간 ai_service가 본 데이터의 모습"을 고정시켜 기록합니다.

테이블 정의:

```sql
CREATE TABLE feature_snapshots (
  snapshot_id        UUID PRIMARY KEY,
  ingestion_run_id   UUID REFERENCES ingestion_runs(run_id),
  user_id            TEXT NOT NULL,
  window_start       DATE NOT NULL,    -- 어떤 날짜부터의 데이터를 봤는가
  window_end         DATE NOT NULL,    -- 어디까지 봤는가
  row_count          INT  NOT NULL,    -- 그 윈도우에 행이 몇 개였나
  feature_hash       CHAR(16),         -- 행 내용 해시 (재현성·중복 검증용)
  created_at         TIMESTAMPTZ DEFAULT NOW()
);
```

**왜 필요한가** — 디버깅·재현·실험 비교의 토대.

- 같은 회원에게 *오늘 오전 9시*와 *오늘 오후 3시*에 추론을 두 번 돌리면, 사이에 새 Fitbit 데이터가 들어와 입력 features가 달라집니다. 결과 메시지가 다른 이유를 추적할 단서가 *어느 데이터로 추론했는지* 외에는 없습니다.
- "지난주 코칭 메시지가 이번 주와 다른데, 모델이 바뀌어서인가, 데이터가 바뀌어서인가, 프롬프트가 바뀌어서인가?"를 분리하려면 (모델 버전, 프롬프트 해시, **feature snapshot id**, LLM 파라미터)가 모두 `predictions` 행에 외래키로 붙어야 합니다.
- 한 회원의 *같은 입력으로* 여러 번 호출하면 멱등하게 처리(§9.6) — `feature_hash` 일치 시 기존 결과 반환.

**구현 방법** (가벼운 버전):

```text
1. data_service /fetch
   - PostgreSQL의 fitbit_daily_features에 새 행 적재
   - feature_snapshots에 (snapshot_id, user_id, window_start, window_end, row_count) INSERT
   - 응답: { ingestion_run_id, feature_snapshot_id }

2. ai_service /predict
   - 요청에 feature_snapshot_id 포함
   - feature_snapshots에서 (user_id, window_start, window_end)을 읽고
   - fitbit_daily_features에서 그 윈도우의 행만 조회 → CatBoost 학습/추론
   - predictions(uid, run_id, feature_snapshot_id, message, ...) INSERT
```

가장 단순한 형태는 위처럼 **윈도우 메타정보만 저장**해 같은 fitbit_daily_features를 다시 조회하는 방식입니다. 더 강한 재현성을 원하면 `feature_snapshot_rows(snapshot_id, user_id, date, ...)` 같은 *물리적 archive 테이블*에 행 자체를 복사해 두지만, 저장 비용이 두 배가 됩니다. 데모/면접용으로는 메타정보만으로 충분합니다.

이렇게 하면 `predictions.feature_snapshot_id`만 보고 "이 코칭 메시지는 2026-04-23부터 2026-04-30까지의 데이터 188행으로부터 나왔다"라고 한 줄로 답할 수 있습니다.

##### To-Be 서비스별 데이터 소유권·계약

```text
data_service
  owns: fitbit_raw, fitbit_daily_features, ingestion_runs
  exposes: /fetch, /ingestion-runs/{run_id}, /users/{uid}/features?window=7

feedback_api
  owns: sleep_feedback
  exposes: /feedback, /users/{uid}/feedback?from=&to=

ai_service
  owns: predictions, token_usage, model_runs
  consumes: data_service /users/{uid}/features  +  feedback_api /users/{uid}/feedback
  exposes: /predict, /predictions/{run_id}

group_service
  owns: preferred_slots, group_sessions, match_history
  consumes: ai_service /predictions/{run_id} (recommended_slot 추출)
  exposes: /recommendations/{uid}
```

##### As-Is에서 To-Be로 가는 최소 변경 경로

물리적 DB 분리는 운영 자원이 큽니다. 같은 PostgreSQL을 유지하면서 **논리적 소유권**만 강화하는 단계적 경로:

1. **읽기 경계 도입** (코드 ~50줄): `ai_service`가 `{uid}_sleep_summary` 테이블을 직접 읽지 않고, `data_service`의 `/users/{uid}/features` HTTP API를 호출. 첫 단계로는 같은 SQL을 호출하지만 *호출 위치가 data_service 안*으로 옮겨짐.
2. **표준 feature 테이블 도입** (코드 ~100줄, 마이그레이션 1회): `fitbit_daily_features(user_id, date, ...)`를 추가하고 `data_service`만 write. 기존 `{uid}_*` 테이블은 *legacy*로 한동안 공존.
3. **Streamlit의 직접 SELECT 제거** (코드 ~20줄): `streamlit_fitbit.py`의 `pd.read_sql("SELECT message FROM predictions ...")`를 `requests.get(f"{AI_URL}/predictions/{run_id}")`로 교체.
4. **`{uid}_*` 테이블 단계적 폐기**: 신규 회원부터 표준 테이블 사용, 기존 회원은 백필 후 삭제.

이 4단계는 각각 *독립적으로 PR 단위로 머지 가능*하므로, 운영 중인 시스템이라도 점진 전환이 가능합니다.

#### 보완 구조가 작동하는 방식

보완 구조에서는 Streamlit이 "어떤 버튼 다음에 어떤 버튼을 눌러야 하는지"만 제어하고, 실제 처리 상태와 데이터 연결은 백엔드의 `run_id`와 표준 API 계약으로 관리합니다. 핵심 변화는 세 가지입니다.

1. **동적 테이블명 대신 표준 데이터 계약 사용**

   `data_service`는 `{uid}_{suffix}` 테이블을 여러 개 만드는 대신, 원천 데이터와 일 단위 feature를 공통 테이블에 저장합니다.

   > **사용자 질문 답변** — "daily features 각각 따로가 아니라 feature도 통합한 table을 만들자는 건가요?"
   >
   > **두 단계의 통합을 함께 제안**합니다.
   >
   > **1단계 — 데이터 종류별 통합** (§9.1 표 답변 Q1과 동일): 각 데이터 종류(`sleep_summary`, `activity_sum` …)마다 회원당 한 테이블이 아닌, **데이터 종류당 1개의 공통 테이블 + `user_id` 컬럼**.
   >
   > **2단계 — 일별 feature 가로 통합 (지금 질문)**: `sleep_summary`, `activity_sum`, `resting_hr`, `azm` 등 *여러 일별 테이블*을 **하나의 `fitbit_daily_features` 테이블**에 (user_id, date) PRIMARY KEY로 wide-format으로 묶습니다.
   >
   > ```sql
   > -- 1단계만 (종류별 분리 유지)            -- 2단계까지 (가로 통합)
   > fitbit_sleep_summary(uid,date,...)        fitbit_daily_features(
   > fitbit_activity_sum(uid,date,...)            user_id, date,
   > fitbit_resting_hr(uid,date,...)              -- sleep
   > fitbit_azm(uid,date,...)                     efficiency, stage_deep, stage_light, ...,
   >                                              -- activity
   >                                              steps, distance, calories,
   >                                              -- vital
   >                                              resting_hr, azm_total, azm_fatburn, azm_cardio,
   >                                              -- HRV
   >                                              hrv_rmssd, hrv_hf, hrv_lf,
   >                                              PRIMARY KEY (user_id, date))
   > ```
   >
   > **2단계까지 가는 게 좋은 이유**:
   > - `ai_service`가 4번의 JOIN 대신 **단일 SELECT**로 모든 features를 가져옴 → CatBoost 입력 준비 코드가 한 줄.
   > - `(user_id, date)` 인덱스 *하나*로 모든 일별 feature 조회가 빨라짐.
   > - `feature_snapshot`이 가리키는 단위가 **명확한 행 집합**(`fitbit_daily_features`의 특정 날짜 범위) — §9.1 표 답변 Q3에서 다룬 재현성과 직결.
   >
   > **다만 분 단위(minute-level) 데이터는 wide-format 부적합**:
   > - `activity_1min`, `heart_rate_1min`, `hrv` 같은 1분 단위는 카디널리티가 *전혀 다름*(하루 1,440행). daily_features와 같은 PK로 묶으면 행이 폭발.
   > - 분 단위는 별도 long-format 테이블로 유지하고, `data_service`가 ingest 시점에 *집계*해서 daily_features의 `hrv_rmssd_mean` 같은 컬럼으로 흘려보냄.
   >
   > **권장 dataflow**:
   > ```text
   > Fitbit raw (1분 단위) → fitbit_minute_metrics (long-format)
   >                              ↓ 일별 집계 (data_service 책임)
   >                       fitbit_daily_features (wide-format, ai_service 입력)
   > ```
   >
   > **트레이드오프 — 한 wide table의 단점**:
   > - 컬럼 추가/타입 변경 빈도가 높으면 schema migration 비용이 누적됨 (§9.7의 Alembic 도입과 묶이는 이유).
   > - sparse한 컬럼이 많으면(예: 일부 회원만 측정한 `glucose`) NULL 비율이 커짐. 이 경우 `fitbit_optional_metrics(user_id, date, metric_name, value)` long-format 보조 테이블을 별도로 두는 게 깔끔.

   ```text
   fitbit_raw_events(user_id, source, event_time, payload)
   fitbit_daily_features(user_id, date, steps, calories, resting_hr, efficiency, ...)
   ingestion_runs(run_id, user_id, date_start, date_end, status, row_count)
   ```

   그러면 `ai_service`는 `{uid}_activity_1min` 같은 테이블명을 추측하지 않고, `feature_snapshot_id` 또는 `user_id/date range`로 표준 feature를 조회합니다.

2. **서비스 간 흐름을 run_id로 연결**

   각 단계는 이전 단계의 결과 ID를 입력으로 받습니다.

   ```text
   Streamlit → data_service /fetch
     request:  { uid, start_date, end_date, token }
     response: { ingestion_run_id, feature_snapshot_id, status }

   Streamlit → ai_service /predict
     request:  { uid, feature_snapshot_id }
     response: { prediction_run_id, recommended_slot, status }

   Streamlit → group_service /recommendations
     request:  { uid, prediction_run_id, recommended_slot }
     response: { recommendation_run_id, partners, groups, status }
   ```

   이 구조에서는 "어떤 데이터 수집 결과가 어떤 AI 예측과 어떤 그룹 추천으로 이어졌는가"를 DB에서 역추적할 수 있습니다. 실패가 발생해도 `ingestion_run_id` 또는 `prediction_run_id` 기준으로 재시도할 수 있습니다.

3. **서비스 소유권을 명확히 분리**

   현재는 모든 서비스가 같은 DB를 자유롭게 읽고 쓰는 형태에 가깝습니다. 보완 구조에서는 같은 PostgreSQL을 계속 쓰더라도 논리적 소유권을 나눕니다.

   ```text
   data_service
     - Fitbit token 처리, raw data 적재, feature snapshot 생성 책임
     - 다른 서비스는 data_service 소유 테이블에 직접 write하지 않음

   feedback_api
     - sleep_feedback 저장 책임
     - ai_service에는 user_id/date 기준 피드백 조회 계약만 제공

   ai_service
     - feature snapshot + feedback snapshot을 입력으로 prediction 생성
     - predictions/model_runs/token_usage 소유
     - recommended_slot을 structured field로 저장

   group_service
     - preferred_slots, group_sessions, match_history 소유
     - ai_service의 recommended_slot을 받아 실제 가능한 파트너/그룹으로 변환

   streamlit
     - 상태 저장소가 아니라 사용자 조작과 결과 표시 계층
     - 최신 message를 DB에서 직접 SELECT하지 않고 /predictions/{run_id} API로 조회
   ```

이 보완안의 요지는 "컨테이너를 여러 개로 나눴다"가 아니라, **각 서비스가 소유하는 데이터와 외부에 제공하는 계약을 분리한다**는 것입니다. 이렇게 설명하면 현재 구현은 빠른 프로토타입, 보완 구조는 운영형 MSA로 자연스럽게 구분됩니다.

최소 수정 버전으로는 DB를 물리적으로 나누지 않더라도, **테이블 소유권 문서화 + read/write 경계 분리**만 해도 MSA 설계 논리가 강화됩니다. 예를 들어 `ai_service`는 원천 테이블을 직접 추측해 읽는 대신 `data_service`의 feature snapshot API를 호출하거나, 최소한 `fitbit_daily_features(user_id, date, ...)` 같은 표준 feature 테이블만 읽도록 제한합니다.

---

### 9.2 동적 per-user 테이블은 데이터 흐름 설명을 약하게 만듦

#### 약점

현재 원천 데이터와 피드백은 `{uid}_{suffix}` 또는 `{uid}_feedback` 형태로 저장됩니다. 이는 데모에서는 직관적이지만, 데이터 흐름 설계 관점에서는 다음 질문에 취약합니다.

- 신규 회원이 생길 때 테이블 DDL은 누가 책임지는가? (DDL이 무엇인가요?)
- 여러 회원을 한 번에 학습하거나 비교할 때 모든 테이블을 어떻게 discover하는가?
- 인덱스, 제약조건, 마이그레이션, 백업 정책을 테이블마다 어떻게 일관되게 적용하는가?
- 회원 삭제 요청이 들어오면 어떤 테이블을 찾아 지워야 하는가? 

#### 보완 방법

운영형 설계에서는 사용자별 테이블 대신 **정규화된 공통 테이블 + `user_id` 컬럼 + 인덱스**로 전환하는 것이 논리적으로 강합니다.

```sql
fitbit_sleep_summary(user_id, date, efficiency, stage_deep, stage_light, stage_rem, stage_wake, ...)
fitbit_activity_minute(user_id, ts, steps, distance, calories, ...)
sleep_feedback(user_id, date, sleep_score, created_at)
predictions(user_id, run_id, feature_snapshot_id, message, created_at)
```

이 구조의 장점:

- `ai_service`가 "어떤 테이블을 읽어야 하는지"를 uid 문자열 조합에 의존하지 않음.
- `user_id, date` 복합 인덱스로 조회 성능을 관리할 수 있음.
- 개인정보 삭제/보존 기간 정책을 `WHERE user_id = ?` 단위로 집행 가능.
- 여러 회원 기반 global model, cohort baseline, 파트너 매칭 분석으로 확장 가능.

---

### 9.3 데이터 수집·AI 추론·추천 사이의 run_id가 끊겨 있음

#### 약점

`ai_service`는 `/predict` 호출마다 `run_id`를 만들지만, `data_service /fetch` 결과와 연결된 ingestion run id가 없습니다. 따라서 `predictions.run_id`가 "어떤 기간의 어떤 원천 데이터로 만든 결과인지"를 설명하지 못합니다. `group_service`도 최신 AI 추천 시간대를 입력으로 받지 않고, 현재는 고정 `CURRENT_USER_SLOTS` 기준으로 추천합니다.

#### 왜 문제인가

- 같은 회원을 같은 날 여러 번 호출하면, 어떤 데이터 수집 결과가 어떤 AI 메시지로 이어졌는지 추적이 어렵습니다.
- 추천 결과가 AI 코칭의 "권장 운동 시간대"와 연결되지 않아, `AI 코칭 → 파트너/그룹 추천`이라는 제품 서사가 데이터상으로 닫히지 않습니다.
- 실패 복구가 어렵습니다. 예를 들어 data는 성공했지만 AI가 실패한 경우 재시도 기준이 없습니다.

#### 보완 방법

서비스 간 흐름에 `run_id` 또는 `correlation_id`를 전파합니다.

```text
1. Streamlit → data_service /fetch
   response: { ingestion_run_id, uid, date_start, date_end, feature_snapshot_id }

2. Streamlit → ai_service /predict
   request: { uid, feature_snapshot_id }
   response: { prediction_run_id, recommended_slot, confidence, message_status }

3. Streamlit → group_service /recommend
   request: { uid, prediction_run_id, recommended_slot }
   response: { recommendation_run_id, partners, groups }
```

PostgreSQL에는 다음 추적 테이블을 둡니다.

```sql
ingestion_runs(run_id, user_id, started_at, finished_at, status, source, date_start, date_end)
feature_snapshots(snapshot_id, ingestion_run_id, user_id, window_start, window_end, row_count)
model_runs(run_id, snapshot_id, model_version, prompt_hash, status, error_message)
recommendation_runs(run_id, prediction_run_id, user_id, status)
```

이렇게 하면 포트폴리오에서 **관측 가능하고 재현 가능한 서비스 데이터 흐름**을 제시할 수 있습니다.

---

### 9.4 vLLM이 Compose 내부 서비스가 아니라 외부 IP 의존으로 남아 있음

#### 약점

`ai_service`는 `OPENAI_BASE=http://172.28.8.101:8282/v1`로 vLLM OpenAI-compatible endpoint를 호출합니다. Docker Compose 안에는 vLLM 서비스가 정의되어 있지 않고, `MODEL_PATH`는 GGUF 경로이지만 실제 호출 코드는 OpenAI 클라이언트로 외부 vLLM을 사용합니다.

#### 왜 문제인가

- `docker compose up`만으로 전체 시스템이 재현된다는 설명이 약해집니다.
- 외부 vLLM 서버의 모델명(`./llama3`), API key, 네트워크 접근성, health 상태가 compose 파일의 의존성 그래프에 들어오지 않습니다.
- `llama_cpp`/GGUF 기반 설명과 vLLM 기반 설명이 섞여 있어 면접관이 "실제로 어떤 추론 서버를 썼나요?"라고 물을 수 있습니다.

#### 보완 방법

둘 중 하나로 명확히 정리해야 합니다.

1. **외부 vLLM 의존형**: `ai_service`는 OpenAI-compatible client이고, vLLM은 외부 GPU 서버라고 명시. `.env.example`에 `OPENAI_BASE`, `OPENAI_KEY`, `LLM_MODEL_NAME`을 분리하고 `/health` 점검과 timeout fallback을 둠.
2. **Compose 내장형**: GPU 서버 환경이 준비되어 있다면 `vllm` 서비스를 compose에 추가하고 `ai_service.depends_on: vllm` + 내부 DNS `http://vllm:8000/v1`로 연결.

데모/면접용으로는 1번이 현실적입니다. 다만 README와 문서에는 "Docker Compose는 앱/DB 계층을 재현하고, vLLM은 외부 GPU 추론 계층으로 분리했다"는 아키텍처 결정을 명시해야 합니다.

---

### 9.5 동기 API 체인은 데모에는 단순하지만 운영 부하 논리가 약함

#### 약점

Streamlit이 `data_service`를 최대 120초, `ai_service`를 최대 300초 동기 호출합니다. CatBoost 학습, SHAP 계산, vLLM 호출이 모두 `/predict` 요청 안에서 일어나므로 트레이너 UI가 긴 시간 블로킹됩니다.

> **사용자 질문 답변** — "블로킹 됐을 때 단점이 뭐가 있나요?"
>
> 단순히 "오래 기다린다" 이상의 운영상 문제가 8가지 누적됩니다.
>
> 1. **트레이너 UI가 5분 멈춤 = 사실상 서비스 실패**: 회원과 마주 앉은 상담실에서 5분 응답 없음 화면은 *데모 가능*이지 *서비스 가능*이 아님. 트레이너가 다른 회원 데이터를 볼 수도, 같은 회원의 다른 페이지로 이동할 수도 없음.
> 2. **HTTP worker 점유로 동시 사용자 수 제한**: FastAPI uvicorn worker가 N개라면, 5분 호출 N개가 동시에 들어오면 *N+1번째는 큐잉도 안 되고 503 거부*. 트레이너 5명이 동시에 추론을 누르면 일부 즉시 실패.
> 3. **타임아웃 다층 누적이 디버깅 곤란**: streamlit 300s ⊃ ai_service uvicorn 30s default ⊃ vLLM 호출 timeout — 어느 단계에서 끊겼는지 단서 없음. 보통 *가장 짧은 timeout*에서 잘려 사용자에겐 "원인 불명"으로 보임.
> 4. **중간 reverse proxy가 끊음**: Nginx/AWS ALB의 default idle timeout은 60s/120s. 5분 호출은 *프록시 설정도 따로 늘려야* 동작 — 운영 환경 이전 시 "왜 데모는 됐는데 운영은 502?" 함정.
> 5. **부분 실패 시 토큰 누수**: vLLM이 응답을 시작해 *토큰을 이미 소비*했는데 streamlit이 timeout으로 close → ai_service의 `predictions` INSERT는 일어나지만 트레이너는 결과를 못 받음. 비용은 발생, 가치는 0. (§9.6의 정합성 문제와 직결)
> 6. **재시도 시 멱등성 없으면 비용·결과 중복**: 네트워크 끊김 한 번에 streamlit이 재시도하면 ai_service는 *이미 LLM을 호출 중인 채로* 또 호출 → 토큰·DB row 중복(§9.6).
> 7. **모바일·불안정 네트워크에서 일관성 0**: Wi-Fi 끊김 1번 = 5분 작업 처음부터. 트레이너가 헬스장 라커룸에서 태블릿으로 쓰면 매 호출이 도박.
> 8. **운영 모니터링이 어려움**: 정상 호출과 *그냥 LLM이 느린 호출*을 구분할 수 없음 — 둘 다 "long-running request"로 보임. 이상 탐지·SLO 모니터링이 본질적으로 불가능.
>
> 핵심: 블로킹은 *데모 한 사람*에게는 "느리다" 정도지만, *운영*에서는 동시성·정합성·관찰가능성이 동시에 깨지는 시작점입니다.

#### 보완 논리

운영형 구조에서는 다음처럼 **짧은 요청/긴 작업 분리**를 제안하는 것이 좋습니다.

```text
POST /predict-jobs { uid, feature_snapshot_id }
  → 즉시 202 Accepted { job_id }

GET /predict-jobs/{job_id}
  → queued/running/succeeded/failed + progress

GET /predictions/{prediction_run_id}
  → 최종 카드 데이터
```

기술 선택지는 Celery/RQ/Redis가 일반적이지만, 새 의존성을 늘리지 않는 과제형 보강이라면 FastAPI `BackgroundTasks` + `prediction_jobs` 테이블만으로도 충분히 설계를 설명할 수 있습니다. 핵심은 **Streamlit이 장시간 계산을 직접 기다리는 구조에서, 상태 조회 기반 구조로 전환한다**는 점입니다.

> **사용자 질문 답변** — "어떤 과정으로 블로킹 문제를 해결하는지 좀 더 설명이 필요합니다."
>
> 한 줄 요약: **5분짜리 HTTP 요청 한 번**을 → **즉시 끝나는 짧은 요청 + 폴링 기반 상태 조회**로 분해합니다. 호출 1번이 5분이 아니라 *수십 개의 1초짜리* 호출로 바뀝니다.
>
> ##### As-Is (블로킹)
>
> ```text
> Streamlit ───────────────────────── 5분 대기 ─────────────────────────► ai_service
>          [│ 화면 응답 없음 │ worker 점유 │ proxy timeout 위험 │]
>          ◄────────────────────────── 응답 ───────────────────────────
> ```
>
> 모든 시간 동안 streamlit은 응답을 기다리고, ai_service worker도 점유, 둘 사이의 모든 네트워크 장비는 연결을 *5분간* 유지해야 함.
>
> ##### To-Be (비동기 job 모델) — 4단계
>
> ###### 1단계 — 작업 시작 (요청은 100ms로 끝남)
> ```text
> Streamlit ──── POST /predict-jobs { uid } ────► ai_service
>          ◄─── 202 Accepted { job_id: "abc-123" } (즉시) ────
>          화면: "처리 중... ⏳"
> ```
>
> ai_service는 요청을 받자마자 `prediction_jobs` 테이블에 `(job_id, status='queued')`로 INSERT하고, 백그라운드 작업을 큐에 넣은 뒤 *즉시 200ms 안에* 응답.
>
> ###### 2단계 — 백그라운드 작업이 *별도로* 진행
>
> ai_service의 별도 thread/worker(`BackgroundTasks` 또는 Celery worker)가:
> ```text
>   prediction_jobs 행: status='queued' → 'running' (started_at 기록)
>   CatBoost 학습 (10초)
>   SHAP top-k 계산 (1초)
>   vLLM 호출 (5분)
>   predictions 테이블 INSERT
>   prediction_jobs 행: status='succeeded' (finished_at, prediction_run_id 기록)
> ```
>
> 이 5분 동안 **HTTP 연결은 이미 닫혔음**. streamlit도, ai_service의 HTTP worker도, 네트워크 장비도 다른 일을 자유롭게 할 수 있음.
>
> ###### 3단계 — Streamlit이 짧은 요청으로 상태 폴링
> ```text
> 매 2~3초마다:
>   Streamlit ──── GET /predict-jobs/abc-123 ────► ai_service
>            ◄─── { status: "running", progress: 0.4 } ────
>            화면: 진행 표시줄 갱신
> ```
>
> 한 번의 폴링은 단순 SELECT 한 줄(50ms 미만). 100명이 동시에 폴링해도 부담 없음.
>
> ###### 4단계 — 완료되면 결과 조회
> ```text
> Streamlit이 status='succeeded'를 받으면:
>   GET /predictions/{prediction_run_id} ────► ai_service
>   ◄── 카드 데이터 (즉시)
>   화면 갱신
> ```
>
> ##### `prediction_jobs` 테이블 정의
>
> ```sql
> CREATE TABLE prediction_jobs (
>   job_id            UUID PRIMARY KEY,
>   user_id           TEXT NOT NULL,
>   status            TEXT NOT NULL,    -- queued | running | succeeded | failed | canceled
>   progress          FLOAT DEFAULT 0,  -- 0.0~1.0 (선택)
>   started_at        TIMESTAMPTZ,
>   finished_at       TIMESTAMPTZ,
>   prediction_run_id UUID,             -- 성공 시 결과를 가리킴
>   error_message     TEXT
> );
> ```
>
> ##### 가벼운 구현 — FastAPI `BackgroundTasks` (외부 의존성 0개)
>
> ```python
> # ai_service
> from fastapi import BackgroundTasks
>
> @app.post("/predict-jobs", status_code=202)
> def start_predict(req: Req, bg: BackgroundTasks):
>     job_id = uuid.uuid4()
>     db_insert("INSERT INTO prediction_jobs (job_id, user_id, status) VALUES (%s, %s, 'queued')",
>               (job_id, req.uid))
>     bg.add_task(run_prediction, job_id, req.uid)
>     return {"job_id": str(job_id)}
>
> def run_prediction(job_id, uid):
>     try:
>         db_update("UPDATE prediction_jobs SET status='running', started_at=NOW() WHERE job_id=%s", (job_id,))
>         run_id = coach_main(uid)   # 5분 작업
>         db_update("UPDATE prediction_jobs SET status='succeeded', finished_at=NOW(), prediction_run_id=%s WHERE job_id=%s",
>                   (run_id, job_id))
>     except Exception as e:
>         db_update("UPDATE prediction_jobs SET status='failed', finished_at=NOW(), error_message=%s WHERE job_id=%s",
>                   (str(e), job_id))
>
> @app.get("/predict-jobs/{job_id}")
> def get_job(job_id: str):
>     return db_fetchone("SELECT job_id, status, progress, prediction_run_id, error_message FROM prediction_jobs WHERE job_id=%s", (job_id,))
> ```
>
> ##### Streamlit 측 — polling 패턴
>
> ```python
> import time
>
> if "job_id" not in st.session_state:
>     if st.button("AI 추론 실행"):
>         r = requests.post(f"{AI_URL}/predict-jobs", json={"uid": uid})
>         st.session_state.job_id = r.json()["job_id"]
>         st.rerun()
> else:
>     job = requests.get(f"{AI_URL}/predict-jobs/{st.session_state.job_id}").json()
>     if job["status"] == "succeeded":
>         pred = requests.get(f"{AI_URL}/predictions/{job['prediction_run_id']}").json()
>         render_card(pred["message"])
>         del st.session_state.job_id
>     elif job["status"] == "failed":
>         st.error(f"실패: {job['error_message']}")
>         del st.session_state.job_id
>     else:  # queued | running
>         st.info(f"처리 중... {int(job.get('progress', 0)*100)}%")
>         time.sleep(2); st.rerun()
> ```
>
> ##### 8가지 단점이 어떻게 해결되는가
>
> | As-Is 단점 | To-Be 해결 |
> |----|----|
> | UI 5분 멈춤 | 화면이 즉시 "처리 중"으로 응답, 트레이너는 다른 회원 화면 자유롭게 이동 가능 |
> | HTTP worker 점유 | worker는 100ms 후 즉시 free. 동시 트레이너 N명도 *N개 worker*만 잠깐 점유 |
> | 타임아웃 다층 누적 | 모든 HTTP 호출이 1초 이내 — proxy/uvicorn timeout 모두 default로 충분 |
> | reverse proxy 끊김 | Nginx default 60s에 한참 못 미치므로 운영 환경 이전 무리 없음 |
> | 토큰 누수 | 응답이 끊겨도 백그라운드 작업은 계속 진행되어 결과를 *DB에 적재*. 트레이너는 새로고침 후 polling 재개로 결과 회수 가능 |
> | 재시도 중복 | 멱등성 키(§9.6)와 결합 시, 같은 job 요청은 같은 job_id로 회귀 |
> | 모바일 끊김 일관성 | 폴링 클라이언트가 *작업 자체*를 끊지 않음. job_id만 알면 어디서든 상태 회수 |
> | 모니터링 곤란 | `prediction_jobs.status` 분포로 큐 길이·처리 시간·실패율을 SQL 한 줄로 추적 가능 |
>
> ##### 진화 경로 (선택)
>
> - **`BackgroundTasks`** (지금 권장): 외부 의존성 0, ai_service 프로세스 안에서 1~2개 동시 작업 OK. *프로토타입 단계 적합*.
> - **`Celery + Redis`**: worker pool 분리, 작업 우선순위, retry 자동, 분산 처리. *동시 5명 이상부터 권장*.
> - **`SSE` 또는 `WebSocket`**: streamlit이 폴링 대신 push로 상태 수신. 폴링 부담이 클 때.
> - **rate limit + circuit breaker**: §9.6과 결합해 vLLM 보호.

---

### 9.6 분산 트랜잭션·멱등성·재시도 부재 🟡

#### 약점

여러 단계가 한 요청 안에서 순차 실행되지만, 각 단계 사이의 **부분 실패** 복구 논리가 없습니다.

- `data_service/app.py:67-90` — `csv_to_db.py`가 PostgreSQL에 적재 후, raw CSV를 호스트 파일시스템에서 삭제. 적재 성공 + 파일 삭제 실패 / 적재 실패 + 파일 잔존 같은 부분 상태가 정의되지 않음.
- `ai_service/app_ai.py:42-56` — `coach_main()` 안에서 (1) DB 조회 → (2) CatBoost 학습 → (3) SHAP → (4) vLLM 호출 → (5) `predictions` INSERT가 직렬로 실행. (4)가 timeout이면 vLLM 토큰은 이미 소비됐는데 (5)는 일어나지 않아 `token_usage`와 `predictions`이 어긋남.
- 같은 `(uid, feature_snapshot_id)` 쌍으로 `/predict`를 두 번 호출하면, 두 번 학습 + 두 번 vLLM 호출 + 두 번 INSERT가 일어나 비용·DB row가 중복됩니다 (멱등성 없음).

#### 왜 문제인가

- 면접에서 분산 시스템·MSA 설계를 말할 때 *멱등성·재시도·실패 복구*는 단골 주제. 현재 코드엔 이 어휘가 등장하지 않음.
- 운영 단계에서 LLM은 가장 흔한 timeout 원천이라, 부분 실패 처리 부재는 데이터 정합성 문제로 자주 표면화됨.

#### 보완 방법

1. **멱등성 키**: `/predict` 요청에 `idempotency_key`(예: `sha256(uid + feature_snapshot_id)`)를 받고, `predictions` 테이블에 unique 제약. 같은 키로 재호출되면 기존 결과를 그대로 반환.
2. **상태 머신**: `model_runs(run_id, status, started_at, finished_at, error)`를 두고 `queued → running → llm_called → succeeded/failed`로 전이. 실패 시 *어느 단계까지 진행됐는지*가 남아 retry 가능.
3. **transactional outbox 패턴**: vLLM 호출 결과와 token_usage·predictions INSERT를 같은 트랜잭션 또는 outbox 테이블로 묶어, "토큰은 차감됐는데 결과는 안 남음" 상태를 차단.
4. **재시도 정책**: vLLM 호출은 exponential backoff + circuit breaker. CatBoost 학습은 멱등이지만 비싸므로 *직전 학습 결과*가 캐시되어 있으면 재사용.

---

### 9.7 스키마 진화·마이그레이션 도구 부재 🟡

#### 약점

`db/init/*.sql`은 PostgreSQL 컨테이너의 `pgdata` 볼륨이 비어 있을 때만 실행됩니다(`/docker-entrypoint-initdb.d` 동작). 즉:

- 일단 한 번 운영에 들어간 DB는 `*.sql`을 추가하거나 수정해도 자동 적용되지 않음.
- 스키마 변경을 반영하려면 `docker compose down -v`로 볼륨을 삭제 → **모든 회원 데이터 손실**.
- Alembic·Flyway 같은 마이그레이션 도구가 없어, "회원 N명이 누적된 운영 DB에 컬럼 하나를 어떻게 추가하나요?"에 답이 없음.

#### 왜 문제인가

- 면접 단골: "DB 스키마를 바꿀 때 다운타임을 어떻게 처리하나요?"
- §8.5(`predictions` 테이블 확장)·§9.3(`feature_snapshots`, `model_runs` 추가) 같은 후속 작업이 모두 *마이그레이션 도구 없이* 구현 불가.

#### 보완 방법

1. **Alembic 도입**: `ai_service`(또는 별도 `migrations/` 서비스)에 Alembic을 두고 `alembic revision --autogenerate` → `alembic upgrade head`. compose 기동 시 `depends_on: db`인 1회성 `migrate` 컨테이너가 마이그레이션을 실행하고 종료.
2. **Up/Down 스크립트 페어**: 모든 마이그레이션은 롤백 가능하게 작성.
3. **CI 게이트**: PR마다 *스키마 변경 → 테스트 DB에서 up/down → 데이터 보존 확인*을 자동화.
4. **현행 `db/init/*.sql`의 책임 축소**: 초기 부트스트랩(역할 생성, 권한)만 담당. 테이블 정의는 모두 마이그레이션으로 이전.

> **사용자 질의 답변** — "보완방법의 기술적 이해가 부족합니다. 자세한 설명이 필요합니다."
>
> 4개 항목을 각각 *무엇이고 / 왜 필요하며 / 어떻게 구현하는가*로 풀어 씁니다.
>
> ---
>
> ##### 1. Alembic 도입 — 자세히
>
> **Alembic이 무엇인가**: SQLAlchemy 팀이 만든 *DB 스키마 마이그레이션 프레임워크*. Rails의 `ActiveRecord::Migration`, Django의 `makemigrations`와 같은 도구의 Python 일반판. PostgreSQL/MySQL/SQLite/Oracle/MSSQL 모두 지원.
>
> **PostgreSQL은 스스로 마이그레이션을 못 하나?** 못 합니다. PostgreSQL에는 "스키마 변경 이력"이라는 개념 자체가 없음. 누가 언제 어떤 컬럼을 추가했는지, *운영 DB가 어느 버전인지* 추적할 기본 도구가 없습니다. Alembic이 채우는 역할이 정확히 그것.
>
> **동작 원리** — Alembic은 DB 안에 자기만의 메타 테이블 하나(`alembic_version`)를 두고 *현재 적용된 마이그레이션의 ID*를 기록합니다.
>
> ```sql
> -- Alembic이 자동 생성한 메타 테이블
> CREATE TABLE alembic_version (
>   version_num VARCHAR(32) PRIMARY KEY
> );
> -- 한 행만 존재. 예: '7a3e8f12c4b9'
> ```
>
> 마이그레이션 파일 하나마다 고유 revision ID가 있고, 이전 revision을 가리키는 `down_revision` 필드로 *체인*을 구성합니다.
>
> ```text
> migrations/versions/
>   001_create_predictions.py        revision='abc1', down_revision=None
>   002_add_token_usage.py           revision='def2', down_revision='abc1'
>   003_add_prompt_hash.py           revision='ghi3', down_revision='def2'
> ```
>
> `alembic upgrade head` 실행 → 현재 DB가 `def2`이면 `ghi3`만 추가 적용. 사용자가 `down_revision` 체인을 따라 *순서를 자동 계산*합니다.
>
> **마이그레이션 파일 실제 모습**:
> ```python
> # migrations/versions/003_add_prompt_hash.py
> revision = 'ghi3'
> down_revision = 'def2'
>
> def upgrade():
>     op.add_column('predictions',
>                   sa.Column('prompt_hash', sa.CHAR(8), nullable=True))
>     op.create_index('ix_predictions_prompt_hash', 'predictions', ['prompt_hash'])
>
> def downgrade():
>     op.drop_index('ix_predictions_prompt_hash')
>     op.drop_column('predictions', 'prompt_hash')
> ```
>
> **`--autogenerate`** — 가장 강력한 부분. SQLAlchemy 모델(`Base.metadata`)과 실제 DB 스키마를 비교해 *차이를 자동 감지*하고 마이그레이션 파일 초안을 만들어 줍니다:
> ```bash
> alembic revision --autogenerate -m "add prompt_hash to predictions"
> # → migrations/versions/003_add_prompt_hash.py 생성
> ```
> 자동 생성 결과를 *반드시 사람이 검토*해야 함 — autogenerate가 놓치는 케이스(컬럼 rename은 drop+add로 잘못 감지하는 등)가 있어 운영 직전 차이를 손으로 보정.
>
> **Compose 통합 — 1회성 migrate 컨테이너**:
> ```yaml
> # docker-compose.yml
> services:
>   db: { image: postgres:13, ... }
>
>   migrate:                              # ← 새로 추가
>     build: ./migrations
>     command: alembic upgrade head
>     depends_on:
>       db:
>         condition: service_healthy
>     environment:
>       DATABASE_URL: postgresql://biofit:biofitpass@db:5432/biofitdb
>     restart: "no"                       # 1회 실행 후 종료
>
>   ai_service:
>     depends_on:
>       migrate:
>         condition: service_completed_successfully   # 마이그레이션 성공 후 기동
>     ...
> ```
> 이 한 단위로 `docker compose up`만 해도 *항상 최신 스키마*에서 시작.
>
> ---
>
> ##### 2. Up/Down 스크립트 페어 — 자세히
>
> **무엇인가** — 모든 마이그레이션 파일이 `upgrade()` (앞으로) + `downgrade()` (롤백) 두 함수를 *대칭으로* 가져야 한다는 규칙.
>
> **왜 필요한가** — 운영 중 PR을 머지했는데 *잘못된 마이그레이션*임이 발견되면 그 변경만 빼고 싶습니다. 그러나:
> - `git revert`로 코드는 되돌릴 수 있지만, *DB는 그대로 변경된 상태*.
> - downgrade가 없으면 DBA가 *직접 SQL을 짜서* 복구해야 함 — 위험·시간 소모.
>
> downgrade가 있으면:
> ```bash
> alembic downgrade -1   # 직전 버전으로
> ```
>
> **대칭의 예**:
> ```python
> def upgrade():     op.add_column('predictions', sa.Column('x', sa.Integer))
> def downgrade():   op.drop_column('predictions', 'x')
>
> def upgrade():     op.create_table('feature_snapshots', ...)
> def downgrade():   op.drop_table('feature_snapshots')
>
> def upgrade():     op.alter_column('predictions', 'message', type_=sa.Text)
> def downgrade():   op.alter_column('predictions', 'message', type_=sa.String(1000))  # 주의: 길이 초과 데이터 잘림
> ```
>
> **함정 — 데이터 손실이 있는 변경은 *진정한* 롤백 불가**:
> - `op.drop_column('predictions', 'note')` → downgrade에서 `add_column`은 가능하지만 *원래 데이터는 영원히 사라짐*.
> - 컬럼 타입 축소(VARCHAR(1000) → VARCHAR(100))도 마찬가지.
>
> 이런 경우 **expand-contract 패턴**(또는 *blue-green 마이그레이션*)을 씁니다 — 다운타임 없는 변경의 표준 패턴:
>
> ```text
> [예: predictions.note의 형식을 바꾸고 싶다]
>
> Phase 1 (expand) — 새 컬럼 note_v2 추가, NULLABLE
>   - 구 코드: 여전히 note만 사용
>   - 신 코드: note + note_v2 둘 다 write, read는 note_v2 우선
>   - 배포해도 무방: 한쪽만 배포돼도 동작
>
> Phase 2 (backfill) — 기존 note의 값을 변환해 note_v2로 복사
>   - cron 또는 일회성 script
>   - 끝나면 모든 행에 note_v2가 있음
>
> Phase 3 (contract) — note 컬럼 삭제, note_v2를 NOT NULL로
>   - 신 코드만 남은 시점에 적용
> ```
>
> 이 3단계 각각이 *별도 마이그레이션*이고, 각각이 up/down 페어를 가져야 합니다. *한 번에* 컬럼을 rename하는 마이그레이션은 운영형에서 거의 항상 다운타임 또는 데이터 손실을 부릅니다.
>
> ---
>
> ##### 3. CI 게이트 — 자세히
>
> **무엇을 자동화하는가** — PR이 마이그레이션을 추가하면, GitHub Actions(또는 다른 CI)가 *PR을 머지하기 전에* 다음을 자동 실행:
>
> 1. 빈 PostgreSQL 컨테이너 기동
> 2. **현재 main의 마이그레이션을 head까지 적용** → "PR 직전 운영 DB" 상태 재현
> 3. 시드 데이터 삽입 (대표 회원 1명, 더미 predictions·token_usage 등)
> 4. **PR의 새 마이그레이션 upgrade**
> 5. 검증:
>    - 시드 데이터가 *그대로 살아있는가* (행 수 변화, 키 보존)
>    - NOT NULL 제약 위반 없는가
>    - 외래키 cascade가 의도대로인가
> 6. **downgrade -1** → main 상태로 복귀
> 7. 시드 데이터가 *여전히* 살아있는가 검증 (다운그레이드의 데이터 보존)
> 8. **upgrade 다시** → 멱등성 확인 (두 번 적용해도 안전한가)
>
> **GitHub Actions 예시**:
> ```yaml
> # .github/workflows/migration_test.yml
> name: migration test
> on: pull_request
> jobs:
>   test:
>     runs-on: ubuntu-latest
>     services:
>       postgres:
>         image: postgres:13
>         env: { POSTGRES_PASSWORD: x, POSTGRES_DB: testdb }
>         ports: ['5432:5432']
>         options: --health-cmd pg_isready --health-interval 5s
>     steps:
>       - uses: actions/checkout@v4
>       - run: pip install alembic sqlalchemy psycopg2-binary
>       # 1) main의 head까지 적용
>       - run: git checkout origin/main -- migrations/
>       - run: alembic upgrade head
>       # 2) 시드 삽입
>       - run: psql $DATABASE_URL -f tests/seed.sql
>       # 3) PR 마이그레이션으로 upgrade
>       - run: git checkout HEAD -- migrations/
>       - run: alembic upgrade head
>       # 4) 시드 데이터 보존 검증
>       - run: pytest tests/test_seed_preserved.py
>       # 5) downgrade로 롤백
>       - run: alembic downgrade -1
>       - run: pytest tests/test_seed_preserved.py
>       # 6) 다시 upgrade — 멱등성
>       - run: alembic upgrade head
>       - run: pytest tests/test_seed_preserved.py
> ```
>
> 이 게이트가 있으면 *"마이그레이션이 운영 데이터를 깨뜨린다"는 가장 무서운 incident*가 머지 전에 자동 감지됩니다.
>
> ---
>
> ##### 4. `db/init/*.sql`의 책임 축소 — 자세히
>
> **현재 상황** — `db/init/001_predictions.sql`, `002_feedback_sleep.sql` … 이 *모든 테이블 정의 + 시드 데이터*를 한 곳에 섞어 두고 있습니다. 그리고 `pgdata` 볼륨이 비어 있을 때만 실행 — 즉 **첫 부팅 한 번만 의미가 있고 그 후엔 무용지물**.
>
> **운영형 책임 분리**:
>
> | 분류 | 무엇 | 어디서 처리 |
> |----|----|----|
> | **부트스트랩** | `CREATE ROLE`, `CREATE EXTENSION pg_trgm`, `GRANT`, 권한 설정 | `db/init/*.sql` *유지* (한 번이면 충분한 것) |
> | **테이블 정의** | `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX` | Alembic 마이그레이션 *모두 이전* |
> | **시드 데이터** | 더미 회원, 그룹 세션 데모 데이터 | `seeds/*.sql` 또는 pytest fixture로 분리 |
> | **참조 데이터** | `workout_keywords` enum 값(§questions.md Q2) | data migration (Alembic 안에 데이터 INSERT 작성) |
>
> **현행 → 운영형 변환 예**:
> ```text
> Before:
>   db/init/001_predictions.sql   ← CREATE TABLE + 인덱스 + 권한 + 시드 모두 섞임
>   db/init/002_feedback_sleep.sql
>   db/init/004_partner_schema.sql
>   db/init/006_token_usage.sql
>   db/init/feedback_sleep.csv    ← \copy로 적재
>
> After:
>   db/init/000_bootstrap.sql      ← CREATE ROLE biofit, GRANT만 (1회성)
>
>   migrations/versions/
>     001_predictions.py           ← CREATE TABLE predictions + index
>     002_token_usage.py
>     003_partner_schema.py        ← users, preferred_slots, group_sessions, match_history
>     004_feedback_sleep.py        ← sleep_feedback 통합 테이블
>     005_data_keywords.py         ← workout_keywords 참조 데이터 INSERT
>
>   seeds/
>     dummy_users.sql              ← 데모용. 운영에선 실행하지 않음
>     feedback_sleep_2024.csv      ← 분석용 과거 데이터, 별도 적재 스크립트
> ```
>
> **이게 중요한 이유**:
> - `db/init/`이 부트스트랩만 담당하면, *컨테이너 한 번 띄우고 영원히 잊을 수 있음*. 테이블 변경은 모두 Alembic으로 추적.
> - 시드는 `pytest`/`make seed`로 *원할 때만* 실행 — 운영 DB가 더미 데이터로 오염되지 않음.
> - 새 환경(staging, production, CI) 모두 *같은 마이그레이션 체인*으로 도달 — *어느 환경이 어느 버전*인지 `alembic_version` 한 번에 확인.
>
> ---
>
> ##### 면접 답변용 한 줄 요약
>
> > "현재 `db/init/*.sql`은 첫 기동 1회만 동작하므로 운영 DB는 사실상 *수동 SQL 적용*에 의존합니다. Alembic을 도입해 (1) 마이그레이션 체인을 코드로 관리, (2) 모든 변경을 up/down 페어로 작성해 롤백 가능하게, (3) PR마다 CI에서 *upgrade → seed 보존 검증 → downgrade → 멱등성 확인*을 자동 실행, (4) `db/init/`은 부트스트랩만 남기고 테이블 정의는 모두 마이그레이션으로 이전. *expand-contract 패턴*으로 NOT NULL 추가나 컬럼 rename도 다운타임 없이 진행할 수 있습니다."


---

### 9.8 관찰가능성·분산 추적·구조화 로그 부재 🟡

#### 약점

- 모든 서비스가 stdout으로 비구조화 로그(`print(...)`, `logging.info(f"...")`)만 출력. 사용자 1명의 한 호출이 streamlit → data_service → ai_service → vLLM 을 거치는데, 그 흐름을 *하나의 trace*로 묶을 ID가 없음.
- 메트릭 수집 부재: 응답 시간 p50/p95/p99, 에러율, 활성 세션 수 같은 운영 신호가 없음. 토큰 사용량(`token_usage`)만 있는데 그것도 *직접 SQL을 짜야* 보임.
- `predictions.note` 컬럼은 `"run completed"` 한 문자열만 들어감(`app_ai.py:54`). 실패한 호출의 단서가 DB에도 로그에도 거의 남지 않음.

#### 왜 문제인가

- 운영 단계에서 "왜 이 회원의 추론이 30초 걸렸나"라는 질문에 답하려면 분산 추적이 필수.
- 면접관: "동시에 5명이 요청했을 때 어느 단계가 병목인지 어떻게 보나요?" → 현재로선 답할 도구 없음.

#### 보완 방법

1. **OpenTelemetry**: FastAPI 인스트루멘테이션(`opentelemetry-instrumentation-fastapi`) + `psycopg2`·`requests` 인스트루멘테이션. 한 요청의 trace_id가 streamlit→data_service→ai_service→PostgreSQL→vLLM까지 따라감. Jaeger 또는 Tempo로 시각화.
2. **structlog**: 로그를 JSON으로 출력해 `uid`, `run_id`, `service`, `latency_ms` 같은 필드로 조회 가능하게.
3. **Prometheus exporter**: `prometheus-fastapi-instrumentator`로 각 서비스에 `/metrics` 노출. Grafana 대시보드에 응답 시간, 에러율, vLLM 호출 빈도, 토큰 비용을 묶어 표시.
4. **`predictions.note` 활용**: 실패 시 단계별 에러를 그대로 적재(`"vllm_timeout: ..."`, `"catboost_failed: ..."`) → SQL로 즉시 분석 가능.

면접 답변용으로는 이 정도면 충분합니다: "OpenTelemetry로 trace_id를 서비스 간 propagate하고, structlog + Prometheus로 메트릭과 구조화 로그를 묶어 Grafana에서 본다."

---

### 9.9 회원 데이터 삭제·보존 정책의 일관 흐름 부재 🟡

#### 약점

회원 1명이 탈퇴 또는 *처리 정지 권리*(PIPA §37, GDPR right-to-erasure 유사)를 행사할 때 삭제해야 할 데이터가 **여러 서비스의 여러 테이블에 분산**되어 있고, 그것을 *한 번에 일관되게* 처리하는 절차가 없습니다.

삭제 대상 테이블 목록(현재 구조 기준):
- `data_service` 영역: `{uid}_sleep_summary`, `{uid}_activity_sum`, `{uid}_resting_hr`, `{uid}_azm`, `{uid}_heart_rate_1min`, `{uid}_activity_1min`, `{uid}_hrv`, `{uid}_sleep_detail` … (회원당 N개의 동적 테이블)
- `feedback_api` 영역: `{uid}_feedback`
- `ai_service` 영역: `predictions WHERE uid=?`, `token_usage WHERE uid=?`
- `group_service` 영역: `users.user_id`, `preferred_slots.user_id`, `match_history.user_id` 또는 `partner_id`

#### 왜 문제인가

- 한국 PIPA·EU GDPR은 *합리적 시점 내* 삭제 의무. 현재처럼 "어느 테이블이 있는지부터 찾아야" 하는 구조는 *적시 삭제*를 보장하지 못함.
- 헬스케어 도메인이라 *민감정보*에 해당 → 위반 시 과징금·신뢰 훼손.
- 면접관(특히 헬스케어/금융권): "회원 탈퇴 시 데이터를 어떻게 지우시나요?"에 답이 *동적 테이블 카탈로그를 grep해서…*가 되면 곤란.

#### 보완 방법

1. **회원 데이터 카탈로그 메타 테이블**: `user_data_inventory(user_id, service, table, column_pattern)` 같은 메타 정보를 두고, 삭제 시 자동 순회.
2. **삭제 API**: `DELETE /users/{uid}` 엔드포인트가 모든 서비스에 존재 → 오케스트레이터(streamlit 또는 별도 admin 서비스)가 순차 호출 → 실패 시 §9.6의 멱등성·재시도 정책으로 복구.
3. **§9.2의 정규화 전환과 결합**: 동적 `{uid}_*` 테이블을 *공통 테이블 + `user_id` 컬럼*으로 바꾸면, 삭제는 `WHERE user_id = ?` 한 줄. 카탈로그 grep 불필요.
4. **보존 기간 정책**: `predictions`, `token_usage`, `*_minute` 같은 고빈도 데이터는 90일 후 자동 삭제(또는 익명화). cron job + soft-delete column.
5. **감사 로그**: 삭제 요청·실행·완료를 `data_lifecycle_audit` 테이블에 적재 → 규제 대응 시 증거.

이 항목은 §5.3(인증·권한)이 *접근 통제*를 다뤘다면, 여기서는 *데이터 라이프사이클*을 다룹니다. 두 축이 모두 운영 진입의 PIPA 갭 분석에 들어가야 합니다.

---

### 9.10 MSA 설계 보완용 한 문장 요약

포트폴리오에는 다음 논리로 정리하면 과장을 줄이면서 설계 의도를 살릴 수 있습니다.

> BioFit은 Streamlit을 사용자 오케스트레이션 계층으로 두고, Fitbit 수집/피드백 수집/AI 코칭/그룹 추천을 FastAPI 서비스로 분리한 MSA 프로토타입이다. 현재는 데모 속도를 위해 PostgreSQL을 공유 통합 저장소로 사용하지만, 운영 전환 시에는 서비스별 데이터 소유권, 표준 feature snapshot, run_id 기반 추적, 외부 vLLM health/fallback, 비동기 prediction job으로 경계를 강화하도록 설계했다.

---

## 10. 정리 — 우선순위

면접·포트폴리오 보강 관점에서:

> §8·§9 추가 항목까지 통합한 최종 우선순위입니다. 1차 작성 시 §2.1을 🥇로 두었지만, 재검토에서 발견한 §8.1(시계열 누수)이 더 근본적이라 §2.1보다 위로 재배치합니다.

| 우선 | 약점 | 보완 비용 | 임팩트 |
|----|----|----|----|
| 🥇 | §8.1 시계열 누수 제거(타깃을 t+1로, 동일시점 변수 제외) | 코드 ~80줄, 1일 | 평가가 *정직한 baseline*이 되어 §2.1·§4 분석의 토대가 생김 |
| 🥇 | §8.2 운동 시간대 추천을 코드 측 회귀로 전환 | 코드 ~150줄, 2일 | 핵심 결과물이 LLM 환각이 아닌 *데이터 기반 산출물*이 됨 |
| 🥇 | §1 인과 가설의 한계를 README·슬라이드에 명시 | 1줄 수정 | 인과/상관 구분 가능한 사람으로 인식 |
| 🥇 | §2.1 train/test 분리 + RMSE/MAE 기록 | 코드 ~50줄, 1일 | "성능 얼마?" 질문에 답 가능 (단, §8.1 선결) |
| 🥈 | §8.5 `predictions`에 모델·프롬프트 버전 기록, 백업 파일 정리 | 코드 ~40줄, 0.5일 | MLOps 사고 어필; 디버깅·실험 비교 가능 |
| 🥈 | §9.1~§9.3 MSA 데이터 소유권·표준 feature 테이블·run_id 전파 설계 문서화 | 문서 1쪽, 코드 선택 | "서비스를 왜 나눴고 데이터가 어떻게 추적되는가" 질문에 답 가능 |
| 🥈 | §9.4 vLLM을 외부 GPU 추론 계층으로 명시하고 health/fallback 계약 추가 | 문서 + 코드 ~30줄 | Docker Compose 재현 범위와 LLM 의존성을 명확히 설명 가능 |
| 🥈 | §9.6 멱등성 키 + 상태 머신(`model_runs`) + 재시도 정책 | 코드 ~80줄 | 분산 시스템 단골 질문에 답 가능; 토큰·결과 정합성 확보 |
| 🥈 | §9.7 Alembic 마이그레이션 도입, `db/init/*.sql` 책임 축소 | 1~2일 | "운영 DB 스키마 어떻게 바꾸시나요?" 질문에 답 가능 |
| 🟢 | §9.8 OpenTelemetry trace + structlog + Prometheus exporter | 1~2일 | 운영 관찰가능성 어필; trace_id 전파 답변 가능 |
| 🟢 | §9.9 회원 데이터 삭제 흐름 + 보존 기간 정책 (PIPA 대응) | 코드 ~60줄 + 메타 카탈로그 | 헬스케어 도메인 법규 인식; §5.3과 묶어 PIPA 갭 분석 |
| 🥈 | §2.3 이행 여부를 정량 신호로 추출해 LLM에 주입 | 코드 ~80줄 | LLM 추측 대신 데이터 기반 의사결정 |
| 🥈 | §5.1 LLM 출력 JSON schema + 재시도·폴백 | 코드 ~50줄, 0.5일 | 운영 가능 신뢰성 |
| 🥈 | §8.3 트레이너 thumbs up/down + 회원 follow-up | UI·DB ~50줄, 0.5일 | 품질 평가 사이클 closed loop 시연 가능 |
| 🥉 | §3.2 주관-객관 격차 모델링 (별도 모델 또는 target 이동) | 1~2일 | 도메인 깊이 |
| 🥉 | §4 within-subject 4주 미니 실험 | 본인 데이터 + 분석 1일 | 인과 검증 시도 자체가 차별점 |
| 🥉 | §8.4 group_service 양방향 매칭·동의 흐름 + funnel 측정 | 1주 | 매칭 → 만남 → 출석 conversion 데이터 확보 |
| 🟢 | §5.2 의료 면책·가드레일 | 30줄 | 법무 리스크 인식 |
| 🟢 | §5.3 OAuth 서버측화 + 트레이너 RBAC | 2~3일 | 운영 단계 entry 조건 |
| 🟢 | §6 민감도 분석 (이탈 감소 효과 0/5/10/20%) | 엑셀 1쪽 | 비즈니스 사고 |
| 🟢 | §8.6 비동기 호출·호출 한도·vLLM 폴백 | 1~2일 | 동시 사용자 시나리오 대응 |

#### 시간 예산별 권장 경로

- **면접 1주 전 (≤2일)**: 🥇 4건 중 §1 + §8.1 + §2.1을 처리. §8.2는 코드 작업이 큰 만큼 *말로 풀 수 있게* 보완 설계만 작성.
- **면접 1개월 전 (≤2주)**: 🥇 모두 + 🥈 항목 중 §8.5, §8.3, §9.1~§9.4, §9.6, §9.7. 결과물은 *전·후 비교 표*와 *MSA 데이터 흐름 다이어그램* + *Alembic 마이그레이션 데모*로 포트폴리오에 첨부.
- **3개월 후 후속 발표/논문화**: 🥉의 §4 within-subject 실험을 본인 데이터로 진행, 그 데이터로 §8.2 회귀 모델을 학습·검증.

> **공통 면접 답변 패턴**: "이 프로젝트는 *프로토타입* 단계로 인과 효과는 미증명이지만, 약점을 인지하고 그 다음 실험으로 §X·§Y를 설계해 두었습니다." — *겸손한 정직*이 *과장된 자신감*보다 시니어에게 잘 통합니다.
