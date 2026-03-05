---
name: schema-migrations
description: Zero-downtime migration patterns, expand/contract methodology, backfill strategies, index creation without locking, and Alembic/Flyway migration templates for PostgreSQL.
---

# Schema Migrations Reference

Zero-downtime migration is the only kind acceptable in production.

---

## The Expand/Contract Pattern

Never make breaking schema changes in one step. Always: expand → migrate → contract.

```
STEP 1 — EXPAND (deploy safely, old code still works)
  Add new column as nullable
  Add new table
  Add new index CONCURRENTLY

STEP 2 — MIGRATE (backfill data, dual-write in application)
  Backfill existing rows
  Application writes to both old and new column

STEP 3 — CONTRACT (after all instances use new column)
  Drop old column
  Add NOT NULL constraint to new column
  Remove dual-write from application
```

---

## Adding a Column Without Downtime

```sql
-- STEP 1: Add nullable column (fast, no lock)
ALTER TABLE interview_sessions
    ADD COLUMN question_count INT;

-- STEP 2: Backfill in batches (never UPDATE all rows at once)
DO $$
DECLARE
    batch_size INT := 1000;
    last_id UUID := '00000000-0000-0000-0000-000000000000';
    updated INT;
BEGIN
    LOOP
        WITH batch AS (
            SELECT id FROM interview_sessions
            WHERE id > last_id
              AND question_count IS NULL
            ORDER BY id
            LIMIT batch_size
            FOR UPDATE SKIP LOCKED
        )
        UPDATE interview_sessions s
        SET question_count = (
            SELECT COUNT(*) FROM transcript_turns t
            WHERE t.session_id = s.id AND t.role = 'interviewer'
        )
        FROM batch
        WHERE s.id = batch.id
        RETURNING s.id INTO last_id;

        GET DIAGNOSTICS updated = ROW_COUNT;
        EXIT WHEN updated < batch_size;

        PERFORM pg_sleep(0.05);  -- Yield to other queries between batches
    END LOOP;
END $$;

-- STEP 3: Add NOT NULL after all rows are populated (fast if no nulls exist)
ALTER TABLE interview_sessions
    ALTER COLUMN question_count SET NOT NULL,
    ALTER COLUMN question_count SET DEFAULT 0;
```

---

## Creating Indexes Without Locking

```sql
-- WRONG — locks the table, blocks all reads and writes
CREATE INDEX idx_sessions_completed ON interview_sessions(completed_at);

-- RIGHT — non-blocking, takes longer but safe for production
CREATE INDEX CONCURRENTLY idx_sessions_completed
    ON interview_sessions(completed_at DESC)
    WHERE status = 'completed';

-- Partial indexes are smaller and faster — always add WHERE if applicable
```

---

## Alembic Migration Template (Python)

```python
# migrations/versions/0012_add_question_count.py
"""Add question_count to interview_sessions

Revision ID: 0012
Revises: 0011
Create Date: 2025-02-01
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'

def upgrade():
    # Step 1: Add nullable
    op.add_column('interview_sessions',
        sa.Column('question_count', sa.Integer(), nullable=True))

    # Step 2: Backfill (run via separate script for large tables)
    op.execute("""
        UPDATE interview_sessions s
        SET question_count = (
            SELECT COUNT(*) FROM transcript_turns t
            WHERE t.session_id = s.id AND t.role = 'interviewer'
        )
        WHERE question_count IS NULL
    """)

    # Step 3: Enforce constraint
    op.alter_column('interview_sessions', 'question_count', nullable=False,
                    server_default='0')

    # Create index concurrently (must be outside transaction)
    op.execute('COMMIT')
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_question_count
        ON interview_sessions(question_count)
        WHERE status = 'completed'
    """)

def downgrade():
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_sessions_question_count')
    op.drop_column('interview_sessions', 'question_count')
```

---

## Renaming a Column (Safe Pattern)

```sql
-- NEVER: ALTER TABLE t RENAME COLUMN old TO new  (breaks running app instances)

-- SAFE PATTERN:
-- Step 1: Add new column
ALTER TABLE candidates ADD COLUMN display_name TEXT;

-- Step 2: Sync via trigger
CREATE OR REPLACE FUNCTION sync_display_name()
RETURNS TRIGGER AS $$
BEGIN
    NEW.display_name = NEW.full_name;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sync_display_name_trigger
    BEFORE INSERT OR UPDATE ON candidates
    FOR EACH ROW EXECUTE FUNCTION sync_display_name();

-- Step 3: Backfill
UPDATE candidates SET display_name = full_name WHERE display_name IS NULL;

-- Step 4: After all app instances use new column name:
DROP TRIGGER sync_display_name_trigger ON candidates;
DROP FUNCTION sync_display_name();
ALTER TABLE candidates DROP COLUMN full_name;
```

---

## Partition Management

```sql
-- Automate monthly partition creation with pg_partman
SELECT partman.create_parent(
    p_parent_table  => 'public.transcript_turns',
    p_control       => 'created_at',
    p_type          => 'range',
    p_interval      => 'monthly',
    p_premake       => 3            -- Pre-create 3 future partitions
);

-- Configure retention (drop partitions older than 24 months)
UPDATE partman.part_config
SET retention = '24 months',
    retention_keep_table = false
WHERE parent_table = 'public.transcript_turns';

-- Run maintenance (schedule this via cron or pg_cron)
SELECT partman.run_maintenance();
```

---

## Migration Checklist

```
Before every migration:
  □ Tested on a production-size copy of the database
  □ Estimated lock duration (ALTER TABLE, CREATE INDEX)
  □ Backfill script tested on subset before full run
  □ Rollback migration written and tested
  □ Maintenance window scheduled if any locking DDL

For large table operations (>10M rows):
  □ Use CONCURRENTLY for all index operations
  □ Backfill in batches of 1000-5000 rows
  □ Add pg_sleep between batches
  □ Monitor replication lag during backfill
  □ Verify no long-running queries before starting
```
