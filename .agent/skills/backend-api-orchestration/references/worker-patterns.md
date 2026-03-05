---
name: worker-patterns
description: Worker scaling, priority queues, job progress reporting, distributed locking, and observability patterns for Celery (Python) and BullMQ (Node.js) in LLM-powered application backends.
---

# Worker Patterns Reference

Production patterns for async job workers handling LLM tasks.

---

## Worker Scaling Strategy

### Capacity Planning

```
LLM task characteristics:
  Average duration:   15–45 seconds (varies by model + prompt)
  CPU usage:          Low (waiting on LLM API)
  Memory per worker:  ~100–300MB (Python), ~50–150MB (Node.js)
  Network:            High (streaming tokens)

Concurrency per worker process:
  Python (Celery):   3–5 tasks (I/O-bound — async or threaded)
  Node.js (BullMQ):  5–10 tasks (event loop handles I/O natively)

Formula for worker count:
  target_throughput = jobs_per_minute
  avg_duration_min  = 0.5  (30s average)
  concurrency       = 5
  workers_needed    = ceil(target_throughput * avg_duration_min / concurrency)

  Example: 60 jobs/min, 30s avg, concurrency=5
  → ceil(60 * 0.5 / 5) = ceil(6) = 6 worker processes
```

### Celery Worker Configuration

```python
# celery_config.py
from kombu import Queue

# Priority queues — critical interview jobs jump the queue
CELERY_TASK_QUEUES = (
    Queue("critical", routing_key="critical"),   # Active session messages
    Queue("default",  routing_key="default"),    # Standard processing
    Queue("low",      routing_key="low"),         # Batch eval, archiving
)

CELERY_TASK_DEFAULT_QUEUE   = "default"
CELERY_TASK_DEFAULT_ROUTING_KEY = "default"

CELERY_TASK_ROUTES = {
    "process_candidate_message": {"queue": "critical"},
    "evaluate_session":          {"queue": "default"},
    "archive_transcript":        {"queue": "low"},
}

# Worker startup command — different queues on different workers
# High-priority worker:
# celery -A app worker -Q critical,default --concurrency=3 --loglevel=info
#
# Low-priority worker:
# celery -A app worker -Q default,low --concurrency=5 --loglevel=info
```

### BullMQ Priority Queues

```typescript
// Producer — assign priority (1=highest, 10=lowest)
await messageQueue.add(
  'processMessage',
  { sessionId, content },
  {
    priority: isActiveSession ? 1 : 5,
    attempts: 3,
    backoff: { type: 'exponential', delay: 2000 },
  }
)

// Separate queues for different workloads
export const criticalQueue = new Queue('critical-messages', { connection })
export const defaultQueue  = new Queue('default-messages', { connection })
export const lowQueue      = new Queue('low-priority', { connection })

// Worker that drains critical first, then falls back
const worker = new Worker(
  'critical-messages',
  processor,
  { connection, concurrency: 5 }
)
```

---

## Job Progress Reporting

Clients need to know where their job is — not just "processing."

```python
# Celery — granular progress updates
from celery import current_task

@celery_app.task(bind=True, name="process_candidate_message")
def process_candidate_message(self, session_id: str, content: str):
    def update(pct: int, message: str):
        self.update_state(
            state="PROGRESS",
            meta={"percent": pct, "message": message, "session_id": session_id}
        )

    update(5,  "Retrieving session context...")
    history = get_history_sync(session_id)

    update(15, "Starting LLM processing...")
    # Note: Use a sync wrapper for async agent loop in Celery
    result = run_sync(run_agent_loop(
        session_id=session_id,
        user_message=content,
        conversation_history=history,
        on_progress=lambda pct: update(15 + int(pct * 0.8), "Generating response..."),
    ))

    update(95, "Saving transcript...")
    save_message_sync(session_id, "assistant", result)

    update(100, "Complete")
    return {"status": "complete", "session_id": session_id}


# Polling endpoint — map Celery states to clean API responses
@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    result = AsyncResult(job_id, app=celery_app)

    state_map = {
        "PENDING":  {"status": "queued",     "percent": 0},
        "STARTED":  {"status": "processing", "percent": 5},
        "PROGRESS": {"status": "processing", "percent": result.info.get("percent", 0)},
        "SUCCESS":  {"status": "complete",   "percent": 100},
        "FAILURE":  {"status": "failed",     "percent": 0},
        "REVOKED":  {"status": "cancelled",  "percent": 0},
    }

    mapped = state_map.get(result.state, {"status": "unknown", "percent": 0})

    return {
        "job_id":  job_id,
        "status":  mapped["status"],
        "percent": mapped["percent"],
        "message": result.info.get("message") if isinstance(result.info, dict) else None,
        "result":  result.result if result.successful() else None,
        "error":   str(result.info) if result.failed() else None,
    }
```

