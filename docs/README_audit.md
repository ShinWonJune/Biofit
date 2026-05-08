# README 검증 보고서

`README.md`의 서술이 실제 코드(`docker-compose.yml`, 각 서비스의 `Dockerfile` / `*.py`, `db/init/*.sql`)와 일치하는지 라인 단위로 검증한 결과입니다. 각 이슈는 **README 주장 → 실제 증거 → 실제 동작에 미치는 영향 → 권장 수정안** 순으로 기술합니다.

## 한눈에 보기

| # | 이슈 | 심각도 | README 위치 | 코드 위치 |
|---|------|--------|------------|----------|
| 1 | 수면 점수 척도가 "1~5점"이 아니라 3단계(0/1/2) | 🔴 High | `README.md:15` | `streamlit_app/streamlit_feedback.py:14-21` |
| 2 | 더미 테이블의 `CHECK` 제약이 (0,1)뿐이라 "잘잤어!"(=2) 입력 시 위반 | 🟡 Medium | `README.md:131` | `db/init/002_feedback_sleep.sql:4` |
| 3 | `data_service` 호스트 포트 매핑(8000:8000)이 컨테이너 리스닝 포트(8001)와 어긋남 | 🔴 High | `README.md:58, 94` | `data_service/Dockerfile:23-25` vs `docker-compose.yml:46-47` |
| 4 | `ai_service` 호스트 포트 매핑(8002:8002)이 컨테이너 리스닝 포트(8000)와 어긋남 | 🔴 High | `README.md:60, 96` | `ai_service/Dockerfile:22-25` vs `docker-compose.yml:93-94` |
| 5 | "Fitbit API 호출" 기능이 코드상 비활성(주석 처리) | 🟡 Medium | `README.md:58, 107` | `data_service/app.py:47-62` |
| 6 | `group_service`가 요청의 `uid`를 무시하고 하드코딩 슬롯만 사용 | 🔴 High | `README.md:14, 61` | `group_service/main.py:27-30, 98-100` |
| 7 | `db/init/004_partner_schema.sql` 내부 헤더 주석이 `005_*`로 적힘 | 🟢 Low | — | `db/init/004_partner_schema.sql:2` |
| 8 | README의 vLLM 엔드포인트 표기와 실제 코드 하드코딩 값의 가시성 부족 | 🟢 Low | `README.md:126` | `ai_service/sleep_coach_full_kr_v6.py:294-297` |
| 9 | 자기 개선 코칭 루프 설명에서 칼럼명이 명시되지 않아 코드와 대조 시 헤맴 | 🟢 Low | `README.md:13` | `ai_service/sleep_coach_full_kr_v6.py:194-204` |

---

## 1. 수면 점수 척도가 "1~5점"이 아니라 3단계(0/1/2) 🔴

### README 주장
`README.md:15`
```
- **체감 수면 피드백 입력 UI** — 회원이 별도 화면에서 매일 1~5점 척도로 입력.
```

### 실제 코드
`streamlit_app/streamlit_feedback.py:13-21`
```python
st.markdown("## 🛏️ 잘 잤나요?")
sleep_quality = st.radio(
    label="숙면 정도 선택",
    options=["별로", "보통?", "잘잤어!"],
    horizontal=True
)

score_map = {"별로": 0, "보통?": 1, "잘잤어!": 2}
score = score_map[sleep_quality]
```

전송되는 페이로드(`streamlit_feedback.py:30-34`):
```python
payload = {
    "user_id": uid.strip(),
    "date": selected_date.isoformat(),
    "sleep_score": score   # 0, 1, 또는 2
}
```

### 영향
- 외부 독자가 "5점 만점 리커트 척도"라고 오해. 실제로는 **3단계 정성 라벨**.
- 데이터 분석 단계에서 척도 해상도 가정이 어긋남 (예: SHAP·CatBoost 입력에 들어가는 `sleep_score`의 범위/분포가 0~2 정수).

### 권장 수정
README L15를 다음과 같이 변경:
```
- **체감 수면 피드백 입력 UI** — 회원이 별도 화면에서 매일 3단계 라디오
  ("별로", "보통?", "잘잤어!" → 0·1·2)로 입력.
```

---

## 2. 더미 테이블의 `CHECK` 제약이 (0,1)뿐 🟡

### 코드 증거
`db/init/002_feedback_sleep.sql:1-5`
```sql
CREATE TABLE IF NOT EXISTS "23RK3S_feedback" (
    user_id     TEXT NOT NULL,
    date        DATE NOT NULL,
    sleep_score INT  NOT NULL CHECK (sleep_score IN (0,1))
);
```

