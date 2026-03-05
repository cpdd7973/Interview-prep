---
name: prompt-templates
description: Production-ready LLM prompt templates for candidate evaluation pipelines. Includes full prompt library, structured output schemas, JSON parsing utilities, retry logic, and multi-turn evaluation patterns.
---

# Prompt Templates & Parsing Reference

Complete prompt library for the Candidate Evaluation Engine — ready to copy into production.

---

## Full Evaluation Orchestrator

The top-level function that routes to the correct evaluator and assembles the final result:

```python
import json
import time
from typing import Literal

QuestionType = Literal["behavioral", "technical", "communication"]

def evaluate_answer(
    question: str,
    answer: str,
    question_type: QuestionType,
    role: str,
    level: str,
    expected_concepts: list[str] = None,  # For technical questions
    model: str = "claude-sonnet-4-6",
    max_retries: int = 3
) -> dict:
    """
    Full evaluation pipeline for a single question-answer pair.
    Returns structured evaluation result matching the output schema.
    """
    start = time.time()

    # 1. Pre-processing checks
    flags = run_preflight_checks(answer)
    if "toxicity_detected" in flags:
        return build_halted_result(answer, flags, "toxicity")

    # 2. Select and run evaluator
    if question_type == "behavioral":
        raw = run_behavioral_evaluator(question, answer, role, level, model, max_retries)
        weights = BEHAVIORAL_WEIGHTS
    elif question_type == "technical":
        raw = run_technical_evaluator(question, answer, role, level, expected_concepts or [], model, max_retries)
        weights = TECHNICAL_WEIGHTS
    else:
        raw = run_communication_evaluator(question, answer, role, level, model, max_retries)
        weights = COMMUNICATION_WEIGHTS

    # 3. Aggregate and verdict
    composite = compute_composite_score(raw["dimension_scores"], weights)
    verdict, rationale = compute_verdict(composite, level, raw["dimension_scores"])
    escalate, escalation_reasons = requires_human_escalation(verdict, raw["dimension_scores"])

    return {
        "evaluation_id": generate_id(),
        "evaluated_at": utc_now(),
        "input": {
            "question": question,
            "answer": answer,
            "role": role,
            "level": level,
            "question_type": question_type,
        },
        "dimension_scores": raw["dimension_scores"],
        "composite_score": composite,
        "composite_max": 100,
        "verdict": verdict,
        "verdict_rationale": rationale,
        "flags": flags,
        "requires_human_review": escalate,
        "escalation_reasons": escalation_reasons,
        "internal_notes": raw.get("evaluator_notes", ""),
        "metadata": {
            "answer_length_tokens": estimate_tokens(answer),
            "processing_time_ms": int((time.time() - start) * 1000),
            "model": model,
        }
    }
```

---

## Preflight Check Implementation

```python
def run_preflight_checks(answer: str) -> list[str]:
    """Fast, synchronous checks before any LLM calls."""
    flags = []

    tokens = estimate_tokens(answer)
    if tokens < 30:
        flags.append("answer_too_short")

    if tokens > 2000:
        flags.append("answer_very_long")  # May need truncation

    # Simple pattern-based PII detection (augment with a proper library in prod)
    import re
    if re.search(r'\b\d{3}-\d{2}-\d{4}\b', answer):  # SSN pattern
        flags.append("pii_detected")

    # Toxicity: use a classifier in prod; pattern-based here for illustration
    toxic_patterns = ["kill", "hate", "threaten"]  # Extend as needed
    if any(p in answer.lower() for p in toxic_patterns):
        flags.append("toxicity_detected")

    return flags
```

---

## Behavioral Evaluator — Full Implementation

