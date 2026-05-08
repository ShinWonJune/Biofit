"""phase3 baseline — empty migration to establish alembic_version

기존 db/init/001~009.sql이 적재한 schema 위에서 alembic_version 테이블만 생성.
Phase 3 이전의 모든 schema는 *db/init/* 가 책임지고, Phase 3 이후의 schema 변화는
*Alembic 마이그레이션*이 담당하는 *expand-contract* 토대.

Revision ID: 001
Revises:
Create Date: 2026-05-08
"""
from alembic import op  # noqa: F401

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Empty baseline — alembic_version 테이블만 자동 생성된다.
    pass


def downgrade() -> None:
    pass
