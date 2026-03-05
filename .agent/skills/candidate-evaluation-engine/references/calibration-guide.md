---
name: calibration-guide
description: Step-by-step calibration methodology for LLM-based candidate evaluation pipelines. Covers anchor set construction, inter-rater reliability measurement, threshold tuning, drift detection, and human-in-the-loop audit workflows.
---

# Calibration Guide

How to know your evaluator is actually working — and how to fix it when it isn't.

---

## Why Calibration Is Non-Negotiable

An uncalibrated LLM evaluator will:
- Score the same answer differently on different runs (inconsistency)
- Drift over model version changes (silent regression)
- Apply rubric dimensions unevenly (some dimensions over-trusted)
- Be impossible to defend when a hiring decision is challenged

Calibration turns your evaluator from a black box into a measurable system.

---

## Step 1: Build Your Anchor Set

An anchor set is a collection of hand-scored question-answer pairs that represent
known ground truth. Your evaluator must reproduce these scores reliably.

### Anchor Set Requirements

Per question type (behavioral / technical), build:
- **4 anchor answers per question** — one at each score level (1, 2, 3, 4)
- **Minimum 3 questions** per type in your initial set
- **Total: 12 anchors per question type** before going to production

### Anchor Answer Templates

**Score 4 — Behavioral (Exceptional)**
```
Question: "Tell me about a time you resolved a production incident under pressure."

Answer: "In Q3 last year, I was on-call when our payment service started timing out — 
about 40% of transactions were failing. I immediately joined the incident channel, 
pulled the error logs, and identified that a database connection pool had been exhausted 
after a config change was pushed without load testing. I made the call to roll back the 
config within 8 minutes of the alert firing — even though the engineer who pushed it 
pushed back. We restored to 99.9% success rate within 12 minutes. I then led the 
post-mortem, and we added mandatory load test gates to our deploy pipeline as a result. 
That gate has caught two similar issues since."

Expected scores: star=4, specificity=4, ownership=4, impact=4, communication=4
```

**Score 2 — Behavioral (Developing)**
```
Question: "Tell me about a time you resolved a production incident under pressure."

Answer: "Yeah, we had an incident once where our service was down. The team got together 
and we worked through it. I was helping debug and we eventually figured out what the 
problem was and fixed it. It was stressful but we got it done and things were back to 
normal pretty quickly. I learned a lot from it about working under pressure."

Expected scores: star=2, specificity=1, ownership=2, impact=2, communication=2
```

### Anchor Construction Process

1. Write the answer yourself or recruit senior engineers to write calibration answers
2. Have 2-3 senior engineers independently score each anchor using the rubric (no LLM yet)
3. Resolve disagreements — if two engineers can't agree on a score, the rubric needs clarification
4. Lock the anchor set — treat it as immutable ground truth

---

## Step 2: Run Consistency Tests

Before any calibration, measure raw consistency. Your evaluator should produce
the same score on the same input across multiple runs.

```python
def run_consistency_test(
    evaluator_fn,
    anchor_set: list[dict],
    n_runs: int = 5
) -> dict:
    """
    Run each anchor through the evaluator n_runs times.
    Flag any dimension where scores vary by more than 1 point.
    """
    results = {}

    for anchor in anchor_set:
        anchor_id = anchor["id"]
        runs = [evaluator_fn(anchor["question"], anchor["answer"]) for _ in range(n_runs)]

        dim_variance = {}
        for dim in anchor["expected_scores"]:
            scores = [
                next(ds["score"] for ds in r["dimension_scores"] if ds["dimension"] == dim)
                for r in runs
            ]
            dim_variance[dim] = {
                "scores": scores,
                "mean": sum(scores) / len(scores),
                "variance": max(scores) - min(scores),
                "stable": (max(scores) - min(scores)) <= 1
            }

        results[anchor_id] = dim_variance

    # Summary
    unstable_dims = [
        (aid, dim)
        for aid, dims in results.items()
        for dim, v in dims.items()
        if not v["stable"]
    ]

    return {
        "per_anchor": results,
        "unstable_dimensions": unstable_dims,
        "consistency_rate": 1 - (len(unstable_dims) / (len(anchor_set) * len(anchor["expected_scores"]))),
        "ready_for_calibration": len(unstable_dims) == 0
    }
```

**Target:** 100% stable dimensions (variance ≤ 1 across 5 runs) before moving to accuracy testing.
**If failing:** Tighten rubric language. Ambiguous anchors in the prompt cause score variance.