```python
BEHAVIORAL_PROMPT = """You are a calibrated interview evaluation system scoring a candidate's behavioral answer.
Apply the rubric exactly as specified. Return ONLY valid JSON — no prose, no markdown, no explanation outside the JSON.

=== INPUT ===
QUESTION: {question}
CANDIDATE ANSWER: {answer}
ROLE: {role}
LEVEL: {level}

=== RUBRIC ===
Score each dimension 1–4. For EVERY dimension, extract a verbatim quote or close paraphrase from the answer as evidence.

DIMENSION 1: star_structure
4 - All four STAR elements (Situation, Task, Action, Result) present and clearly ordered
3 - All elements present but one is weak, rushed, or underdeveloped
2 - Two or three elements present; Result is typically absent
1 - One or zero elements; answer is hypothetical, rambling, or off-topic

DIMENSION 2: specificity
4 - Named individuals, exact metrics ("increased conversion by 18%"), real dates or timelines throughout
3 - Some concrete details present alongside vague generalisations
2 - Mostly abstract; project or outcome described in general terms only
1 - No verifiable specifics; could describe anyone's experience

DIMENSION 3: ownership_accountability
4 - Clear first-person ownership throughout; explicitly owns failures and decisions; no hiding behind "we"
3 - Mostly first-person; some diffusion to "the team" or "we" in key moments
2 - Primarily "we"; personal contribution is ambiguous or unclear
1 - Cannot determine what this individual specifically did or decided

DIMENSION 4: impact_result
4 - Quantified result (numbers, percentages, timelines) AND explains business or team significance
3 - Result stated but not quantified ("it went well", "the project shipped")
2 - Vague outcome implied ("things improved") or result missing from story
1 - No result or outcome mentioned at all

DIMENSION 5: communication_clarity
4 - Logical progression, concise, no unnecessary filler, answer is self-contained
3 - Generally clear; minor disorganisation or slight over-length
2 - Difficult to follow in places; repetitive, or answer trails off
1 - Incoherent, circular, or non-responsive to the question asked

=== REQUIRED OUTPUT ===
{{
  "dimension_scores": [
    {{
      "dimension": "star_structure",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<quote or close paraphrase from answer>",
      "confidence": <0.70-1.00>
    }},
    {{
      "dimension": "specificity",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<quote or close paraphrase from answer>",
      "confidence": <0.70-1.00>
    }},
    {{
      "dimension": "ownership_accountability",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<quote or close paraphrase from answer>",
      "confidence": <0.70-1.00>
    }},
    {{
      "dimension": "impact_result",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<quote or close paraphrase from answer>",
      "confidence": <0.70-1.00>
    }},
    {{
      "dimension": "communication_clarity",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<quote or close paraphrase from answer>",
      "confidence": <0.70-1.00>
    }}
  ],
  "evaluator_notes": "<1-2 sentences for hiring team; never shown to candidate>"
}}"""


def run_behavioral_evaluator(
    question: str, answer: str, role: str, level: str,
    model: str, max_retries: int
) -> dict:
    prompt = BEHAVIORAL_PROMPT.format(
        question=question, answer=answer, role=role, level=level
    )
    return call_with_retry(prompt, model, max_retries)
```

---

## Technical Evaluator — Full Implementation

```python
TECHNICAL_PROMPT = """You are a calibrated technical interview evaluation system.
Apply the rubric exactly. Return ONLY valid JSON.

=== INPUT ===
QUESTION: {question}
EXPECTED CONCEPTS: {expected_concepts}
CANDIDATE ANSWER: {answer}
ROLE: {role}
LEVEL: {level}

=== RUBRIC ===

DIMENSION 1: correctness
4 - Fully correct; handles edge cases; no factual errors
3 - Core solution correct; minor gaps on edge cases or constraints
2 - Partially correct; one significant error or missing component
1 - Fundamentally incorrect, unusable, or question not addressed

DIMENSION 2: depth_completeness
4 - Proactively addresses constraints, scalability, failure modes, and edge cases
3 - Addresses the main problem; misses 1-2 edge cases or constraints
2 - Solves the happy path only; no consideration of edge cases
1 - Superficial treatment; does not substantively address the problem

DIMENSION 3: tradeoff_reasoning
4 - Names 2+ alternative approaches with clear rationale for chosen solution
3 - Acknowledges trade-offs (may need prompting); considers one alternative
2 - Presents chosen solution as the only option; no alternatives considered
1 - No awareness of design choices; treats solution as obvious

DIMENSION 4: communication_clarity
4 - Explanation is precise, structured, and could stand alone as documentation
3 - Generally clear but assumes shared context; minor gaps in explanation
2 - Unclear in places; non-technical listener would struggle to follow
1 - Incomprehensible or entirely off-topic

=== REQUIRED OUTPUT ===
{{
  "dimension_scores": [
    {{
      "dimension": "correctness",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<specific observation or quote from answer>",
      "confidence": <0.70-1.00>
    }},
    {{
      "dimension": "depth_completeness",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<specific observation or quote from answer>",
      "confidence": <0.70-1.00>
    }},
    {{
      "dimension": "tradeoff_reasoning",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<specific observation or quote from answer>",
      "confidence": <0.70-1.00>
    }},
    {{
      "dimension": "communication_clarity",
      "score": <1-4>,
      "label": "<Exceptional|Proficient|Developing|Insufficient>",
      "evidence": "<specific observation or quote from answer>",
      "confidence": <0.70-1.00>
    }}
  ],
  "missing_concepts": ["<expected concept not addressed in answer>"],
  "evaluator_notes": "<internal notes for hiring team only>"
}}"""
```