```typescript
// BullMQ — progress with typed metadata
interface JobProgress {
  percent: number
  message: string
}

const worker = new Worker('interview-messages', async (job: Job) => {
  const progress = async (percent: number, message: string) => {
    await job.updateProgress({ percent, message } satisfies JobProgress)
  }

  await progress(5, 'Retrieving session context...')
  const history = await sessionStore.getHistory(job.data.sessionId)

  await progress(15, 'Starting LLM processing...')
  const result = await runAgentLoop({
    ...job.data,
    conversationHistory: history,
    onProgress: async (pct) => {
      await progress(15 + Math.floor(pct * 0.8), 'Generating response...')
    },
  })

  await progress(95, 'Saving transcript...')
  await sessionStore.appendMessage(job.data.sessionId, 'assistant', result)

  await progress(100, 'Complete')
  return { status: 'complete', sessionId: job.data.sessionId }
}, { connection, concurrency: 5 })


// Status endpoint with typed progress
app.get('/jobs/:jobId', async (request, reply) => {
  const job = await messageQueue.getJob(request.params.jobId)
  if (!job) return reply.code(404).send({ error: 'Job not found' })

  const state    = await job.getState()
  const progress = job.progress as JobProgress | number | undefined

  return {
    jobId:   job.id,
    status:  state,
    percent: typeof progress === 'object' ? progress.percent : progress ?? 0,
    message: typeof progress === 'object' ? progress.message : null,
    result:  state === 'completed' ? job.returnvalue : null,
    error:   state === 'failed'    ? job.failedReason : null,
  }
})
```

---

## Distributed Locking

Prevent duplicate processing when a client retries and the original job is still running.

```python
import redis.asyncio as aioredis
from contextlib import asynccontextmanager

@asynccontextmanager
async def distributed_lock(key: str, ttl_seconds: int = 60):
    """
    Redis-based distributed lock using SET NX EX.
    Prevents duplicate job execution across workers.
    """
    lock_key = f"lock:{key}"
    lock_value = str(uuid.uuid4())  # Unique value to prevent stealing

    acquired = await redis.set(
        lock_key, lock_value,
        nx=True,   # Only set if not exists
        ex=ttl_seconds,
    )

    if not acquired:
        raise LockAcquisitionError(f"Could not acquire lock for {key}")

    try:
        yield
    finally:
        # Only release if we still own the lock (Lua script for atomicity)
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        await redis.eval(lua_script, 1, lock_key, lock_value)


# Usage in job processor
async def process_message_safe(session_id: str, message_id: str, content: str):
    lock_key = f"session:{session_id}:message:{message_id}"
    try:
        async with distributed_lock(lock_key, ttl_seconds=90):
            await run_agent_loop(session_id=session_id, user_message=content, ...)
    except LockAcquisitionError:
        logger.info(f"Duplicate job skipped: {lock_key}")
        # This message is already being processed — idempotent skip
```

---

## Dead Letter Queue Handling

```python
# Celery — catch and route permanently failed tasks
from celery.signals import task_failure

@task_failure.connect
def handle_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    **other,
):
    # Only handle tasks that have exhausted all retries
    task_result = AsyncResult(task_id)
    if task_result.info and hasattr(task_result.info, 'retries'):
        if task_result.info.retries < sender.max_retries:
            return  # Still retrying — don't DLQ yet

    session_id = kwargs.get("session_id") or (args[0] if args else None)

    # Archive to dead letter store
    redis.lpush("dead_letter_queue", json.dumps({
        "task_id":    task_id,
        "task_name":  sender.name,
        "session_id": session_id,
        "args":       args,
        "kwargs":     kwargs,
        "error":      str(exception),
        "failed_at":  datetime.now(timezone.utc).isoformat(),
    }))

    # Alert the client session
    if session_id:
        asyncio.run(publish_error(
            session_id,
            "We encountered an error processing your response. Please try again."
        ))

    # Alert ops (PagerDuty / Slack / etc.)
    notify_ops(
        severity="warning",
        message=f"Job permanently failed: {sender.name} for session {session_id}",
        details={"task_id": task_id, "error": str(exception)},
    )
```

