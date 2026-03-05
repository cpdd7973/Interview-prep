---
name: observability-stack
description: Grafana dashboard templates, Datadog monitor configurations, structured log pipeline design, distributed tracing setup with OpenTelemetry, and SLO/SLA definitions for interview platforms.
---

# Observability Stack Reference

---

## Three Pillars Strategy

```
METRICS  → "Is something wrong?"      → Datadog / Prometheus + Grafana
LOGS     → "What happened?"           → Datadog Logs / CloudWatch / Loki
TRACES   → "Where did it go wrong?"   → Datadog APM / Jaeger / Tempo

Rule: Never diagnose a production issue with only one pillar.
Alert fires (metrics) → inspect logs → follow traces to root cause.
```

---

## Key Metrics per Service

```python
# Instrument your FastAPI app with these metrics
from prometheus_client import Counter, Histogram, Gauge

# API Service
api_request_total     = Counter("api_requests_total", "...", ["method", "path", "status"])
api_request_duration  = Histogram("api_request_duration_seconds", "...",
                          buckets=[.05, .1, .25, .5, 1, 2.5, 5, 10])
active_sessions       = Gauge("active_sessions_total", "Active interview sessions")

# LLM / Agent
llm_request_duration  = Histogram("llm_duration_seconds", "...", ["model"],
                          buckets=[1, 2, 5, 10, 20, 30, 60])
llm_tokens_used       = Counter("llm_tokens_total", "...", ["direction"])  # input/output
agent_iterations      = Histogram("agent_iterations_total", "...",
                          buckets=[1, 2, 3, 5, 8, 10])

# Worker / Queue
queue_depth           = Gauge("job_queue_depth", "...", ["queue"])
job_duration          = Histogram("job_duration_seconds", "...", ["status"],
                          buckets=[5, 15, 30, 60, 120, 300])
job_retry_count       = Counter("job_retries_total", "...", ["queue"])
dlq_depth             = Gauge("dead_letter_queue_depth", "...", ["queue"])

# Voice
stt_latency           = Histogram("stt_latency_seconds", "...", ["provider"],
                          buckets=[.1, .3, .5, 1, 2, 5])
tts_first_chunk_ms    = Histogram("tts_first_chunk_ms", "...", ["provider"],
                          buckets=[100, 200, 400, 600, 1000])
```

---

## SLO Definitions

```yaml
slos:
  api_availability:
    description: "API responds successfully to valid requests"
    target: 99.9%
    window: 30d
    good_event: "HTTP 2xx or 4xx response"
    bad_event:  "HTTP 5xx response or timeout"
    alert_burn_rate: 14.4x   # 1-hour burn rate alert

  session_evaluation_latency:
    description: "95% of evaluations complete within 3 minutes"
    target: 95%
    window: 7d
    good_event: "Evaluation completed in < 180 seconds"
    bad_event:  "Evaluation took > 180 seconds or failed"

  voice_round_trip:
    description: "P95 voice round-trip under 3 seconds"
    target: 95%
    window: 7d
    measurement: "Time from audio sent → first TTS audio chunk received"
    threshold_ms: 3000
```

---

## Structured Log Format

```python
import structlog, json

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

# Every log entry should have these fields:
# {
#   "timestamp": "2025-02-26T14:00:00.000Z",
#   "level": "info",
#   "event": "session_completed",
#   "session_id": "abc-123",
#   "request_id": "req-xyz",
#   "duration_ms": 1840,
#   "service": "api",
#   "environment": "production"
# }
#
# NEVER log: email, full_name, phone, resume content, transcript content
# ALWAYS log: session_id, request_id, duration_ms, status codes
```

---

## Datadog Alert Templates

```python
# alert_templates.py — generate Datadog monitors via API

ALERTS = [
    {
        "name": "[Interview API] High Error Rate",
        "type": "metric alert",
        "query": "sum(last_5m):sum:trace.fastapi.request.errors{env:production}.as_rate() / sum:trace.fastapi.request.hits{env:production}.as_rate() > 0.05",
        "message": """
## High API Error Rate

Error rate has exceeded 5% for the last 5 minutes.

**Runbook:** https://wiki.internal/runbooks/api-high-error-rate

**Steps:**
1. Check recent deployments: `kubectl rollout history deployment/interview-api`
2. Check logs: `datadog logs search "service:api status:error"`
3. If deployment-related: `helm rollback interview-api`

@pagerduty-P2 @slack-#incidents
        """,
        "thresholds": {"critical": 0.05, "warning": 0.02},
        "priority": 2,
    },
    {
        "name": "[Interview Worker] Queue Depth Critical",
        "type": "metric alert",
        "query": "max(last_10m):avg:job_queue_depth{queue:critical,env:production} > 100",
        "message": """
## Critical Queue Backup

Critical job queue has >100 pending jobs for 10+ minutes.
Candidates are experiencing significant delays.

**Runbook:** https://wiki.internal/runbooks/queue-backup

@pagerduty-P1 @slack-#incidents
        """,
        "thresholds": {"critical": 100, "warning": 50},
        "priority": 1,
    },
]
```

---

## Grafana Dashboard — Interview Operations

```json
{
  "title": "Interview Platform — Operations",
  "panels": [
    {
      "title": "Active Sessions",
      "type": "stat",
      "targets": [{
        "expr": "active_sessions_total{env='production'}"
      }]
    },
    {
      "title": "Session Completion Rate (24h)",
      "type": "gauge",
      "targets": [{
        "expr": "sum(rate(api_requests_total{path='/sessions',status='completed'}[24h])) / sum(rate(api_requests_total{path='/sessions',status=~'completed|cancelled|expired'}[24h])) * 100"
      }],
      "thresholds": [
        {"value": 70, "color": "red"},
        {"value": 85, "color": "yellow"},
        {"value": 95, "color": "green"}
      ]
    },
    {
      "title": "LLM P95 Latency",
      "type": "graph",
      "targets": [{
        "expr": "histogram_quantile(0.95, rate(llm_duration_seconds_bucket[5m]))"
      }]
    },
    {
      "title": "Job Queue Depth by Queue",
      "type": "graph",
      "targets": [
        {"expr": "job_queue_depth{queue='critical'}", "legendFormat": "critical"},
        {"expr": "job_queue_depth{queue='default'}",  "legendFormat": "default"},
        {"expr": "dead_letter_queue_depth",            "legendFormat": "DLQ"}
      ]
    }
  ]
}
```

---

## On-Call Runbook Template

```markdown
# Runbook: [Alert Name]

## Severity: P1 / P2 / P3

## Symptoms
- What the alert fires on
- What users experience

## Immediate Actions (first 5 minutes)
1. Check deployment history: `kubectl rollout history deployment/X`
2. Check error logs: `datadog logs "service:X status:error last:15m"`
3. Check queue depth: `redis-cli llen celery`

## Diagnosis
- If error rate spike after deploy → rollback
- If queue backed up → check worker pods, scale if needed
- If LLM latency high → check Anthropic status page

## Escalation
- After 15min unresolved → escalate to P1
- LLM provider down → enable fallback mode
- Data breach suspected → contact security@company.com immediately

## Post-Incident
- Write post-mortem within 48 hours
- Update this runbook with new learnings
```