---

## Retry & Parsing Utilities

```python
import json
import re

def call_with_retry(prompt: str, model: str, max_retries: int) -> dict:
    """Call LLM with structured output, retry on parse failure."""
    last_error = None
    for attempt in range(max_retries):
        try:
            raw_text = call_llm(system=prompt, model=model)
            return parse_evaluation_json(raw_text)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))  # Exponential backoff
            continue

    raise EvaluationParseError(
        f"Failed to parse evaluator output after {max_retries} attempts. "
        f"Last error: {last_error}"
    )


def parse_evaluation_json(raw: str) -> dict:
    """
    Robust JSON parser for LLM evaluation output.
    Handles common LLM formatting issues.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = cleaned.rstrip("`").strip()

    # Extract JSON object if surrounded by prose
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if not match:
        raise json.JSONDecodeError("No JSON object found in response", cleaned, 0)

    result = json.loads(match.group())

    # Validate required structure
    if "dimension_scores" not in result:
        raise ValueError("Missing 'dimension_scores' in evaluator output")

    for ds in result["dimension_scores"]:
        required_keys = {"dimension", "score", "label", "evidence", "confidence"}
        missing = required_keys - set(ds.keys())
        if missing:
            raise ValueError(f"Dimension score missing keys: {missing}")
        if not (1 <= ds["score"] <= 4):
            raise ValueError(f"Score {ds['score']} out of range for {ds['dimension']}")

    return result


class EvaluationParseError(Exception):
    """Raised when LLM output cannot be parsed into a valid evaluation."""
    pass
```

---

## Batch Evaluation Pattern

For processing multiple answers asynchronously (interview pipeline use case):

```python
import asyncio

async def evaluate_interview_session(
    session: dict,  # {candidate_id, role, level, qa_pairs: [{question, answer, type}]}
    model: str = "claude-sonnet-4-6"
) -> dict:
    """
    Evaluate all answers in an interview session concurrently.
    Returns aggregated session result.
    """
    tasks = [
        asyncio.to_thread(
            evaluate_answer,
            qa["question"], qa["answer"], qa["type"],
            session["role"], session["level"],
            model=model
        )
        for qa in session["qa_pairs"]
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Separate successful evaluations from errors
    evaluations = []
    errors = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            errors.append({"qa_index": i, "error": str(r)})
        else:
            evaluations.append(r)

    # Session-level aggregation
    all_composites = [e["composite_score"] for e in evaluations]
    session_composite = sum(all_composites) / len(all_composites) if all_composites else 0
    any_hard_fail = any(e["verdict"] == "FAIL" for e in evaluations)
    all_pass = all(e["verdict"] == "PASS" for e in evaluations)

    session_verdict = (
        "FAIL" if any_hard_fail else
        "PASS" if all_pass else
        "MAYBE"
    )

    return {
        "session_id": generate_id(),
        "candidate_id": session["candidate_id"],
        "role": session["role"],
        "level": session["level"],
        "question_evaluations": evaluations,
        "session_composite": round(session_composite, 1),
        "session_verdict": session_verdict,
        "requires_human_review": any(e["requires_human_review"] for e in evaluations),
        "evaluation_errors": errors,
    }
```

---

## Audit Log Schema

Every evaluation must produce an audit record. Non-negotiable in hiring systems.

```python
def write_audit_log(evaluation: dict, session_id: str = None):
    """
    Write immutable audit record. Use append-only store (S3, CloudWatch, etc.)
    NEVER delete or modify audit records.
    """
    audit_record = {
        "audit_id": generate_id(),
        "timestamp": utc_now(),
        "evaluation_id": evaluation["evaluation_id"],
        "session_id": session_id,
        "candidate_id": evaluation.get("candidate_id"),
        "question_hash": hash_text(evaluation["input"]["question"]),
        "answer_hash": hash_text(evaluation["input"]["answer"]),
        # Store answer hash, NOT the answer — audit proves what was scored
        # without storing PII indefinitely
        "role": evaluation["input"]["role"],
        "level": evaluation["input"]["level"],
        "composite_score": evaluation["composite_score"],
        "verdict": evaluation["verdict"],
        "evaluator_version": evaluation["input"].get("evaluator_version"),
        "model": evaluation["metadata"]["model"],
        "flags": evaluation["flags"],
        "requires_human_review": evaluation["requires_human_review"],
    }
    append_to_audit_store(audit_record)
```
