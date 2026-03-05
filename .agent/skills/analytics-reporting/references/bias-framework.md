---
name: bias-framework
description: Statistical bias tests for interview scoring systems — disparate impact, equalised odds, demographic parity calculations, p-value testing, and remediation workflows.
---

# Bias Detection Framework Reference

---

## Fairness Metrics

| Metric | Formula | Threshold | Meaning |
|---|---|---|---|
| Disparate Impact Ratio | pass_rate_A / pass_rate_B | < 0.80 = alert | 4/5ths rule (EEOC) |
| Demographic Parity Diff | pass_rate_A - pass_rate_B | > 10% = alert | Absolute pass rate gap |
| Score Gap | mean_score_A - mean_score_B | > 5pts = alert | Mean score difference |
| Equalised Odds | TPR_A / TPR_B and FPR_A / FPR_B | > 20% gap = alert | Error rate parity |

---

## Statistical Significance Testing

```python
from scipy import stats
import numpy as np

def test_score_disparity(
    group_a_scores: list[float],
    group_b_scores: list[float],
    alpha: float = 0.05,
) -> dict:
    """
    Welch's t-test for score difference between demographic groups.
    Use Welch's (not Student's) — does not assume equal variance.
    """
    if len(group_a_scores) < 30 or len(group_b_scores) < 30:
        return {"result": "insufficient_sample", "min_required": 30}

    t_stat, p_value = stats.ttest_ind(
        group_a_scores, group_b_scores, equal_var=False
    )

    mean_a = np.mean(group_a_scores)
    mean_b = np.mean(group_b_scores)
    cohen_d = (mean_a - mean_b) / np.sqrt(
        (np.std(group_a_scores)**2 + np.std(group_b_scores)**2) / 2
    )

    return {
        "mean_a":           round(float(mean_a), 2),
        "mean_b":           round(float(mean_b), 2),
        "mean_difference":  round(float(mean_a - mean_b), 2),
        "t_statistic":      round(float(t_stat), 4),
        "p_value":          round(float(p_value), 4),
        "significant":      p_value < alpha,
        "effect_size_d":    round(float(cohen_d), 3),
        "effect_magnitude": (
            "negligible" if abs(cohen_d) < 0.2 else
            "small"      if abs(cohen_d) < 0.5 else
            "medium"     if abs(cohen_d) < 0.8 else
            "large"
        ),
        "n_a": len(group_a_scores),
        "n_b": len(group_b_scores),
    }


def compute_disparate_impact(
    group_pass_counts: dict[str, int],
    group_total_counts: dict[str, int],
) -> dict:
    """
    Compute disparate impact ratio for all group pairs.
    Flags any pair below 0.80 (EEOC 4/5ths rule).
    """
    pass_rates = {
        group: group_pass_counts.get(group, 0) / total
        for group, total in group_total_counts.items()
        if total >= 30
    }

    if not pass_rates:
        return {"result": "insufficient_data"}

    max_rate = max(pass_rates.values())
    results = {}

    for group, rate in pass_rates.items():
        di_ratio = rate / max_rate if max_rate > 0 else 1.0
        results[group] = {
            "pass_rate":   round(rate, 4),
            "di_ratio":    round(di_ratio, 3),
            "alert":       di_ratio < 0.80,
            "warning":     di_ratio < 0.90,
            "n":           group_total_counts[group],
        }

    return {
        "reference_group": max(pass_rates, key=pass_rates.get),
        "groups": results,
        "any_alert": any(r["alert"] for r in results.values()),
    }
```

---

## Remediation Workflow

```
ALERT TRIGGERED: Disparate impact ratio < 0.80
│
├── STEP 1: Validate data quality
│   □ Sample size sufficient (n >= 30 per group)?
│   □ Demographic data from self-identification (not inferred)?
│   □ Same role and level being compared?
│   □ Same time period (no seasonal effects)?
│
├── STEP 2: Diagnose source
│   □ Is the gap in a specific dimension? (run dimension-level analysis)
│   □ Is the gap correlated with a specific question type?
│   □ Is the gap from a specific evaluator version?
│   □ Is the gap present in human evaluations too?
│
├── STEP 3: Immediate actions
│   □ Pause automated FAIL verdicts for affected group
│   □ Route all sessions from affected group to human review
│   □ Alert legal and HR teams
│
├── STEP 4: Root cause investigation
│   □ Rubric language audit — is any dimension culturally biased?
│   □ Calibration set audit — are anchor answers representative?
│   □ Question content review — are questions domain-specific in ways that disadvantage groups?
│
└── STEP 5: Remediation and monitoring
    □ Update rubric with clearer, culturally neutral criteria
    □ Expand calibration set with diverse anchor answers
    □ Re-run historical evaluations with updated rubric
    □ Monitor for 30 days after change to confirm improvement
    □ Document incident and remediation in audit log
```

---

## Bias Monitoring Schedule

```python
# Run weekly bias report — schedule with cron or Celery beat
@celery_app.task(name="weekly_bias_report")
def run_weekly_bias_report():
    results = compute_full_bias_report(lookback_days=90)

    for metric in results["alerts"]:
        if metric["severity"] == "critical":
            notify_immediately(metric)   # PagerDuty / legal team
        elif metric["severity"] == "warning":
            include_in_weekly_digest(metric)

    store_bias_report(results)   # Keep for audit trail
```