### 영향
- 더미 사용자 `23RK3S`로 "잘잤어!"(=2) 점수가 들어오면 `CHECK` 제약 위반으로 INSERT 실패.
- 단, `feedback_api/main.py:20-35`는 신규 사용자에 대해 매 요청마다 `{uid}_feedback` 테이블을 **SQLAlchemy로 새로 생성** (CHECK 없음):
  ```python
  feedback_table = Table(
      table_name, metadata,
      Column("user_id", String, nullable=False),
      Column("date", Date, nullable=False),
      Column("sleep_score", Integer, nullable=False),  # CHECK 없음
      extend_existing=True
  )
  metadata.create_all(engine, tables=[feedback_table])
  ```
  따라서 일반 흐름에서는 통과하지만, **데모용 시연이 23RK3S로 진행될 경우 "잘잤어!" 입력이 실패**합니다.

### 권장 수정
둘 중 하나:
1. (권장) 더미 시드의 CHECK를 `IN (0,1,2)`로 확장.
2. UI를 0/1만 받도록 옵션 축소.

---

## 3. `data_service` 호스트 포트 매핑 불일치 🔴

### 다섯 위치의 값 비교
| 위치 | 값 |
|------|----|
| `data_service/Dockerfile:23` | `EXPOSE 8001` |
| `data_service/Dockerfile:25` | `CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", ...]` |
| `docker-compose.yml:46-47` | `ports: - "8000:8000"` (호스트 8000 → 컨테이너 8000) |
| `docker-compose.yml:30` (streamlit env) | `DATA_SERVICE_URL: http://data:8001/fetch` |
| `README.md:58` (Service 표) | `data_service ... 8000` |
| `README.md:94` (URL 표) | `http://localhost:8000/docs ... Data Service Swagger` |

### 영향
- **컨테이너 내부에서는 8001만 리스닝**하므로, `8000:8000` 매핑은 응답 없는 포트로 연결됨.
- **결과**: README가 안내하는 `http://localhost:8000/docs`는 동작하지 않음. 호스트에서 Swagger UI로 접근 불가.
- 컨테이너 간 호출(streamlit → data)은 `http://data:8001`을 직접 사용하므로 사내 네트워크에서만 작동.

### 권장 수정
**호스트 포트는 README의 8000을 유지하고, 매핑의 컨테이너 측만 실제 LISTEN 포트인 8001로 정정** — `docker-compose.yml:46-47`:
```yaml
ports:
  - "8000:8001"    # host 8000 → container 8001
```
- `feedback_api`의 호스트 8001과 **충돌하지 않음** (호스트 측은 8000, 8001로 다름).
- 컨테이너 내부 포트 8001을 두 컨테이너(`data`·`feedback-api`)가 동시에 쓰는 건 무관 — 각자의 네트워크 네임스페이스라 같은 IP를 공유하지 않음.
- 사내 DNS 호출 `http://data:8001/fetch` 그대로 유효, Dockerfile 수정 불필요.

> ⚠️ `"8001:8001"`로 바꾸면 호스트 8001이 `feedback-api`와 충돌해 `Bind for 0.0.0.0:8001 failed: port is already allocated` 오류로 기동 실패합니다. 호스트 포트를 동일하게 잡지 않도록 주의.

---

## 4. `ai_service` 호스트 포트 매핑 불일치 🔴

### 다섯 위치의 값 비교
| 위치 | 값 |
|------|----|
| `ai_service/Dockerfile:22` | `EXPOSE 8000` |
| `ai_service/Dockerfile:25` | `CMD ["uvicorn", "app_ai:app", "--host", "0.0.0.0", "--port", "8000"]` |
| `docker-compose.yml:93-94` | `ports: - "8002:8002"` |
| `streamlit_app/streamlit_fitbit.py:57-58` | `AI_URL=http://ai_service:8000/predict` |
| `README.md:60` | `ai_service ... 8002` |
| `README.md:96` | `http://localhost:8002/docs ... AI Service Swagger` |

### 영향
- 호스트 `localhost:8002`로 들어온 트래픽은 컨테이너 8002로 전달되지만 **거기엔 아무것도 리스닝하지 않음**(8000만 리스닝).
- README의 `http://localhost:8002/docs`는 응답 없음.
- 컨테이너 내부 streamlit → ai_service 호출은 `http://ai_service:8000/predict`로 정상 작동.