---

## Step 3: Measure Accuracy Against Anchors

Once consistency is confirmed, test accuracy — does the evaluator reproduce human scores?

```python
def run_accuracy_test(
    evaluator_fn,
    anchor_set: list[dict]
) -> dict:
    """
    Compare evaluator scores to human ground-truth scores.
    Target: exact match or ±1 on every dimension.
    """
    results = []

    for anchor in anchor_set:
        eval_result = evaluator_fn(anchor["question"], anchor["answer"])

        for dim, expected_score in anchor["expected_scores"].items():
            actual_score = next(
                ds["score"] for ds in eval_result["dimension_scores"]
                if ds["dimension"] == dim
            )
            delta = abs(actual_score - expected_score)
            results.append({
                "anchor_id": anchor["id"],
                "dimension": dim,
                "expected": expected_score,
                "actual": actual_score,
                "delta": delta,
                "exact_match": delta == 0,
                "within_one": delta <= 1,
                "hard_miss": delta >= 2  # Serious calibration failure
            })

    total = len(results)
    return {
        "exact_match_rate": sum(r["exact_match"] for r in results) / total,
        "within_one_rate": sum(r["within_one"] for r in results) / total,
        "hard_miss_rate": sum(r["hard_miss"] for r in results) / total,
        "hard_misses": [r for r in results if r["hard_miss"]],
        "ready_for_production": sum(r["hard_miss"] for r in results) == 0
    }
```

**Targets:**
- Exact match rate: ≥ 70%
- Within-one rate: ≥ 95%
- Hard miss rate (±2 or more): 0% — any hard miss blocks production deployment

---

## Step 4: Fix Calibration Failures

When the evaluator mis-scores an anchor, the fix is almost always in the prompt — not the model.

### Diagnosis → Fix Map

| Failure Pattern | Likely Cause | Fix |
|---|---|---|
| Scores too high across all dims | Rubric language is too lenient | Add "Do not award 4 unless ALL criteria are met" |
| Scores too low on specificity | Evaluator misreads detail level | Add concrete example of Score 3 vs 4 evidence |
| High variance on ownership | "I" vs "we" boundary is ambiguous | Add explicit counting heuristic in rubric |
| Consistently wrong on Score 1 | Score 1 definition too vague | Add "Score 1 means X is completely absent" |
| Hard miss on Score 4 only | Missing the ceiling definition | Add a verbatim Score 4 example in the prompt |

### Prompt Hardening Techniques

```
1. Add negative examples to rubric anchors:
   "Score 4 does NOT mean perfect delivery — it means all criteria are met.
    An answer can score 4 on specificity while scoring 2 on structure."

2. Add explicit instruction for uncertainty:
   "If you cannot determine a score with confidence ≥ 0.75, score the lower
    of the two candidate scores and set confidence below 0.75."

3. Add chain-of-thought requirement before the JSON:
   "Before outputting the JSON, write one sentence per dimension explaining
    your reasoning. Then output the JSON."
   (Remove the CoT from parsing; it improves accuracy without adding to output size.)

4. Add format strictness instruction:
   "Do not add commentary, apologies, or explanation outside the JSON object.
    The first character of your response must be {{ and the last must be }}."
```

---

## Step 5: Threshold Calibration

Once the evaluator is accurate, tune the pass/fail thresholds to match your hiring bar.

### Threshold Tuning Process

```python
def tune_thresholds(
    historical_evaluations: list[dict],  # Past evals with human final decisions
    target_precision: float = 0.90       # How often PASS should be a real hire
) -> dict:
    """
    Given historical evaluations with known human outcomes,
    find the composite score threshold that achieves target precision.
    """
    from collections import defaultdict

    # Group by composite score bucket
    buckets = defaultdict(lambda: {"hired": 0, "rejected": 0})
    for e in historical_evaluations:
        bucket = int(e["composite_score"] // 5) * 5  # 5-point buckets
        outcome = "hired" if e["human_decision"] == "hire" else "rejected"
        buckets[bucket][outcome] += 1

    # Find threshold where precision meets target
    recommended_pass = None
    for threshold in range(95, 40, -5):
        above_threshold = [
            e for e in historical_evaluations
            if e["composite_score"] >= threshold
        ]
        if not above_threshold:
            continue
        precision = sum(1 for e in above_threshold if e["human_decision"] == "hire") / len(above_threshold)
        if precision >= target_precision:
            recommended_pass = threshold
            break

    return {
        "recommended_pass_threshold": recommended_pass,
        "precision_at_threshold": precision,
        "coverage": len([e for e in historical_evaluations if e["composite_score"] >= recommended_pass]) / len(historical_evaluations),
        "bucket_analysis": dict(buckets)
    }
```

