# Questions
1. 맞춤형 데이터베이스(Polyglot Persistence) 선택 가능성? 내용의 타당성을 검토해주세요. 굳이 필요 없다면 필요 없다고 해주세요.
현재 (공유 DB): 모든 데이터가 PostgreSQL 하나에 저장됩니다. 물론 훌륭한 DB지만, 모든 일에 최적은 아닙니다.
소유권 분리 시: 서비스의 성격에 맞춰 가장 빠르고 효율적인 DB를 고를 수 있습니다.
data_service: 센서 로그가 초당 무지막지하게 들어오므로 시계열 DB(InfluxDB)나 NoSQL(MongoDB) 도입.
group_service: "A회원과 B회원의 매칭" 등 관계 중심이므로 그래프 DB(Neo4j) 사용.
ai_service: 코칭 결과 텍스트 저장은 PostgreSQL 유지.

2. 현재 파트너 및 세션 추천은 하드 코딩 로직으로 진행되고 있어. 프레이너와 회원의 상담 도중 추천도 일어나야할 거 같아. 추천은 ML로 하기보다 운동 스타일 키워드와 운동 시간대 기준으로 해당하는 목록을 보여주면 될 거 같아. 따라서 트레이너 화면에 회원이 운동 나오기로 한 시간대 또는 키워드를 입력하면 (키워드는 선택적으로) 그 시간대와 키워드에 교집합이 되는 대상들을 보여주는 로직을 추가하면 좋을거같아. 이에 대한 타당성 검증과 보완 사항이 있으면 제안해주세요.

---

# Answers

## 1. Polyglot Persistence 도입 타당성 검토

### 결론 — 현재 단계에서는 **불필요**, 단계적 진화 권장

세 서비스의 데이터 특성·접근 패턴·실제 데이터량을 따져보면, 각 NoSQL/그래프 DB의 강점이 *현재 BioFit이 풀고 있는 문제*에서는 거의 활용되지 않습니다. PostgreSQL 한 개로 시작하고, *특정 데이터 종류가 핵심 가치*가 될 때 부분 도입이 시니어 답변입니다.

### 서비스별 검토

#### data_service (시계열 DB 도입 제안: InfluxDB / MongoDB) — 🟡 부분 타당, 현재 단계 over-engineering

| 축 | 현재 데이터 / 접근 패턴 | InfluxDB 강점이 발현되는 조건 | 매칭 여부 |
|----|----|----|----|
| 데이터 양 | 회원당 분 단위 ≈ 1,440행/일. 200명 × 30일이면 약 870만 행 | 1억+ 행, 초당 수십만 write | ❌ 한참 미달 |
| 쓰기 패턴 | Fitbit API로 *배치* 적재 (`csv_to_db.py` 호출 시점에 일괄) | 초 단위 streaming ingest | ❌ 배치 |
| 핵심 쿼리 | 회원·날짜 윈도우의 `mean/sum`, 다른 테이블과 `JOIN` | downsampling, retention policy, continuous query | ⚠ 일부만 |
| Join 필요성 | sleep_summary, activity_sum, hrv 등 *다른 종류* 시계열을 외부 변수와 결합 | InfluxDB는 join이 약함 (Flux는 가능하지만 SQL 대비 표현력 떨어짐) | ❌ PostgreSQL이 더 강함 |

→ **PostgreSQL의 BRIN 인덱스 + `(user_id, date) PRIMARY KEY` + 월 단위 partitioning**으로 현재 100배 데이터까지 충분히 감당. 실제로 *분 단위 분석*이 핵심 기능이 되면 그때 **TimescaleDB**(PostgreSQL extension) 도입 — InfluxDB로 가지 않아도 시계열 최적화 인덱스/파티셔닝/연속 집계를 얻을 수 있고 마이그레이션 비용도 거의 0.

MongoDB는 *스키마가 회원·디바이스마다 다른* JSON-heavy 데이터에 적합한데, Fitbit 데이터는 스키마가 고정이므로 더더욱 부적합.

