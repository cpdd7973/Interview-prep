---
name: retrieval-patterns
description: Advanced retrieval patterns for RAG pipelines including query expansion, HyDE, multi-hop retrieval, cross-encoder re-ranking, and a full evaluation harness with precision/recall measurement.
---

# Retrieval Patterns Reference

Advanced retrieval techniques beyond basic vector search — with implementations
and when to reach for each one.

---

## Pattern 1: Query Rewriting

Never send raw user input to your retriever. Always rewrite.

```python
QUERY_REWRITE_PROMPT = """Rewrite this user query to be optimised for document retrieval.
Rules:
- Remove conversational filler ("can you tell me", "I want to know")
- Expand acronyms if domain is known
- Add synonyms for key terms
- Convert negatives to positive search terms where possible
- Keep it concise — retrieval queries should be 5-20 words

DOMAIN: {domain}
ORIGINAL QUERY: {query}

Return JSON: {{"rewritten": "<query>", "key_terms": ["<term1>", "<term2>"]}}"""


def rewrite_query(query: str, domain: str) -> dict:
    return call_llm_json(QUERY_REWRITE_PROMPT.format(query=query, domain=domain))
```

**HR domain rewrite examples:**
```
"show me people who can build APIs"
→ "software engineer API development REST backend experience"

"what do you need for the marketing job"
→ "marketing manager requirements qualifications experience skills"

"is there something remote"
→ "remote work from home distributed position location"
```

---

## Pattern 2: HyDE (Hypothetical Document Embeddings)

Generate a hypothetical answer, embed it, use that embedding for retrieval.
Particularly effective for Q&A retrieval where query and answer have different vocabulary.

```python
HYDE_PROMPT = """Write a short hypothetical answer to this question as if you were
an expert in {domain}. This will be used to find real answers in a knowledge base —
so write it in the style and vocabulary of the documents you'd expect to find.
2-4 sentences max.

QUESTION: {question}"""


def hyde_retrieve(
    question: str,
    domain: str,
    retriever,
    top_k: int = 5
) -> list[dict]:
    """
    Use a hypothetical answer embedding for retrieval instead of the raw question.
    Dramatically improves recall when query vocabulary differs from document vocabulary.
    """
    # Generate hypothetical answer
    hypothetical_answer = call_llm(
        HYDE_PROMPT.format(question=question, domain=domain)
    )

    # Embed the hypothetical answer (not the question)
    hyde_embedding = embed(hypothetical_answer)

    # Retrieve using hypothetical embedding
    results = retriever.query(embedding=hyde_embedding, top_k=top_k)

    return results


# When to use HyDE:
# ✅ User asks "how do I..." and docs are written in instructional format
# ✅ FAQ retrieval where question vocab ≠ answer vocab
# ✅ Resume matching where query is "find Python engineers" and docs are CVs
# ❌ When exact keyword matching matters (use BM25 instead)
# ❌ When the query already matches document language well
```

---

## Pattern 3: Multi-Query Retrieval

Generate multiple query variants, retrieve for each, fuse results.
Reduces the impact of any single query being poorly formed.

```python
MULTI_QUERY_PROMPT = """Generate {n} different search queries that would retrieve
documents relevant to answering this question. Each query should approach the topic
from a different angle. Return as JSON array of strings.

QUESTION: {question}
DOMAIN: {domain}"""


def multi_query_retrieve(
    question: str,
    domain: str,
    retriever,
    n_queries: int = 3,
    top_k_per_query: int = 5
) -> list[dict]:
    """
    Retrieve using multiple query variants, deduplicate and fuse.
    """
    # Generate query variants
    variants = call_llm_json(
        MULTI_QUERY_PROMPT.format(question=question, domain=domain, n=n_queries)
    )

    all_results = []
    seen_ids = set()

    for query in variants:
        embedding = embed(query)
        results = retriever.query(embedding=embedding, top_k=top_k_per_query)
        for r in results:
            if r["chunk_id"] not in seen_ids:
                all_results.append(r)
                seen_ids.add(r["chunk_id"])

    # Re-rank the deduplicated pool
    return rerank(question, all_results, top_n=top_k_per_query)
```

---

## Pattern 4: Cross-Encoder Re-ranking

Your bi-encoder retriever is fast but approximate. Your re-ranker is slow but accurate.
Use both — retrieve wide, re-rank narrow.

