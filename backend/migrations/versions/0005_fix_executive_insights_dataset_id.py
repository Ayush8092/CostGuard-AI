"""Repair executive_insights.dataset_id column type from VARCHAR to UUID.

Root cause: migration 0004 used CREATE TABLE IF NOT EXISTS, so when the
table already existed with dataset_id as VARCHAR(36), PostgreSQL skipped
creation and left the wrong column type. SQLAlchemy then compares
UUID = VARCHAR which PostgreSQL rejects with "operator does not exist".

This migration does exactly one thing:
  If executive_insights.dataset_id is VARCHAR or TEXT, convert it to UUID.
  If it is already UUID, do nothing.
  If the column does not exist, raise — that is a serious schema problem
  that 0004 should have caught and this migration must not silently mask.

Revision ID: 0005_fix_executive_insights_dataset_id
Revises: 0004_add_missing_columns
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_fix_dataset_id"
down_revision = "0004_add_missing_columns"
branch_labels = None
depends_on = None


def _convert_uuid_column_if_needed(table: str, column: str) -> None:
    """
    Convert a UUID column from VARCHAR/TEXT to the native UUID type.

    Behaviour by current column state:
      - Already UUID        → do nothing (idempotent, safe on fresh DBs)
      - VARCHAR or TEXT     → ALTER COLUMN ... TYPE UUID USING col::uuid
                              Existing string values are preserved because
                              they were always valid UUID strings from
                              Python's uuid.uuid4().
      - Column missing      → raise immediately. Something is seriously
                              wrong that 0004 should have fixed. Do not
                              silently create columns with missing
                              constraints, indexes, and FK definitions.
      - Any other type      → raise. An INTEGER or BOOLEAN column named
                              dataset_id is not something this migration
                              should touch; it indicates a deeper problem.
    """
    op.execute(sa.text(f"""
        DO $$
        DECLARE
            col_type TEXT;
        BEGIN
            SELECT data_type
            INTO col_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = '{table}'
              AND column_name  = '{column}';

            IF col_type IS NULL THEN
                RAISE EXCEPTION
                    'Column {table}.{column} does not exist. '
                    'Run migration 0004 first to recover missing columns.';

            ELSIF col_type IN ('character varying', 'text') THEN
                ALTER TABLE {table}
                    ALTER COLUMN {column} TYPE UUID
                    USING {column}::uuid;

            ELSIF col_type = 'uuid' THEN
                -- Already correct, nothing to do.
                NULL;

            ELSE
                RAISE EXCEPTION
                    'Column {table}.{column} has unexpected type "%". '
                    'Expected uuid, character varying, or text. '
                    'This migration will not attempt a conversion.',
                    col_type;
            END IF;
        END $$;
    """))


def upgrade() -> None:
    # The only verified broken column: executive_insights.dataset_id.
    # All other tables were created correctly in 0001/0004 as UUID.
    # Do not speculatively repair tables that have not been confirmed broken.
    _convert_uuid_column_if_needed("executive_insights", "dataset_id")


def downgrade() -> None:
    # Type conversions from UUID back to VARCHAR are not reversible without
    # knowing the original precision and constraints. Schema repair migrations
    # intentionally do not implement downgrade.
    pass