**Important:** Until you have ≥ 100 historical evaluations with human outcomes,
use conservative defaults and widen the MAYBE band. Err toward human review.

---

## Step 6: Drift Detection

Model updates, prompt changes, and rubric edits can all silently change your evaluator's behaviour.
Run drift detection weekly in production.

```python
def check_for_drift(
    evaluator_fn,
    anchor_set: list[dict],
    baseline_scores: dict,  # Scores from initial calibration
    drift_threshold: float = 0.1  # Alert if mean score shifts by more than 0.1
) -> dict:
    """
    Re-run anchor set against current evaluator.
    Alert if mean scores have drifted from baseline.
    """
    current_scores = {}
    for anchor in anchor_set:
        result = evaluator_fn(anchor["question"], anchor["answer"])
        for ds in result["dimension_scores"]:
            dim = ds["dimension"]
            current_scores.setdefault(dim, []).append(ds["score"])

    current_means = {dim: sum(scores) / len(scores) for dim, scores in current_scores.items()}
    baseline_means = baseline_scores  # Pre-computed at calibration time

    drift_report = {}
    alerts = []
    for dim in current_means:
        delta = abs(current_means[dim] - baseline_means.get(dim, current_means[dim]))
        drifted = delta > drift_threshold
        drift_report[dim] = {
            "baseline_mean": baseline_means.get(dim),
            "current_mean": current_means[dim],
            "delta": round(delta, 3),
            "drifted": drifted
        }
        if drifted:
            alerts.append(f"{dim}: shifted {delta:+.2f} from baseline")

    return {
        "drift_detected": len(alerts) > 0,
        "alerts": alerts,
        "per_dimension": drift_report,
        "action_required": len(alerts) > 0
    }
```

**Run drift detection:**
- After any model version change
- After any rubric or prompt edit
- Weekly in steady state (catches silent model updates from providers)

---

## Human-in-the-Loop Audit Workflow

Every MAYBE verdict and every low-confidence evaluation needs a human touchpoint.

### Audit Queue Schema

```python
AUDIT_QUEUE_ENTRY = {
    "audit_id": "audit_xyz",
    "evaluation_id": "eval_abc",
    "candidate_id": "cand_123",
    "queue_reason": "MAYBE verdict",       # Why this was flagged
    "priority": "normal",                  # high / normal / low
    "assigned_to": None,                   # HR reviewer user ID
    "status": "pending",                   # pending / in_review / resolved
    "created_at": "2025-02-26T14:00:00Z",
    "sla_deadline": "2025-02-27T14:00:00Z", # 24hr SLA for pending reviews
    "evaluation_summary": {
        "composite_score": 58,
        "verdict": "MAYBE",
        "dimension_scores": [...],
        "flags": [],
    }
}
```

### SLA Targets

| Verdict | Review SLA | Priority |
|---|---|---|
| PASS | No review required | — |
| MAYBE | 24 hours | Normal |
| FAIL (hard fail dim) | 48 hours (appeals) | Low |
| Any flag raised | 4 hours | High |
| Toxicity detected | Immediate | Critical |

---

## Production Readiness Checklist

Before deploying your evaluation pipeline to real candidates:

```
CALIBRATION
  □ Anchor set built (12+ anchors per question type)
  □ Consistency test passing (all dimensions stable, variance ≤ 1)
  □ Accuracy test passing (0 hard misses on anchor set)
  □ Baseline scores recorded for drift detection

PIPELINE
  □ Retry logic implemented (max 3 attempts, exponential backoff)
  □ JSON parsing validated against malformed LLM output
  □ Preflight checks active (length, PII, toxicity)
  □ Flag conditions defined and tested
  □ Hard-fail dimensions configured per role/level
  □ Verdict thresholds set per level (L3–L6)

OPERATIONS
  □ Audit logging active (append-only store)
  □ Human review queue live with SLA tracking
  □ Drift detection scheduled (weekly minimum)
  □ Escalation path defined for MAYBE verdicts
  □ Candidate data retention policy documented

LEGAL & FAIRNESS
  □ Bias audit run on anchor set across demographic proxies
  □ Legal review of automated decision-making disclosure
  □ Candidate right-to-explanation process defined
  □ Evaluator version pinned in all audit records
```
