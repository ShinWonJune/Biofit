# 현재
아래 피처를 통해 efficiency 예측
| 분류 | 피처 |
|---|---|
| **운동 시간대 (7)** | steps_morning(06–12), steps_afternoon(12–18), steps_evening(18–24), steps_night(00–06), last_active_hour, pre_sleep_steps_0_2h, pre_sleep_steps_2_4h |
| **운동량 (6)** | steps, distance, calories, azm_total, azm_fatburn, azm_cardio |
| **수면 시간대 (5)** | bedtime_hour, waketime_hour, bedtime_dev_min, waketime_dev_min, sleep_duration_h |
| **HRV/HR (4)** | resting_hr, rmssd_mean, hf_mean, lf_mean |


# 보완사항
- 수면의 질은 피츠버그 수면 질 지수(PSQI)를 사용하여 주관적 수면의 질, 수면 잠복기(즉, 잠드는 데 걸리는 시간), 수면 시간, 습관적 수면 효율(중간에 깨는거 파악) 로 파악하면 더 정확할 듯. 
- 각 항목 도출 가능. 각 항목은 0~3로 측정되며 최종 합이 낮을 수록 수면의 질 높음. 단, 수면 잠복기를 위한 잠자리에 드는 시간을 fitbit wake 추즉할 수 있지만 정확한 값은 아님. 현재로써는 이대로 진행.

- PSQI지수를 이루는 항목 각각을 예측하는 catboost 모델 학습. 이후 예측값을 더해서 최종 수면의 질 예측. 

- 이후 각각의 SHAP 분석을 통해 근거 마련?  

Tree SHAP는 특정 변수가 주어지지 않은 상태의 예측값을, 트리 구조에서 가능한 분기들의 가중 평균을 이용한 기대 예측값으로 계산한다.