### 권장 수정
**compose 매핑의 컨테이너 측만 실제 LISTEN 포트인 8000으로 정정** — `docker-compose.yml:93-94`:
```yaml
ports:
  - "8002:8000"    # host 8002 → container 8000
```
- README 표(`localhost:8002`)와 일치하면서 호스트 Swagger 접근 정상화.
- 사내 DNS 호출 `http://ai_service:8000/predict` 그대로 유효 (`streamlit_fitbit.py:57` 수정 불필요).
- 다른 호스트 포트와 충돌 없음 (8002는 다른 컨테이너에서 사용 안 함).

대안: Dockerfile을 8002 LISTEN으로 변경 + streamlit의 `AI_URL`도 8002로 갱신. 코드 두 군데가 바뀌므로 권장하지 않음.

---

## 5. "Fitbit API 호출" 기능 비활성 🟡

### README 주장
`README.md:58` (Service 표):
```
data_service ... Fitbit API 호출 / CSV → DB 적재
```
`README.md:107` (Usage Flow):
```
② [데이터 수집·전처리] 버튼  ─→  data_service /fetch
```

### 실제 코드
`data_service/app.py:47-62` — `00-CallAPI.py` (Fitbit API 호출) 블록 **전체 주석 처리**:
```python
# # 2) 00-CallAPI.py 실행: Fitbit API → /app/fitbit_csv/*.csv 생성
# try:
#     subprocess.run(
#         ["python3", "00-CallAPI.py", uid, s, e],
#         ...
#     )
# except subprocess.CalledProcessError as err:
#     ...
```

`/fetch`가 실제로 실행하는 것은 `csv_to_db.py`뿐이며, 이는 **이미 `./fitbit_csv/`에 준비된 CSV를 DB로 옮기는 작업만 수행**.

### 영향
- 신규 사용자가 Fitbit Access Token을 입력해도 실제 Fitbit API 호출은 일어나지 않음.
- README의 다이어그램은 "Fitbit/CSV → DB"로 사실상 후자만 동작.
- 데모 시 미리 CSV를 `./fitbit_csv/`에 넣어두지 않으면 후속 AI 추론 단계에서 빈 DB로 실패.

### 권장 수정
README L58, L107 부근에 명시적 한 줄 추가:
```
> 현재 코드의 /fetch는 ./fitbit_csv/ 에 미리 준비된 CSV를 DB로 적재하는 단계만
> 실행합니다. Fitbit API 직접 호출(00-CallAPI.py) 부분은 운영 안정성을 위해
> 일시 비활성화되어 있으며, 다시 켜려면 data_service/app.py 의 해당 블록을
> 주석 해제하세요.
```

---

## 6. `group_service`가 `uid`를 무시 🔴
### README 주장
`README.md:14`:
```
- **운동 파트너·그룹 세션 추천** — 회원별 선호 운동 시간대의 30분 이상 겹침을 기준으로 매칭.
```
`README.md:61`:
```
group_service ... 운동 가능 시간대 30분 이상 겹침 기준 파트너·그룹 매칭
```

### 실제 코드
`group_service/main.py:19-30`:
```python
class RecoReq(BaseModel):
    uid: str          # Streamlit으로부터 받음

CURRENT_USER_SLOTS = [
    (time(10, 0), time(11, 0)),
    (time(18, 0), time(19, 0)),
]   # 하드코딩, 모든 사용자 동일
SLEEP_TIME = time(22, 0)
WAKE_TIME  = time(8, 0)
```

`group_service/main.py:98-100`:
```python
@app.post("/predict")
def recommend(req: RecoReq):
    return {"status": "ok", **get_reco()}   # req.uid 사용 안 함
```

`get_reco()`는 `req.uid`를 인자로 받지 않으며, `users`/`preferred_slots`에서 **요청자의** 슬롯을 조회하는 로직이 없습니다. 모든 호출이 `[(10:00–11:00), (18:00–19:00)]`이라는 동일 기준으로 매칭됩니다.

### 영향
- "회원별"이라는 README 문구와 달리, 실제로는 어떤 회원이 호출하든 **같은 결과**가 반환됨.
- `users` 테이블의 `sleep_time/wake_time`도 응답 페이로드(`SLEEP_TIME`, `WAKE_TIME` 하드코딩 값)와 무관.

### 권장 수정
- 프로젝트는 프로토타입이기 때문에 논리만 설계함. README에 (미구현) 표기 추가.


---

## 7. `004_partner_schema.sql` 헤더 주석 파일명 불일치 🟢

### 코드 증거
`db/init/004_partner_schema.sql:1-2`
```sql
-- ---------------------------------------------------------------------------
-- 005_partner_schema.sql  |  BioFit Partner & Group Session 추천용 스키마 v2
```

실제 파일명은 `004_partner_schema.sql`. `db/init/`에는 003·005번 파일이 존재하지 않음(`001`, `002`, `004`, `006`만 있음).

