"""Phase F.5 — predictions에 PSQI/추천 슬롯 컬럼 추가.

PSQI 4 차원 점수, 합산 예측값, 추천 슬롯 JSON, exploration/exploitation 모드를
predictions 테이블에 박제. *추천 산출의 재현성·회귀 추적*의 단일 출처.

옵트인 default 0이라 컬럼이 NULL인 행도 정상 — Phase F 옵트인 미사용 시 그대로.

Revision ID: 006
Revises: 005
Create Date: 2026-05-10
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE predictions
            ADD COLUMN IF NOT EXISTS psqi_scores            JSONB,
            ADD COLUMN IF NOT EXISTS psqi_predicted_total   FLOAT,
            ADD COLUMN IF NOT EXISTS recommended_slot_psqi  JSONB,
            ADD COLUMN IF NOT EXISTS recommendation_mode    TEXT;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE predictions
            DROP COLUMN IF EXISTS psqi_scores,
            DROP COLUMN IF EXISTS psqi_predicted_total,
            DROP COLUMN IF EXISTS recommended_slot_psqi,
            DROP COLUMN IF EXISTS recommendation_mode;
        """
    )
