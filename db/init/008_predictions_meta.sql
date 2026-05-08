-- 008_predictions_meta.sql
-- §8.5 모델·프롬프트·LLM 메타 추적 컬럼 추가.
-- Phase 1의 007_predictions_eval_columns.sql 위에 누적.
-- 모두 NULLABLE — 기존 행과 호환.
--
-- 추가되는 컬럼:
--   model_version          TEXT  — sleep_coach MODEL_VERSION 상수 (예: 'phase2_§8.2_window_regression')
--   prompt_hash            CHAR(8) — sha256(SYS_PROMPT + prompt)[:8]
--   llm_params             JSONB — 호출 시점 model/temperature/top_p/max_tokens 캡처
--   recommended_slot_json  JSONB — §8.2 회귀 산출 top-3 슬롯 ([{start, end}, ...])

ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS model_version          TEXT,
    ADD COLUMN IF NOT EXISTS prompt_hash            CHAR(8),
    ADD COLUMN IF NOT EXISTS llm_params             JSONB,
    ADD COLUMN IF NOT EXISTS recommended_slot_json  JSONB;

-- 모델 버전별 회귀 성능 모니터링 (model_version × rmse_test 분포 추적)
CREATE INDEX IF NOT EXISTS idx_predictions_model_version
    ON predictions(model_version);

-- 같은 prompt_hash 호출의 결과 분포 (LLM 비결정성 분석용)
CREATE INDEX IF NOT EXISTS idx_predictions_prompt_hash
    ON predictions(prompt_hash);
