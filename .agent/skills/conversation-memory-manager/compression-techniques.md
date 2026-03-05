---
name: compression-techniques
description: Detailed memory compression algorithms, implementation patterns, and benchmarks for LLM context window management. Covers rolling summary, hierarchical summary, selective eviction, semantic dedup, and entity extraction strategies.
---

# Compression Techniques Reference

Lena's detailed breakdown of every context compression strategy — when it works, when it fails, and how to implement it.

---

## 1. Rolling Summary (Most Common)

**What it does:** Compresses all turns older than the last N into a single summary block. Re-summarizes as the session grows.

**When to use:**
- Sessions expected to exceed 30–50 turns
- Continuity matters but verbatim recall doesn't
- You want something that works today, not in 3 sprints

**Implementation:**
```python
def rolling_summary(
    turns: list[dict],
    model,
    keep_raw: int = 8,
    max_summary_tokens: int = 400
) -> list[dict]:
    """
    Compresses turns older than `keep_raw` into a summary.
    Triggered every time history grows beyond keep_raw.
    """
    if len(turns) <= keep_raw:
        return turns

    old_turns = turns[:-keep_raw]
    new_turns = turns[-keep_raw:]

    summary = call_llm(
        system="""Summarize this conversation segment into a compact memory block.
        Keep: decisions, facts revealed, user preferences, open questions.
        Drop: filler, repeated context, pleasantries.
        Write in third person present tense. Max 400 tokens.""",
        messages=old_turns
    )

    return [
        {"role": "system", "content": f"[Prior conversation summary]: {summary}"}
    ] + new_turns
```

**Compression ratio:** 5–15× (highly variable by conversation style)
**Latency cost:** 1 LLM call per compression trigger (~500–2000ms)
**Quality loss:** Low for gist retention, high for verbatim recall

**Failure mode:** Summary accumulates summaries-of-summaries over very long sessions → meaning drift. Fix: hierarchical approach below.

---

## 2. Hierarchical Summary

**What it does:** Maintains summaries at multiple granularity levels — turn-level, segment-level, session-level. Like a document outline.

**When to use:**
- Sessions spanning hours or days
- Agents doing long multi-step tasks
- When a rolling summary starts losing coherence

**Structure:**
```
Session Memory
├── Session Summary (high-level, ~200 tokens)
│   ├── Segment 1 Summary (~100 tokens) ← "User was debugging auth flow"
│   │   ├── Turn 1–8 (raw, then evicted)
│   ├── Segment 2 Summary (~100 tokens) ← "Switched to deployment issue"
│   │   ├── Turn 9–16 (raw, then evicted)
│   └── Segment 3 (current, raw turns kept)
│       ├── Turn 17–current
```

**Implementation pattern:**
```python
class HierarchicalMemory:
    def __init__(self, segment_size=10, keep_raw=6):
        self.segments: list[dict] = []       # Compressed segments
        self.current_segment: list[dict] = [] # Raw current segment
        self.session_summary: str = ""
        self.segment_size = segment_size
        self.keep_raw = keep_raw

    def add_turn(self, turn: dict, model):
        self.current_segment.append(turn)

        # Compress segment when it reaches segment_size
        if len(self.current_segment) >= self.segment_size:
            seg_summary = self._summarize_segment(self.current_segment, model)
            self.segments.append({"summary": seg_summary, "turn_count": len(self.current_segment)})
            self.current_segment = []

            # Re-summarize session-level if segments grow large
            if len(self.segments) >= 5:
                self._compress_session(model)

    def build_context(self) -> list[dict]:
        blocks = []
        if self.session_summary:
            blocks.append({"role": "system", "content": f"[Session overview]: {self.session_summary}"})
        for seg in self.segments[-3:]:  # Last 3 segment summaries
            blocks.append({"role": "system", "content": f"[Earlier]: {seg['summary']}"})
        blocks += self.current_segment[-self.keep_raw:]
        return blocks
```

**Compression ratio:** 10–50×
**Latency cost:** Multiple LLM calls; must be async
**Quality loss:** Medium — coarse-grained older context, fine-grained recent

---

## 3. Selective Eviction

**What it does:** Scores each turn by importance and evicts the lowest-scoring ones when budget is exceeded. Not a summary — actual deletion.

**When to use:**
- You need verbatim preservation for high-importance turns
- Conversations with clearly mixed-importance content (small talk + critical decisions)
- When you can define importance signals programmatically

**Scoring signals:**
```python
def score_turn(turn: dict, turn_index: int, total_turns: int) -> float:
    score = 0.0

    # Recency bonus (always keep recent turns)
    recency = turn_index / total_turns
    score += recency * 0.4

    # Length signal (longer turns often more substantive)
    word_count = len(turn["content"].split())
    score += min(word_count / 200, 1.0) * 0.2

    # Explicit marker signals
    content = turn["content"].lower()
    if any(kw in content for kw in ["decided", "confirmed", "important", "remember"]):
        score += 0.3
    if any(kw in content for kw in ["thanks", "ok", "sure", "got it"]):
        score -= 0.2

    # Role signal (assistant turns often more information-dense)
    if turn["role"] == "assistant":
        score += 0.1

    return max(0.0, min(1.0, score))
```