#### group_service (그래프 DB 도입 제안: Neo4j) — 🔴 현재 단계 부적합

매칭 로직을 코드로 보면(`group_service/main.py:38-45`):
```python
def overlap(a_start, a_end, b_start, b_end, min_minutes=30):
    ...
```

이는 두 회원의 *시간 구간 겹침*을 비교하는 단순 boolean. 그래프 DB의 핵심 가치는 *다중 hop 트래버설*("A의 친구의 친구의 친구 중 운동 레벨이 비슷한 사람")인데, 본 시스템은 1-hop도 아닌 *시간 비교*입니다.

PostgreSQL로 동일 질의:
```sql
SELECT b.user_id
FROM preferred_slots a
JOIN preferred_slots b ON a.user_id != b.user_id
WHERE a.user_id = :me
  AND tsrange(a.slot_start::timestamp, a.slot_end::timestamp)
   && tsrange(b.slot_start::timestamp, b.slot_end::timestamp)
  AND EXTRACT(EPOCH FROM (
        LEAST(a.slot_end, b.slot_end) - GREATEST(a.slot_start, b.slot_start)
      )) >= 1800;
```

PostgreSQL의 **range type + GiST 인덱스**가 시간 구간 매칭에 *그래프 DB보다 빠릅니다*. Neo4j는 매칭이 "공통 친구 기반 추천", "유대감 클러스터링", "이벤트 전파 분석" 같은 도메인으로 *진화한 후*에야 가치가 발현됩니다.

#### ai_service (PostgreSQL 유지) — ✅ 동의

`predictions.message`의 텍스트 검색이 빈번해지면 PostgreSQL의 **`tsvector` + GIN 인덱스**(전문 검색)로 충분. 별도 검색 엔진(Elasticsearch)도 회원 수가 *수만 명* 단계까지는 불필요.

### 단계적 도입 로드맵 (필요해질 때만)

| 트리거 신호 | 도입 대상 | 비용 |
|----|----|----|
| 분 단위 시계열이 *핵심 분석 단위*가 되고 데이터가 1억 행 이상 | TimescaleDB extension (PostgreSQL 위에 얹음) | 작음, 마이그레이션 거의 0 |
| 회원 매칭이 "공통 친구·관계 강도·클러스터링"으로 진화 | Neo4j 또는 PostgreSQL `pgrouting` | 중간 |
| LLM 호출 결과 텍스트에 의미 검색(vector similarity)이 필요 | `pgvector` extension (PostgreSQL 내) → 한계 시 Qdrant/Weaviate | 작음 → 큼 |
| 회원·트레이너·기기 간 권한 그래프가 복잡해짐 | OpenFGA / Cedar 같은 권한 엔진 | 별도 영역 |

### 면접 답변 패턴

> "Polyglot Persistence는 알고 있지만 *현재 데이터 양과 쿼리 패턴이 정당화하지 않으므로* PostgreSQL 한 개로 시작했습니다. 시계열이 분 단위로 핵심 분석 단위가 되면 TimescaleDB extension으로 점진 전환하고, 그래프 추천이 다중 hop으로 진화하면 그때 Neo4j를 검토합니다. 운영 부담이 두 배가 되는 결정은 *데이터로 정당화될 때*만 합니다."

이렇게 답하면 "도구를 안다 + 적용 시기를 안다 + 운영 비용을 안다"가 한 번에 어필됩니다.

---

## 2. 키워드 + 시간대 교집합 기반 파트너 추천

### 결론 — **타당성 강함**, 현재 프로젝트 단계에서 ML보다 적합

데이터가 적은 프로토타입에서 ML 매칭은 본질적으로 *cohort 평균을 외우는 수준*이고, 트레이너 입장에서 *왜 이 사람을 추천하는지* 설명할 수 없습니다. 키워드+시간대 교집합은:

- **해석 가능** — "운동 시간 18:00–19:00 + 키워드 [근력]" 두 조건의 교집합이라는 답변이 명확.
- **상담 중 즉시 조정** — 트레이너가 "그럼 시간대를 17:00로 옮기면?" 같은 what-if를 *그 자리에서* 다시 돌릴 수 있음.
- **차가운 시작(cold-start)에 강함** — 신규 회원도 키워드와 시간대만 입력하면 즉시 추천 가능.
- **ML 추천의 ground truth 수집** — 어떤 추천이 *실제 매칭*으로 이어졌는지 데이터를 쌓으면, *나중에* 랭킹 모델 학습에 사용 가능.

### 설계 보강 제안

#### 1. 데이터 모델

`users`/`preferred_slots`만으로는 부족 — 키워드 컬럼이 없습니다. 다음 두 옵션:

**옵션 A — 정규화 테이블 (권장)**

```sql
CREATE TABLE workout_keywords (
  keyword TEXT PRIMARY KEY,
  category TEXT NOT NULL    -- 예: 'strength', 'cardio', 'flexibility'
);

CREATE TABLE user_keywords (
  user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
  keyword TEXT REFERENCES workout_keywords(keyword),
  PRIMARY KEY (user_id, keyword)
);

INSERT INTO workout_keywords VALUES
  ('근력', 'strength'), ('유산소', 'cardio'),
  ('요가', 'flexibility'), ('필라테스', 'flexibility'),
  ('HIIT', 'cardio'), ('스트레칭', 'flexibility'),
  ('맨몸', 'strength');
```

**옵션 B — 배열 컬럼 (단순)**

```sql
ALTER TABLE users ADD COLUMN preferred_keywords TEXT[];
CREATE INDEX ON users USING GIN (preferred_keywords);
```

PostgreSQL `&&` (overlap) 연산자로 교집합 쿼리:
```sql
WHERE u.preferred_keywords && ARRAY['근력', '유산소']
```

옵션 B가 코드는 간단하지만, *"근력"·"근력 운동"·"근력운동"이 같은 키워드인지* 같은 정규화 책임이 운영 중 비싸집니다. 실제 서비스라면 옵션 A를 권장.

#### 2. 자유 입력 vs. 사전 정의 enum

자유 텍스트 입력은 *반드시* 정규화·동의어·오타 처리 비용이 따라옵니다. 트레이너 화면에서는 **multiselect dropdown** + **자주 쓰는 키워드 추천**이 운영상 안전합니다. Streamlit 예시:

```python
all_keywords = ["근력", "유산소", "요가", "필라테스", "HIIT", "스트레칭", "맨몸"]
selected = st.multiselect("관심 키워드 (선택)", all_keywords, default=[])
```

#### 3. 추천 SQL 한 방

```sql
WITH me AS (
  SELECT slot_start::time AS s, slot_end::time AS e
  FROM preferred_slots WHERE user_id = :uid
),
my_keywords AS (
  SELECT keyword FROM user_keywords WHERE user_id = :uid
)
SELECT
  u.user_id, u.name, u.workout_level, u.image_url,
  ps.slot_start, ps.slot_end,
  EXTRACT(EPOCH FROM (
    LEAST(ps.slot_end, me.e) - GREATEST(ps.slot_start, me.s)
  )) / 60 AS overlap_minutes,
  ARRAY_AGG(uk.keyword) AS shared_keywords
FROM users u
JOIN preferred_slots ps ON ps.user_id = u.user_id
JOIN me ON GREATEST(ps.slot_start, me.s) < LEAST(ps.slot_end, me.e)
LEFT JOIN user_keywords uk ON uk.user_id = u.user_id
                           AND uk.keyword IN (SELECT keyword FROM my_keywords)
WHERE u.user_id != :uid
  AND EXTRACT(EPOCH FROM (
        LEAST(ps.slot_end, me.e) - GREATEST(ps.slot_start, me.s)
      )) >= 1800   -- 30분 이상
GROUP BY u.user_id, u.name, u.workout_level, u.image_url, ps.slot_start, ps.slot_end, me.s, me.e
ORDER BY
  CARDINALITY(ARRAY_AGG(uk.keyword) FILTER (WHERE uk.keyword IS NOT NULL)) DESC,  -- 1순위: 키워드 일치 수
  overlap_minutes DESC                                                              -- 2순위: 시간 겹침 길이
LIMIT 20;
```

