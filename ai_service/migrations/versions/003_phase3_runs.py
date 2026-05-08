"""phase3 §9.6: model_runs 상태 머신 + idempotency_log

분석 문서 §9.6 — vLLM timeout 시 토큰만 소비되고 predictions가 누락되는 정합성
문제, 같은 입력으로 두 번 호출 시 중복 처리 방지.

- model_runs: 추론의 단계별 상태(queued → running → llm_calling → succeeded/failed)
- idempotency_log: Idempotency-Key 헤더의 멱등 처리. 같은 키로 재호출 시 기존 응답 반환

Revision ID: 003
Revises: 002
Create Date: 2026-05-08
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_runs (
            run_id        UUID PRIMARY KEY,
            uid           TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'queued',
            current_step  TEXT,
            started_at    TIMESTAMPTZ DEFAULT NOW(),
            finished_at   TIMESTAMPTZ,
            error         TEXT,
            retry_count   INT DEFAULT 0
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_status ON model_runs(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_uid    ON model_runs(uid);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS idempotency_log (
            key            TEXT PRIMARY KEY,
            run_id         UUID,
            response_body  JSONB NOT NULL,
            created_at     TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    # 7일 후 정리 cron이 사용할 인덱스
    op.execute("CREATE INDEX IF NOT EXISTS idx_idemp_created_at ON idempotency_log(created_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_idemp_created_at;")
    op.execute("DROP TABLE IF EXISTS idempotency_log;")
    op.execute("DROP INDEX IF EXISTS idx_model_runs_uid;")
    op.execute("DROP INDEX IF EXISTS idx_model_runs_status;")
    op.execute("DROP TABLE IF EXISTS model_runs;")