**Compression ratio:** 2–5× (gentle — keeps high-value turns)
**Latency cost:** Scoring only (fast) — no LLM calls needed
**Quality loss:** Low if scoring is well-calibrated; catastrophic if not

**Failure mode:** Important context in a short, casual-sounding turn gets evicted. Always combine with recency protection.

---

## 4. Semantic Deduplication

**What it does:** Embeds all turns and removes near-duplicate content — turns that say essentially the same thing.

**When to use:**
- Conversations with lots of back-and-forth on the same topic
- Agent loops that repeat context in tool calls
- Automated pipelines where duplicate injection is common

**Implementation:**
```python
import numpy as np

def semantic_dedup(
    turns: list[dict],
    embed_fn,
    similarity_threshold: float = 0.92
) -> list[dict]:
    if len(turns) <= 2:
        return turns

    embeddings = [embed_fn(t["content"]) for t in turns]
    keep = [True] * len(turns)

    for i in range(len(turns)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(turns)):
            if not keep[j]:
                continue
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim >= similarity_threshold:
                keep[j] = False  # Evict the later duplicate

    return [t for t, k in zip(turns, keep) if k]
```

**Compression ratio:** 1.5–3× (effective only on repetitive conversations)
**Latency cost:** Embedding calls (fast with cached models, ~10–50ms per turn)
**Quality loss:** Very low — removes redundancy, not meaning

**Failure mode:** Two turns look semantically similar but serve different discourse roles (confirmation vs. new question). Tune threshold carefully; 0.92+ is usually safe.

---

## 5. Entity Extraction (Lossy → Structured)

**What it does:** Rather than compressing turns into prose summaries, extracts structured facts — user name, preferences, decisions, entities — and discards the raw turns.

**When to use:**
- Building user profiles / semantic memory from conversations
- Long-term personalization across sessions
- When you need to *query* memory, not just inject it

**Output format:**
```json
{
  "user_id": "u_abc123",
  "extracted_at": "2025-02-26T14:30:00Z",
  "facts": [
    {"key": "name", "value": "Priya", "confidence": 0.99, "source_turn": 3},
    {"key": "language_preference", "value": "Python", "confidence": 0.95, "source_turn": 7},
    {"key": "timezone", "value": "IST", "confidence": 0.80, "source_turn": 12},
    {"key": "open_question", "value": "Wants help deploying to AWS ECS", "confidence": 0.90, "source_turn": 22}
  ],
  "decisions": [
    {"description": "Chose FastAPI over Flask for new project", "turn": 15}
  ]
}
```

**Extraction prompt:**
```
Extract structured facts from this conversation segment.
Return JSON with keys: facts (list of {key, value, confidence}), decisions (list of {description}).
Only extract facts explicitly stated — do not infer. Confidence reflects certainty from the text.
Omit pleasantries, filler, and any PII beyond first name unless user volunteered it explicitly.
```

**Compression ratio:** Extremely high — entire sessions → <1KB JSON
**Latency cost:** 1 LLM call (can be async, end-of-session)
**Quality loss:** High — you lose discourse flow, tone, and anything not extractable as a fact

---

## Compression Strategy Selection Guide

```
Is session length the problem? (hitting token limits mid-session)
  → YES: Rolling Summary (quick win) or Hierarchical (long sessions)
  → NO ↓

Is the content repetitive? (agent loops, back-and-forth on same topic)
  → YES: Semantic Dedup first, then Rolling Summary if still needed
  → NO ↓

Do you need verbatim recall of some turns? (legal, medical, commitments)
  → YES: Selective Eviction (keep important turns raw)
  → NO ↓

Do you need structured queries over memory? (user profile, personalization)
  → YES: Entity Extraction → structured semantic store
  → NO ↓

Default: Rolling Summary — it handles 90% of cases.
```

---

## Benchmarks (Approximate, GPT-4-class Models)

| Technique | Avg Compression | Fact Retention | Latency Added | Implementation Effort |
|---|---|---|---|---|
| Sliding Window | 1× (eviction) | 0% (old turns lost) | 0ms | Trivial |
| Rolling Summary | 8× | 75–85% | 800–2000ms | Low |
| Hierarchical Summary | 25× | 70–80% | 1500–4000ms | Medium |
| Selective Eviction | 3× | 85–95% | 10–50ms | Medium |
| Semantic Dedup | 2× | 90–98% | 50–200ms | Low–Medium |
| Entity Extraction | 100×+ | 60–75% (structured) | 500–1500ms | Medium–High |

> These are ballpark figures. Real performance depends heavily on conversation style,
> model quality, prompt design, and how you define "fact retention."
> Always benchmark on your own data before committing to a strategy.
