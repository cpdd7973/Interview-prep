---
name: storage-backends
description: Storage backend selection guide for LLM memory systems. Covers when to use Redis, PostgreSQL, vector databases, and in-memory stores for each memory layer — with latency profiles, cost considerations, and failure mode notes.
---

# Storage Backends Reference

Which database for which memory layer — Lena's opinionated guide.

---

## Backend Selection at a Glance

```
MEMORY LAYER          BEST BACKEND              RUNNER-UP
─────────────────────────────────────────────────────────
Working Memory        In-process (dict/list)    Redis (if multi-instance)
Episodic Memory       Vector DB + metadata DB   PostgreSQL + pgvector
Semantic Memory       PostgreSQL / DynamoDB     Redis (for hot profiles)
Session Summaries     PostgreSQL / S3           Redis (TTL-based)
Full Turn Archive     S3 / cold object store    PostgreSQL (small scale)
```

---

## In-Process Memory (Working Memory)

**Use for:** Current session's raw turns. Single-server, single-session scope.

```python
# Simplest possible working memory
class SessionMemory:
    def __init__(self, max_turns: int = 50):
        self.turns: list[dict] = []
        self.max_turns = max_turns

    def add(self, role: str, content: str):
        self.turns.append({"role": role, "content": content})
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]  # Sliding eviction

    def get(self) -> list[dict]:
        return self.turns
```

**Pros:** Zero latency, zero infra, zero cost
**Cons:** Lost on process restart, doesn't scale to multiple instances
**Upgrade trigger:** You need horizontal scaling or session persistence → Redis

---

## Redis (Working Memory at Scale / Session Cache)

**Use for:** Working memory when running multiple server instances, or session data with TTL.

**Key pattern:**
```python
import redis, json

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

SESSION_TTL = 3600  # 1 hour

def get_session(session_id: str) -> list[dict]:
    data = r.get(f"session:{session_id}")
    return json.loads(data) if data else []

def save_session(session_id: str, turns: list[dict]):
    r.setex(
        f"session:{session_id}",
        SESSION_TTL,
        json.dumps(turns)
    )
```

**Latency:** <1ms (local), 1–5ms (cloud Redis)
**Cost:** ~$0.10–0.50/GB/month (ElastiCache / Upstash)
**Failure mode:** Redis goes down → session lost. Mitigate: Redis Sentinel or Cluster, or treat as cache-only and fall back to DB.

**Do NOT use Redis for:** Episodic memory that needs semantic search, or long-term storage — it's expensive per GB and not built for queries.

---

## PostgreSQL (Episodic + Semantic Memory)

**Use for:** Session summaries, user profiles, structured fact stores, turn archives.

**Schema for a complete memory system:**

```sql
-- User semantic memory (facts and preferences)
CREATE TABLE user_memory (
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  FLOAT DEFAULT 1.0,
    source      TEXT,                    -- e.g., "session:abc123, turn 7"
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,             -- NULL = never
    PRIMARY KEY (user_id, key)
);

-- Session episodic summaries
CREATE TABLE session_summaries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    summary     TEXT NOT NULL,
    embedding   VECTOR(1536),            -- pgvector for retrieval
    started_at  TIMESTAMPTZ,
    ended_at    TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON session_summaries USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON session_summaries (user_id, ended_at DESC);

-- Raw turn archive (optional — for compliance/audit)
CREATE TABLE turn_archive (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    token_count INT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
-- Partition by month for large scale
```

**Pros:** ACID, flexible queries, pgvector handles semantic search at moderate scale
**Cons:** Vector search slower than dedicated vector DBs at >10M rows; needs index tuning
**Upgrade trigger:** >5M episodic entries or <50ms retrieval SLA → dedicated vector DB

---

## Vector Databases (Episodic Retrieval at Scale)

**Use for:** Semantic retrieval of past episodes, large-scale episodic memory, similarity-based recall.

### Comparison

| DB | Best For | Latency (p99) | Scale | Managed Option |
|---|---|---|---|---|
| **pgvector** | <5M vectors, existing PG stack | 20–100ms | Moderate | Supabase, Neon |
| **Pinecone** | Managed, fast, no infra | 5–30ms | Very high | Yes (fully) |
| **Weaviate** | Hybrid search (BM25 + dense) | 10–50ms | High | Yes + self-host |
| **Qdrant** | Self-hosted, high perf | 5–20ms | High | Yes + self-host |
| **Chroma** | Local dev, prototyping | Variable | Low | No |

