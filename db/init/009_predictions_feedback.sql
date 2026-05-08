-- 009_predictions_feedback.sql
-- §8.3 코칭 메시지 품질 평가 루프 — 트레이너 thumbs up/down + 회원 별점 + 코멘트.
-- predictions의 run_id를 외래키로 참조해 *어떤 추론*이 *어떻게 평가됐는가*를 기록.
--
-- 평가 페이로드 패턴:
--   - 트레이너: { useful: true|false, rated_by: 'trainer-id-123', comment: '...' }
--   - 회원:    { rating: 1..5,        rated_by: '23RK3S',          comment: '...' }
--   - 둘 다: rating 또는 useful 중 *최소 하나*는 NOT NULL이어야 의미가 있음 (CHECK 강제)

CREATE TABLE IF NOT EXISTS predictions_feedback (
    id          SERIAL PRIMARY KEY,
    run_id      UUID    NOT NULL REFERENCES predictions(run_id) ON DELETE CASCADE,
    rating      SMALLINT CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    useful      BOOLEAN,
    comment     TEXT,
    rated_by    TEXT    NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),

    -- 1인 1회 평가 (수정 원하면 PUT/PATCH로 별도 처리)
    CONSTRAINT uq_predictions_feedback_run_rater UNIQUE (run_id, rated_by),

    -- rating·useful 중 최소 하나는 채워져야 함
    CONSTRAINT ck_predictions_feedback_at_least_one CHECK (
        rating IS NOT NULL OR useful IS NOT NULL
    )
);

-- run_id별 최신 평가 조회용
CREATE INDEX IF NOT EXISTS idx_predictions_feedback_run_id
    ON predictions_feedback(run_id);

-- 평가자별 활동 집계용
CREATE INDEX IF NOT EXISTS idx_predictions_feedback_rated_by
    ON predictions_feedback(rated_by);
