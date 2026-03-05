---
name: query-optimisation
description: Index design principles, EXPLAIN ANALYZE interpretation, common slow query patterns, connection pooling, and query rewriting techniques for PostgreSQL in hiring application contexts.
---

# Query Optimisation Reference

---

## Reading EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT s.id, e.composite_score
FROM interview_sessions s
JOIN session_evaluations e ON e.session_id = s.id
WHERE s.candidate_id = $1 AND e.status = 'complete'
ORDER BY s.created_at DESC;
```

**Key fields to read:**

| Field | What it means | Bad sign |
|---|---|---|
| `Seq Scan` | Full table scan | On large tables without WHERE |
| `Index Scan` | Uses index | Good |
| `Index Only Scan` | Covered by index, no heap fetch | Best |
| `rows=X (actual rows=Y)` | Planner estimate vs actual | X >> Y = bad stats |
| `Buffers: hit=X read=Y` | Cache hits vs disk reads | High `read` = needs cache warmup |
| `cost=X..Y` | Startup..total cost (arbitrary units) | Relative comparison only |
| `actual time=X..Y ms` | Wall time | Self-explanatory |

---

## Index Design Principles

```sql
-- 1. Index columns you filter on, in selectivity order (most selective first)
-- BAD: index on (status) — only 5 distinct values, low selectivity
-- GOOD: index on (candidate_id, status) — candidate_id is highly selective

-- 2. Include columns you SELECT to enable Index Only Scans
CREATE INDEX idx_sessions_candidate_covering
    ON interview_sessions(candidate_id, created_at DESC)
    INCLUDE (status, role, level);   -- Covered — no heap fetch needed

-- 3. Partial indexes — only index the rows you query
CREATE INDEX idx_sessions_active
    ON interview_sessions(started_at)
    WHERE status = 'active';         -- Only active sessions indexed

-- 4. Expression indexes for computed filters
CREATE INDEX idx_candidates_email_lower
    ON candidates(LOWER(email));     -- Enables: WHERE LOWER(email) = $1
```

---

## Common Slow Queries & Fixes

### N+1 in Session Listing

```sql
-- BAD: N+1 — one query per session to get evaluation
-- This is what ORMs generate by default
SELECT * FROM interview_sessions WHERE candidate_id = $1;
-- Then for each session:
SELECT * FROM session_evaluations WHERE session_id = $session_id;

-- GOOD: Single query with LEFT JOIN
SELECT
    s.id, s.role, s.level, s.status, s.started_at,
    e.composite_score, e.verdict
FROM interview_sessions s
LEFT JOIN LATERAL (
    SELECT composite_score, verdict
    FROM session_evaluations
    WHERE session_id = s.id AND status = 'complete'
    ORDER BY completed_at DESC
    LIMIT 1
) e ON true
WHERE s.candidate_id = $1
ORDER BY s.created_at DESC
LIMIT 20;
```

### Slow Aggregate on Large Table

```sql
-- BAD: Full scan on transcript_turns (could be 100M+ rows)
SELECT COUNT(*) FROM transcript_turns WHERE session_id = $1;

-- GOOD: Maintain a denormalised counter
ALTER TABLE interview_sessions ADD COLUMN turn_count INT NOT NULL DEFAULT 0;

-- Increment on insert (via trigger or application)
UPDATE interview_sessions SET turn_count = turn_count + 1 WHERE id = $1;

-- Now the count is O(1)
SELECT turn_count FROM interview_sessions WHERE id = $1;
```

### Score Distribution Over Time

```sql
-- BAD: Scans entire evaluations table, recalculates on every request
SELECT DATE_TRUNC('day', completed_at), AVG(composite_score)
FROM session_evaluations
WHERE status = 'complete'
GROUP BY 1;

-- GOOD: Materialised view, refreshed hourly
CREATE MATERIALIZED VIEW mv_daily_score_summary AS
SELECT
    DATE_TRUNC('day', e.completed_at)   AS day,
    s.role, s.level,
    COUNT(*)                            AS n,
    AVG(e.composite_score)              AS avg_score,
    PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY e.composite_score)    AS median_score
FROM session_evaluations e
JOIN interview_sessions s ON s.id = e.session_id
WHERE e.status = 'complete'
GROUP BY 1, 2, 3
WITH NO DATA;

CREATE UNIQUE INDEX ON mv_daily_score_summary(day, role, level);

-- Refresh on a schedule
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_score_summary;
```

---

## Connection Pooling

```python
# Always use a connection pool — never open a new connection per request
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,           # Persistent connections
    max_overflow=20,        # Temporary connections during bursts
    pool_timeout=30,        # Wait max 30s for a connection
    pool_recycle=1800,      # Recycle connections every 30min (prevent stale)
    pool_pre_ping=True,     # Test connection before use
)

# For Celery workers — use a separate pool
worker_engine = create_async_engine(
    DATABASE_URL,
    pool_size=3,            # Workers have fewer concurrent DB needs
    max_overflow=5,
)
```

```
PgBouncer sizing (if using as middleware):
  pool_mode = transaction    # Best for async/short queries
  max_client_conn = 1000     # Max app connections to PgBouncer
  default_pool_size = 25     # Connections PgBouncer holds to Postgres

Postgres max_connections should be:
  (num_pgbouncer_instances × default_pool_size) + 10 (admin overhead)
```
