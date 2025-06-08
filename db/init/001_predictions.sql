-- db/init/001_predictions.sql
-- 실행 시점: 컨테이너가 '처음' DB를 만들 때
-- db/init/001_predictions.sql
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    uid TEXT NOT NULL,
    run_id UUID NOT NULL UNIQUE,
    note TEXT,
    message TEXT,              -- ← 추가
    created_at TIMESTAMP DEFAULT NOW()
);

-- 사용량 많을 때 조회 속도용 인덱스
CREATE INDEX IF NOT EXISTS idx_predictions_uid ON predictions(uid);
