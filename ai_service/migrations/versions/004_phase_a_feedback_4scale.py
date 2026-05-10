"""Phase A.1 §C1 — feedback.sleep_score 3단계(0~1) → 4단계(0~3) 확장

PSQI 4 차원 분리에서 C1(주관적 수면의 질)이 다른 차원(0~3)과 *동일 규모*로 통일되도록
sleep_score CHECK 제약을 갱신한다.

대상: sleep_score 컬럼을 가진 *모든 동적 {uid}_feedback 테이블*. 제약 이름이
PostgreSQL이 자동 부여한 식별자라 직접 알 수 없으므로 DO 블록으로 안전하게 순회.

기존 데이터 정책 (옵션 A): 변경 시점 이전의 0/1 데이터는 그대로 유지하되
*ai_service의 학습에서는 제외*. 0/1 → 4단계 매핑이 정확히 불가능하기 때문.

Revision ID: 004
Revises: 003
Create Date: 2026-05-10
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            tbl text;
            c   text;
        BEGIN
            FOR tbl IN
                SELECT table_name
                FROM information_schema.columns
                WHERE column_name = 'sleep_score'
                  AND table_schema = 'public'
            LOOP
                -- 기존 sleep_score 관련 CHECK 제약 모두 drop
                FOR c IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = format('%I', tbl)::regclass
                      AND contype = 'c'
                      AND pg_get_constraintdef(oid) ILIKE '%sleep_score%'
                LOOP
                    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', tbl, c);
                END LOOP;

                -- 새 0~3 CHECK 추가
                EXECUTE format(
                    'ALTER TABLE %I ADD CONSTRAINT %I CHECK (sleep_score >= 0 AND sleep_score <= 3)',
                    tbl, tbl || '_sleep_score_0_3'
                );
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    """0~1 CHECK으로 복원. *기존 데이터에 2 또는 3 값이 있으면 실패* — 의도된 안전장치."""
    op.execute(
        """
        DO $$
        DECLARE
            tbl text;
            c   text;
        BEGIN
            FOR tbl IN
                SELECT table_name
                FROM information_schema.columns
                WHERE column_name = 'sleep_score'
                  AND table_schema = 'public'
            LOOP
                FOR c IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = format('%I', tbl)::regclass
                      AND contype = 'c'
                      AND pg_get_constraintdef(oid) ILIKE '%sleep_score%'
                LOOP
                    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', tbl, c);
                END LOOP;

                EXECUTE format(
                    'ALTER TABLE %I ADD CONSTRAINT %I CHECK (sleep_score IN (0,1))',
                    tbl, tbl || '_sleep_score_check'
                );
            END LOOP;
        END $$;
        """
    )
