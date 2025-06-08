CREATE TABLE IF NOT EXISTS "23RK3S_feedback" (
    user_id     TEXT NOT NULL,
    date        DATE NOT NULL,
    sleep_score INT  NOT NULL CHECK (sleep_score IN (0,1))
);

\copy "23RK3S_feedback"(user_id, date, sleep_score) FROM '/feedback_sleep.csv' CSV HEADER