이 한 쿼리가 *키워드 선택적, 시간대는 필수* 조건과 *해석 가능한 정렬*을 모두 처리합니다.

#### 4. 트레이너 화면 UX 흐름

```
[현재 회원 ID]            (자동)
[추천할 시간대 from] 18:00
[추천할 시간대 to]   19:00
[관심 키워드 (선택)] [근력] [유산소] [×]
[ 🔍 후보 찾기 ]

→ 결과 카드:
  Charlie  | 18:00–19:00 | 겹침 60분 | 공통 키워드 [근력, 유산소] | High
  Jenney   | 18:30–19:30 | 겹침 30분 | 공통 키워드 [근력]         | Middle
  ...
```

#### 5. 빈 결과 fallback (운영상 자주 발생)

후보가 0명일 때 트레이너에게 *"왜 없는지"* 설명하는 것이 중요. 단계적 완화:

| 단계 | 완화 조건 | 메시지 |
|----|----|----|
| 1 | 시간대 정확 매칭 + 키워드 모두 일치 | 기본 |
| 2 | 시간대 정확 매칭 + 키워드 1개라도 일치 | "키워드 일부만 일치하는 후보입니다" |
| 3 | 시간대 ±30분 확장 + 키워드 매칭 | "시간대를 30분 확장한 결과입니다" |
| 4 | 시간대 매칭만 (키워드 무시) | "조건에 맞는 후보가 없어 시간대만으로 추천합니다" |

#### 6. 회원 동의 흐름과 연결 (§8.4 보강)

추천 결과를 *그대로 회원에게 노출*하지 말고, **트레이너 → 회원 A 동의 → 회원 B 동의 → 연락처 교환**의 3단계 게이트. `match_history`에 각 단계 timestamp를 기록해 *추천 → 매칭 → 만남 → 동행 출석* funnel 측정.

#### 7. 데이터를 쌓는 의도적 설계 — 미래 ML 추천의 ground truth

추천이 일어날 때마다 다음을 적재:

```sql
CREATE TABLE recommendation_events (
  rec_id        UUID PRIMARY KEY,
  trainer_id    TEXT,
  user_id       TEXT,             -- 추천을 받은 회원
  candidate_id  TEXT,             -- 추천된 상대방
  query_slot    TSRANGE,
  query_keywords TEXT[],
  rank          INT,
  outcome       TEXT,             -- 'shown' | 'proposed' | 'accepted_by_a' | 'accepted_by_b' | 'first_meet' | 'sustained_4w'
  outcome_at    TIMESTAMPTZ
);
```

3~6개월 누적되면 (입력 키워드, 시간대, 회원 특성) → (4주 후에도 동행 운동 중) 데이터로 **랭킹 모델**을 학습할 수 있는 토대가 생깁니다. 즉 "처음엔 단순 규칙으로 시작했지만, 데이터가 쌓이면 ML로 진화 가능한 설계"라는 *학습 가능한 시스템* 어필이 가능.

### 보완 사항 한 줄 요약

키워드 + 시간대 교집합으로 시작하는 결정은 **데이터가 적은 단계의 정답**입니다. 다만 (1) 키워드를 사전 정의 enum으로 시작, (2) 빈 결과 fallback 단계 정의, (3) 회원 양측 동의 게이트, (4) 추천 결과를 `recommendation_events`에 적재해 미래 ML의 ground truth 확보 — 이 네 가지를 함께 설계하면 *현재 단순함의 가치*를 유지하면서도 *미래 진화 가능성*을 닫지 않습니다. 동의합니다.