**Lena's pick by stage:**
- Prototype/MVP → pgvector (you already have Postgres)
- Production, managed → Pinecone or Qdrant Cloud
- Production, self-hosted → Qdrant (best perf/cost ratio)
- Need hybrid BM25 + dense → Weaviate

**What goes in the vector DB:**
```python
# Episode record to upsert
{
    "id": "session_abc123_ep2",
    "embedding": embed("User struggled with Redis connection pooling. Resolved by setting max_connections=20."),
    "metadata": {
        "user_id": "u_xyz",
        "session_id": "session_abc123",
        "summary": "User struggled with Redis connection pooling...",
        "timestamp": "2025-02-26T14:00:00Z",
        "topic_tags": ["redis", "connection-pooling", "debugging"]
    }
}
```

**Retrieval query:**
```python
def retrieve_relevant_episodes(
    user_id: str,
    query: str,
    top_k: int = 3,
    max_age_days: int = 90
) -> list[dict]:
    query_embedding = embed(query)
    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()

    results = vector_db.query(
        vector=query_embedding,
        top_k=top_k,
        filter={
            "user_id": {"$eq": user_id},
            "timestamp": {"$gte": cutoff}
        },
        include_metadata=True
    )
    return [r.metadata for r in results.matches]
```

**Common mistake:** Querying the vector DB with the raw user message as the query.
Better: Rewrite the query to be more retrieval-friendly first.
```python
retrieval_query = call_llm(
    f"Rewrite this as a search query for retrieving relevant past conversations: {user_message}"
)
```

---

## S3 / Object Storage (Turn Archives + Cold Memory)

**Use for:** Raw turn archives you need for compliance/audit but never query directly. Long-term episodic storage at low cost.

**Pattern:**
```python
# Archive a session after it ends (async, background job)
def archive_session(session_id: str, turns: list[dict], user_id: str):
    key = f"archives/{user_id}/{session_id}.json"
    s3.put_object(
        Bucket="my-memory-archive",
        Key=key,
        Body=json.dumps({
            "session_id": session_id,
            "user_id": user_id,
            "archived_at": datetime.now().isoformat(),
            "turns": turns
        }),
        StorageClass="INTELLIGENT_TIERING"   # Auto-tiers to cold after 30 days
    )
```

**Cost:** ~$0.023/GB/month (S3 Standard), ~$0.004/GB/month (Glacier)
**Use INTELLIGENT_TIERING** — old archives automatically move to cheaper storage classes.
**Never query S3 for retrieval** — always index into a vector DB or Postgres alongside archival.

---

## Multi-Backend Architecture (Production Pattern)

```
┌──────────────────────────────────────────────────────┐
│                    REQUEST PATH                      │
│                                                      │
│  Redis ──────────────── Working memory (hot)         │
│  PostgreSQL ─────────── User profiles, summaries     │
│  Qdrant ─────────────── Episodic semantic retrieval  │
│  S3 ──────────────────── Raw turn archive (cold)     │
└──────────────────────────────────────────────────────┘

WRITE PATH (async, post-response):
  Turn appended → Redis (sync, immediate)
  Session ended → Summarize → Postgres + Qdrant (async)
  Session ended → Archive raw → S3 (async, low priority)
  Facts extracted → Postgres user_memory (async)

READ PATH (sync, pre-request):
  Redis → working memory (always)
  Postgres → user profile (always, <5ms)
  Qdrant → relevant episodes (when query warrants it, <30ms)
```

**Key principle:** All writes except Redis are async. The user never waits for memory persistence.
**Key principle:** Keep read path under 50ms total. Budget each store's contribution.

---

## Retention & Deletion Policy Template

Every production memory system needs answers to these before launch:

```
Working memory:     Auto-expire after session ends (Redis TTL)
Session summaries:  Retain 12 months, then delete or anonymize
User facts:         Retain until user requests deletion
Raw turn archive:   Retain 30 days (operational) → Glacier (compliance)
                    Permanently delete after [X] years per policy

User deletion request (GDPR / right to erasure):
  □ Delete Redis session keys
  □ Delete Postgres rows (user_memory WHERE user_id = ?)
  □ Delete Postgres session_summaries
  □ Delete Qdrant vectors (filter by user_id)
  □ Delete or anonymize S3 archives
  □ Log deletion event with timestamp
```

**Lena's warning:** If you haven't answered these questions before your first production user,
you'll be answering them under pressure when your first deletion request arrives.
That is not when you want to discover your vector DB doesn't support filtered deletes.
