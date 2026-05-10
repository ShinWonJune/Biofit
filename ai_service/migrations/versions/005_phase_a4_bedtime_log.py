"""Phase A.4 §C2 — bedtime_log 테이블 신규.

PSQI C2(잠복기) 측정 정확도 보강. fitbit의 *첫 wake 단계 누적*을 *침대 누운 시각*으로
근사하던 방식이 floor effect로 baseline 미달이라 (Phase B 검증 결과), 회원 측에서
*직접 입력*한 침대 시각을 박제할 수 있도록 별도 테이블을 둔다.

PSQI C2 산출 우선순위:
    1. bedtime_log에 *그 sleep window*에 박제된 row가 있으면 → 잠복기 = 첫 비-wake 시각 - bedtime_log
    2. 없으면 fallback → sleep_detail의 첫 wake 누적

Revision ID: 005
Revises: 004
Create Date: 2026-05-10
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bedtime_log (
            id          SERIAL PRIMARY KEY,
            user_id     TEXT NOT NULL,
            bedtime_at  TIMESTAMPTZ NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedtime_log_user_time "
        "ON bedtime_log(user_id, bedtime_at);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bedtime_log;")
