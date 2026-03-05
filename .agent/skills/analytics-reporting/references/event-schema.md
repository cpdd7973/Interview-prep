---
name: event-schema
description: Full analytics event tracking plan, event schema definitions, dbt model templates, and data warehouse table designs for interview platform analytics.
---

# Event Schema Reference

---

## Tracking Plan

Every user action and system event that matters for analytics.

```yaml
events:
  session_created:
    properties: [session_id, candidate_id, role, level, input_mode, recruiter_id]
    trigger: POST /sessions succeeds

  session_started:
    properties: [session_id, started_at, scheduled_delay_mins]
    trigger: Candidate sends first message

  session_completed:
    properties: [session_id, duration_secs, turn_count, input_mode_used]
    trigger: Session status → completed

  session_abandoned:
    properties: [session_id, abandonment_phase, turns_completed, reason]
    trigger: Session expires without completion

  message_sent:
    properties: [session_id, turn_index, role, input_mode, content_tokens, latency_ms]
    trigger: Each transcript turn

  evaluation_completed:
    properties: [session_id, evaluation_id, composite_score, verdict, evaluator_version, duration_ms]
    trigger: Evaluation pipeline completes

  human_override:
    properties: [evaluation_id, original_verdict, new_verdict, reviewer_id, reason]
    trigger: Recruiter changes automated verdict
```

---

## Database Event Table

```sql
CREATE TABLE analytics_events (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name  TEXT        NOT NULL,
    session_id  UUID,
    user_id     UUID,
    properties  JSONB       NOT NULL DEFAULT '{}',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (occurred_at);

CREATE INDEX idx_events_name_time
    ON analytics_events(event_name, occurred_at DESC);
CREATE INDEX idx_events_session
    ON analytics_events(session_id, occurred_at DESC)
    WHERE session_id IS NOT NULL;
CREATE INDEX idx_events_props
    ON analytics_events USING GIN (properties);
```

---

## dbt Model Templates

```sql
-- models/marts/hiring/fct_interview_outcomes.sql
SELECT
    s.id                                AS session_id,
    s.candidate_id,
    s.role,
    s.level,
    s.status,
    s.started_at,
    s.completed_at,
    s.duration_secs,
    e.composite_score,
    e.verdict,
    e.evaluator_version,
    CASE
        WHEN e.verdict = 'PASS' THEN 1
        WHEN e.verdict = 'FAIL' THEN 0
        ELSE NULL
    END                                 AS is_pass,
    -- Cohort week for trend analysis
    DATE_TRUNC('week', s.created_at)    AS cohort_week,
    -- Time to evaluation SLA
    EXTRACT(EPOCH FROM (e.completed_at - s.completed_at))
                                        AS time_to_eval_secs
FROM {{ ref('stg_interview_sessions') }} s
LEFT JOIN {{ ref('stg_session_evaluations') }} e
    ON e.session_id = s.id
    AND e.status = 'complete'
    AND e.evaluator_type = 'llm'
```

---

## Grafana Dashboard Variables

```json
{
  "templating": {
    "list": [
      {
        "name": "role",
        "type": "query",
        "query": "SELECT DISTINCT role FROM interview_sessions ORDER BY role",
        "includeAll": true
      },
      {
        "name": "level",
        "type": "custom",
        "options": ["All", "L3", "L4", "L5", "L6", "L7"]
      },
      {
        "name": "period",
        "type": "interval",
        "options": ["7d", "30d", "90d", "6m"]
      }
    ]
  }
}
```
