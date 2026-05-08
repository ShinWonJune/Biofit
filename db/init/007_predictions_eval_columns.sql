-- 007_predictions_eval_columns.sql
-- §2.1 holdout RMSE/MAE + §8.1 forecast metadata를 위한 컬럼 추가.
-- 모두 NULLABLE — 기존 predictions 행과 호환.
--
-- 실행 시점: PostgreSQL 컨테이너 첫 기동 (/docker-entrypoint-initdb.d 자동 실행).
-- 운영 중 DB에 적용하려면 다음을 직접 실행:
--   docker compose exec db psql -U biofit -d biofitdb -f /docker-entrypoint-initdb.d/007_predictions_eval_columns.sql
-- 또는 (호스트에서):
--   psql $DATABASE_URL -f db/init/007_predictions_eval_columns.sql
--
-- 추가되는 컬럼:
--   rmse_test            FLOAT — §2.1 holdout test set RMSE (정직한 일반화 오차)
--   mae_test             FLOAT — §2.1 holdout test set MAE
--   data_window_end      DATE  — 추론에 사용한 학습 데이터의 마지막 날짜
--   feature_set_version  TEXT  — 사용된 feature set 버전 (예: 'v6_leak_fixed_t+1_forecast')

ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS rmse_test            FLOAT,
    ADD COLUMN IF NOT EXISTS mae_test             FLOAT,
    ADD COLUMN IF NOT EXISTS data_window_end      DATE,
    ADD COLUMN IF NOT EXISTS feature_set_version  TEXT;

-- 평가 메트릭 조회용 인덱스 (선택 — 회원·시점별 RMSE 추적 시 유용)
CREATE INDEX IF NOT EXISTS idx_predictions_data_window_end
    ON predictions(data_window_end DESC NULLS LAST);