```typescript
// BullMQ — dead letter queue with alerting
worker.on('failed', async (job: Job | undefined, error: Error) => {
  if (!job) return

  const maxAttempts = job.opts.attempts ?? 3
  if (job.attemptsMade < maxAttempts) return  // Still has retries left

  // Permanently failed — archive
  await deadLetterQueue.add('failed-job', {
    originalJobId:   job.id,
    taskName:        job.name,
    sessionId:       job.data.sessionId,
    payload:         job.data,
    error:           error.message,
    stack:           error.stack,
    failedAt:        new Date().toISOString(),
    attemptsMade:    job.attemptsMade,
  })

  // Notify client
  await redisPublisher.publish(
    `session:${job.data.sessionId}:events`,
    JSON.stringify({
      type: 'error',
      code: 'JOB_FAILED',
      message: 'Processing failed. Please try again.',
    })
  )

  // Alert ops
  await alertOps({
    severity: 'warning',
    title: `Job permanently failed: ${job.name}`,
    sessionId: job.data.sessionId,
    error: error.message,
  })
})
```

---

## Observability

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

# Bind context that flows through all log calls
def get_request_logger(request: Request) -> structlog.BoundLogger:
    return logger.bind(
        request_id=request.state.request_id,
        session_id=request.headers.get("X-Session-Id"),
        method=request.method,
        path=request.url.path,
    )

# In job handler
task_logger = logger.bind(
    task_id=self.request.id,
    task_name=self.name,
    session_id=session_id,
)
task_logger.info("task_started")
# ... processing ...
task_logger.info("task_complete", duration_ms=duration_ms, tokens_generated=token_count)
```

### Key Metrics to Track

```python
# Prometheus metrics for the interview API
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# LLM metrics
llm_request_duration = Histogram(
    "llm_request_duration_seconds",
    "LLM API call duration",
    ["model", "endpoint"],
    buckets=[1, 2, 5, 10, 20, 30, 60]
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens consumed",
    ["model", "direction"]   # direction: input | output
)

# Job queue metrics
jobs_queued_total    = Counter("jobs_queued_total", "Jobs added to queue", ["queue"])
jobs_completed_total = Counter("jobs_completed_total", "Jobs completed", ["queue", "status"])
jobs_queue_depth     = Gauge("jobs_queue_depth", "Current queue depth", ["queue"])

# Session metrics
active_sessions    = Gauge("active_sessions_total", "Currently active sessions")
session_duration   = Histogram(
    "session_duration_seconds",
    "Interview session duration",
    buckets=[300, 600, 900, 1800, 2700, 3600]
)

# WebSocket metrics
ws_connections_active = Gauge("websocket_connections_active", "Active WS connections")
```

### Distributed Tracing (OpenTelemetry)

```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor

# Auto-instrument — captures HTTP, Redis, and Celery spans automatically
FastAPIInstrumentor.instrument_app(app)
RedisInstrumentor().instrument()
CeleryInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

# Manual span for LLM calls (not auto-instrumented)
async def run_llm_call(messages: list[dict], session_id: str) -> str:
    with tracer.start_as_current_span("llm.chat_completion") as span:
        span.set_attribute("session.id", session_id)
        span.set_attribute("llm.model", "claude-sonnet-4-6")
        span.set_attribute("llm.message_count", len(messages))

        result = await anthropic_client.messages.create(...)

        span.set_attribute("llm.input_tokens", result.usage.input_tokens)
        span.set_attribute("llm.output_tokens", result.usage.output_tokens)
        return result.content[0].text
```

---

## Environment Configuration

```python
# settings.py — Pydantic BaseSettings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    environment:         str = "development"
    debug:               bool = False
    secret_key:          str  # Required — no default

    # Database
    database_url:        str
    redis_url:           str = "redis://localhost:6379/0"

    # LLM
    anthropic_api_key:   str
    llm_model:           str = "claude-sonnet-4-6"
    llm_timeout_seconds: int = 120

    # Queue
    celery_broker_url:   str = "redis://localhost:6379/0"
    celery_backend_url:  str = "redis://localhost:6379/1"
    worker_concurrency:  int = 3

    # Session
    session_ttl_minutes: int = 150   # 2.5 hours (45 min interview + buffer)
    max_sessions_per_key: int = 10

    # Rate limits
    messages_per_minute: int = 20
    sessions_per_hour:   int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

```bash
# .env.example — commit this, not .env
ENVIRONMENT=production
SECRET_KEY=          # Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/interview_db
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=   # From https://console.anthropic.com
LLM_MODEL=claude-sonnet-4-6
WORKER_CONCURRENCY=3
SESSION_TTL_MINUTES=150
```