### 영향
- 기능적으로는 무해. 다만 파일을 git log/grep으로 추적할 때 혼동 유발.

### 권장 수정
주석을 `004_partner_schema.sql`로 정정.

---

## 8. vLLM 엔드포인트 가시성 부족 🟢 ✅ Resolved

### README 주장
`README.md:126`:
```
| `OPENAI_BASE` (ai_service) | http://<vllm-host>:8282/v1 | vLLM (OpenAI-compatible) 추론 엔드포인트 |
```

→ 마치 환경변수로 주입되는 것처럼 보임.

### 실제 코드
`ai_service/sleep_coach_full_kr_v6.py:294-297`
```python
client = OpenAI(
    base_url="http://172.28.8.101:8282/v1",   # ② vLLM 서버 주소
    api_key="token-abc123",                   # ③ 임의 토큰 – 서버와 일치
)
```

→ **하드코딩**. `OPENAI_BASE`/`OPENAI_KEY` 환경변수는 코드에서 참조되지 않음. `docker-compose.yml`에도 해당 변수 없음.

### 영향
- 운영 환경 이전(IP 172.28.8.101이 다른 네트워크에선 무효) 시 README만 보고 환경변수만 변경하면 동작하지 않음. 코드 수정이 반드시 필요.

### 권장 수정
1. **코드를 환경변수 기반으로 전환** (권장):
   ```python
   client = OpenAI(
       base_url=os.getenv("OPENAI_BASE", "http://172.28.8.101:8282/v1"),
       api_key=os.getenv("OPENAI_KEY", "token-abc123"),
   )
   ```
   그리고 `docker-compose.yml`의 `ai_service.environment`에 두 키 추가.


---

## 9. 자기 개선 코칭 루프 칼럼명이 README에 미명시 🟢

### README 주장
`README.md:13`:
```
- **자기 개선 코칭 루프** — 직전 주의 코칭 메시지를 `predictions` 테이블에서 다시 읽어 다음 호출의 프롬프트에 주입합니다.
```

### 실제 코드
`ai_service/sleep_coach_full_kr_v6.py:194-204`
```python
def get_last_feedback(uid: str) -> str | None:
    try:
        df = read_table(
            "predictions",
            where=f"uid = '{uid}' ORDER BY created_at DESC LIMIT 1"
        )
        if not df.empty and df.iloc[0]["message"]:
            return str(df.iloc[0]["message"])
    ...
```

읽는 칼럼은 `message` (정의: `db/init/001_predictions.sql:9`).

### 영향
- 사실 자체는 맞으나, "직전 주" 표현이 모호. 실제로는 **시간 윈도우와 무관하게 가장 최근 1건**(`ORDER BY created_at DESC LIMIT 1`).

### 권장 수정
README L13을 다음과 같이 정확화:
```
- **자기 개선 코칭 루프** — 같은 회원의 가장 최근 코칭 메시지(`predictions.message`,
  ORDER BY created_at DESC LIMIT 1)를 다음 호출 프롬프트에 주입합니다. 
```

---

## 정리: 우선순위별 권장 조치

### 즉시 수정 (🔴 동작에 영향)
- **#3, #4**: compose의 data_service / ai_service 호스트 포트 매핑을 컨테이너 LISTEN 포트와 일치시킴 (`data` → `"8000:8001"`, `ai_service` → `"8002:8000"`). 호스트 포트는 README 표(8000·8002)를 유지하고 컨테이너 측만 실제 LISTEN 포트(8001·8000)로 맞춰 `feedback-api`(호스트 8001)와의 충돌을 방지.
- **#1, #6**: README 문구를 실제 동작에 맞게 정정하거나, 정정이 어려우면 코드를 README와 일치시킴.

### 가까운 시일 내 (🟡 데모/운영 시 함정)
- **#2**: 더미 테이블 `CHECK` 제약을 `(0,1,2)`로 확장.
- **#5**: README에 Fitbit API 호출 비활성 사실을 명시.

### 여유될 때 (🟢 가독성/이식성)
- **#7**: SQL 파일 헤더 주석 정정.
- ~~**#8**: vLLM 엔드포인트 환경변수화.~~ ✅ 적용됨 (`sleep_coach_full_kr_v6.py:294-297`이 `OPENAI_BASE`/`OPENAI_KEY` env 우선, 기존 IP·토큰을 default 폴백으로 유지. `docker-compose.yml`의 `ai_service.environment`에 두 키 추가).
- **#9**: README의 "직전 주" 표현을 코드 실제 의미("가장 최근")로 정정.
