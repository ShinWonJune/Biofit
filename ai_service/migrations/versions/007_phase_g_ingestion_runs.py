"""Phase G.1 — ingestion_runs 테이블 신규.

data_service의 데이터 수집 작업 진행 상태를 박제. ai_service의 model_runs와
같은 형태의 *작업 상태 머신*. 클라이언트(streamlit)가 GET endpoint로 *어디까지
진행됐는지* 조회 가능 — 진행 상태가 더 이상 클라이언트 메모리에만 의존하지 않음.

Revision ID: 007
Revises: 006
Create Date: 2026-05-10
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_runs (
            run_id          UUID PRIMARY KEY,
            user_id         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'queued',
            current_step    TEXT,
            started_at      TIMESTAMPTZ DEFAULT NOW(),
            finished_at     TIMESTAMPTZ,
            date_start      DATE,
            date_end        DATE,
            row_count       INT,
            error_message   TEXT
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_runs_user ON ingestion_runs(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status ON ingestion_runs(status);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_runs;")
