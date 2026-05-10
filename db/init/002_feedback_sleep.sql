-- Phase A.1 — sleep_score 4단계(0~3) 확장. PSQI C1 차원과 *동일 0~3 규모*로 통일.
-- 0=최고, 1=잘잤어, 2=못잤어, 3=최악. 기존 0/1 시드 데이터는 옵션 A로 학습에서 제외.
CREATE TABLE IF NOT EXISTS "23RK3S_feedback" (
    user_id     TEXT NOT NULL,
    date        DATE NOT NULL,
    sleep_score INT  NOT NULL CHECK (sleep_score >= 0 AND sleep_score <= 3)
);

\copy "23RK3S_feedback"(user_id, date, sleep_score) FROM '/feedback_sleep.csv' CSV HEADER