```python
# Option A: API-based re-ranking (Cohere, Jina)
import cohere

co = cohere.Client("your-api-key")

def rerank_with_cohere(
    query: str,
    results: list[dict],
    top_n: int = 5
) -> list[dict]:
    docs = [r["content"] for r in results]

    reranked = co.rerank(
        query=query,
        documents=docs,
        top_n=top_n,
        model="rerank-english-v3.0"
    )

    return [
        {**results[r.index], "rerank_score": r.relevance_score}
        for r in reranked.results
    ]


# Option B: Local cross-encoder (sentence-transformers)
from sentence_transformers import CrossEncoder

cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank_local(
    query: str,
    results: list[dict],
    top_n: int = 5
) -> list[dict]:
    pairs = [(query, r["content"]) for r in results]
    scores = cross_encoder.predict(pairs)

    scored = [(score, result) for score, result in zip(scores, results)]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {**result, "rerank_score": float(score)}
        for score, result in scored[:top_n]
    ]
```

**Latency profile:**
- Cohere rerank API: ~100–300ms for 20 docs
- Local MiniLM cross-encoder: ~50–150ms for 20 docs (GPU), ~300–800ms (CPU)
- Always async; never in the synchronous path if latency is critical

---

## Pattern 5: Contextual Compression

After retrieval, compress each chunk to only the parts relevant to the query.
Reduces noise in the context window and improves generation quality.

```python
COMPRESSION_PROMPT = """Given this query and document chunk, extract only the
sentences or phrases directly relevant to answering the query.
If nothing is relevant, return empty string.
Preserve exact wording — do not paraphrase.

QUERY: {query}
CHUNK: {chunk}

Return only the relevant excerpt, nothing else."""


def compress_retrieved_chunks(
    query: str,
    chunks: list[dict],
    min_relevance_tokens: int = 20
) -> list[dict]:
    """
    Filter each chunk down to query-relevant content only.
    Dramatically reduces context window usage.
    """
    compressed = []
    for chunk in chunks:
        relevant_excerpt = call_llm(
            COMPRESSION_PROMPT.format(query=query, chunk=chunk["content"])
        ).strip()

        if relevant_excerpt and count_tokens(relevant_excerpt) >= min_relevance_tokens:
            compressed.append({
                **chunk,
                "content": relevant_excerpt,
                "original_content": chunk["content"],
                "was_compressed": True
            })

    return compressed
```

---

## Pattern 6: HR-Specific — Candidate-to-Role Matching

Structured retrieval for matching resumes to job descriptions.

```python
def match_candidates_to_role(
    jd_id: str,
    jd_requirements: list[str],
    vector_store,
    structured_db,
    top_k: int = 10
) -> list[dict]:
    """
    Two-phase matching: structured filter → semantic ranking.
    Phase 1: filter by required skills (exact match, fast)
    Phase 2: rank filtered candidates by semantic similarity (slow but accurate)
    """
    # Phase 1: Extract must-have skills and filter candidates
    must_have_skills = extract_must_have_skills(jd_requirements)

    candidate_pool = structured_db.query("""
        SELECT DISTINCT candidate_id
        FROM candidate_skills
        WHERE skill IN :required_skills
        GROUP BY candidate_id
        HAVING COUNT(DISTINCT skill) >= :min_match
    """, required_skills=must_have_skills, min_match=max(1, len(must_have_skills) // 2))

    if not candidate_pool:
        return []

    # Phase 2: Semantic ranking within the filtered pool
    jd_embedding = embed(" ".join(jd_requirements))

    results = vector_store.query(
        vector=jd_embedding,
        top_k=top_k,
        filter={"candidate_id": {"$in": [c["candidate_id"] for c in candidate_pool]},
                "section": "skills"}
    )

    return results


def extract_must_have_skills(requirements: list[str]) -> list[str]:
    """Extract hard-required skills from JD requirements list."""
    return call_llm_json(f"""From these job requirements, extract skills that are
    clearly mandatory (not 'nice to have'). Return as JSON array of skill strings,
    normalised to common names (e.g. 'JS' → 'JavaScript').
    REQUIREMENTS: {requirements}""")
```

---

## Evaluation Harness

Measure your retrieval pipeline before and after every change.

