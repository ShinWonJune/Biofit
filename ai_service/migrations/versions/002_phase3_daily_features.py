"""phase3 §9.1 expand: fitbit_daily_features 정규화 wide-format 테이블

분석 문서 §9.1에서 지적한 동적 `{uid}_*` 테이블 폭증(회원 200명 시 1,800개)을
*expand-contract* 패턴의 expand 단계로 해소. 기존 동적 테이블은 그대로 유지하고,
새 정규화 테이블을 *추가*. dual-write/dual-read는 ai_service·data_service의
env flag로 옵트인 (DUAL_WRITE_NORMALIZED, USE_NORMALIZED_FEATURES).

Revision ID: 002
Revises: 001
Create Date: 2026-05-08
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fitbit_daily_features (
            user_id              TEXT NOT NULL,
            date                 DATE NOT NULL,
            -- sleep summary (Phase 1 LEAK_VARS — 누수 변수도 raw 컬럼은 보존,
            -- get_X 단계에서 LEAK_VARS 제외 로직이 그대로 적용됨)
            efficiency           FLOAT,
            stage_deep           INT,
            stage_light          INT,
            stage_rem            INT,
            stage_wake           INT,
            time_in_bed          INT,
            wake_count           INT,
            -- activity
            steps                INT,
            distance             FLOAT,
            calories             FLOAT,
            -- vital
            resting_hr           FLOAT,
            azm_total            INT,
            azm_fatburn          INT,
            azm_cardio           INT,
            -- HRV (분 단위 집계 결과 일별 평균)
            hrv_rmssd            FLOAT,
            hrv_hf               FLOAT,
            hrv_lf               FLOAT,
            -- 메타
            source_run_id        UUID,
            ingested_at          TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, date)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_fdf_date ON fitbit_daily_features(date DESC);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_fdf_date;")
    op.execute("DROP TABLE IF EXISTS fitbit_daily_features;")