```python
from dataclasses import dataclass, field

@dataclass
class EvalQuery:
    query: str
    relevant_chunk_ids: list[str]
    query_type: str  # factual, procedural, entity_lookup, comparative


@dataclass
class RetrievalMetrics:
    hit_rate_at_1: float = 0.0
    hit_rate_at_3: float = 0.0
    hit_rate_at_5: float = 0.0
    mrr: float = 0.0
    precision_at_5: float = 0.0
    per_query_type: dict = field(default_factory=dict)


def evaluate_retrieval(
    retriever_fn,        # fn(query: str) -> list[dict] with chunk_ids
    eval_set: list[EvalQuery],
    k: int = 5
) -> RetrievalMetrics:
    """
    Run full evaluation of a retrieval pipeline against a labelled eval set.
    """
    hits_at_1, hits_at_3, hits_at_k = [], [], []
    reciprocal_ranks = []
    precisions_at_k = []
    type_results = {}

    for eq in eval_set:
        results = retriever_fn(eq.query)
        retrieved_ids = [r["chunk_id"] for r in results[:k]]
        relevant = set(eq.relevant_chunk_ids)

        # Hit Rate @K
        hits_at_1.append(any(rid in relevant for rid in retrieved_ids[:1]))
        hits_at_3.append(any(rid in relevant for rid in retrieved_ids[:3]))
        hits_at_k.append(any(rid in relevant for rid in retrieved_ids[:k]))

        # MRR
        rr = 0.0
        for rank, rid in enumerate(retrieved_ids, 1):
            if rid in relevant:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        # Precision @K
        precision = len([rid for rid in retrieved_ids if rid in relevant]) / k
        precisions_at_k.append(precision)

        # Per query type breakdown
        qtype = eq.query_type
        type_results.setdefault(qtype, {"hits": [], "rr": []})
        type_results[qtype]["hits"].append(hits_at_k[-1])
        type_results[qtype]["rr"].append(rr)

    metrics = RetrievalMetrics(
        hit_rate_at_1=sum(hits_at_1) / len(hits_at_1),
        hit_rate_at_3=sum(hits_at_3) / len(hits_at_3),
        hit_rate_at_5=sum(hits_at_k) / len(hits_at_k),
        mrr=sum(reciprocal_ranks) / len(reciprocal_ranks),
        precision_at_5=sum(precisions_at_k) / len(precisions_at_k),
        per_query_type={
            qt: {
                "hit_rate": sum(v["hits"]) / len(v["hits"]),
                "mrr": sum(v["rr"]) / len(v["rr"]),
                "n": len(v["hits"])
            }
            for qt, v in type_results.items()
        }
    )

    return metrics


def print_eval_report(metrics: RetrievalMetrics):
    print(f"{'Metric':<25} {'Score':>8}")
    print("-" * 35)
    print(f"{'Hit Rate @1':<25} {metrics.hit_rate_at_1:>8.1%}")
    print(f"{'Hit Rate @3':<25} {metrics.hit_rate_at_3:>8.1%}")
    print(f"{'Hit Rate @5':<25} {metrics.hit_rate_at_5:>8.1%}")
    print(f"{'MRR':<25} {metrics.mrr:>8.3f}")
    print(f"{'Precision @5':<25} {metrics.precision_at_5:>8.1%}")
    print()
    print("Per Query Type:")
    for qt, scores in metrics.per_query_type.items():
        print(f"  {qt:<20} hit={scores['hit_rate']:.1%}  mrr={scores['mrr']:.3f}  n={scores['n']}")
```

---

## Retrieval Debugging Guide

When retrieval is returning wrong results, diagnose systematically:

```
STEP 1: Is the right chunk even in the index?
  → Search by chunk_id directly. If missing → ingestion bug.

STEP 2: Is the embedding capturing the right meaning?
  → Embed the query, find nearest neighbours.
  → Do the top-10 nearest chunks make sense semantically?
  → If not → try a different embedding model or query rewriting.

STEP 3: Is BM25 finding it?
  → Run keyword-only search for the core terms.
  → If BM25 finds it but dense doesn't → vocabulary mismatch → use hybrid.

STEP 4: Is the chunk too long?
  → Chunks >512 tokens embed poorly (embedding models have input limits).
  → Check your max chunk size against your embedding model's context window.

STEP 5: Is the metadata filter too restrictive?
  → Remove all filters, run the raw semantic query.
  → If the right chunk now appears → your filter is over-constraining.

STEP 6: Is the re-ranker downgrading the right chunk?
  → Check scores before and after re-ranking.
  → If re-ranker drops the right chunk → it's a re-ranker calibration issue.
```
