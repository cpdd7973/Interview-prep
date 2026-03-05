---
name: chunking-deep
description: Detailed chunking algorithms, token boundary handling, overlap strategies, and validation patterns for RAG pipelines. Covers QA-pair, section-based, entity-aware, hierarchical, and sliding window strategies with production Python implementations.
---

# Chunking Deep Reference

Sofia's detailed implementation guide for every chunking strategy — with real code,
edge case handling, and validation patterns.

---

## The Golden Rule of Chunking

> A chunk must be independently meaningful to the query that will retrieve it.
> If you need to read the surrounding chunks to understand this one, it's a bad chunk.

Test every chunking strategy against this rule before indexing.

---

## Token Counting — Always Use Tokens, Never Characters

```python
import tiktoken

# Use the encoder that matches your embedding model
# For OpenAI models: cl100k_base
# For most others: cl100k_base is a safe approximation
ENCODER = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(ENCODER.encode(text))

def truncate_to_tokens(text: str, max_tokens: int) -> str:
    tokens = ENCODER.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return ENCODER.decode(tokens[:max_tokens])
```

**Why not characters?**
- "AWS" = 1 token. "antidisestablishmentarianism" = 6 tokens.
- A 1000-char chunk of technical text ≈ 200 tokens.
- A 1000-char chunk of prose ≈ 250 tokens.
- Character limits produce wildly inconsistent chunk sizes.

---

## Strategy 1: QA-Pair Chunking

For structured FAQs and support documentation with extractable Q&A pairs.

```python
import re
from dataclasses import dataclass

@dataclass
class QAChunk:
    chunk_id: str
    question: str
    answer: str
    token_count: int
    metadata: dict

def chunk_faq_document(
    text: str,
    source_id: str,
    max_answer_tokens: int = 400
) -> list[QAChunk]:
    """
    Parse FAQ document into individual QA pair chunks.
    Handles both structured (Q:/A: prefixed) and unstructured formats.
    """
    chunks = []

    # Strategy A: Explicit Q/A markers
    qa_pattern = re.compile(
        r'(?:^|\n)(?:Q:|Question:)\s*(.+?)(?:\n)(?:A:|Answer:)\s*(.+?)(?=\n(?:Q:|Question:)|\Z)',
        re.DOTALL | re.IGNORECASE
    )
    matches = qa_pattern.findall(text)

    if matches:
        for i, (question, answer) in enumerate(matches):
            question = question.strip()
            answer = answer.strip()

            # Truncate overly long answers — split into sub-chunks if needed
            if count_tokens(answer) > max_answer_tokens:
                answer = truncate_to_tokens(answer, max_answer_tokens)

            chunks.append(QAChunk(
                chunk_id=f"{source_id}_qa_{i:04d}",
                question=question,
                answer=answer,
                token_count=count_tokens(question + " " + answer),
                metadata={
                    "source_id": source_id,
                    "chunk_type": "qa_pair",
                    "qa_index": i
                }
            ))
    else:
        # Strategy B: LLM extraction for unstructured docs
        # (Delegate to extract_qa_pairs() in main SKILL.md)
        pass

    return chunks


def validate_qa_chunks(chunks: list[QAChunk]) -> dict:
    """Quality checks on extracted QA chunks."""
    issues = []
    for c in chunks:
        if count_tokens(c.question) < 5:
            issues.append(f"{c.chunk_id}: question too short ({c.question!r})")
        if count_tokens(c.answer) < 10:
            issues.append(f"{c.chunk_id}: answer too short — may be a parsing error")
        if count_tokens(c.answer) > 450:
            issues.append(f"{c.chunk_id}: answer near token limit — consider splitting")
    return {
        "total_chunks": len(chunks),
        "issues": issues,
        "avg_question_tokens": sum(count_tokens(c.question) for c in chunks) / max(len(chunks), 1),
        "avg_answer_tokens": sum(count_tokens(c.answer) for c in chunks) / max(len(chunks), 1),
    }
```

---

## Strategy 2: Section-Based Chunking (Job Descriptions)

```python
import re
from typing import Optional

# Common JD section header patterns
JD_HEADER_PATTERNS = [
    r'^(?:About the (?:Role|Job|Position)|Role Overview|Job Summary)',
    r'^(?:What You\'ll Do|Responsibilities|Key Responsibilities|Job Duties)',
    r'^(?:What We\'re Looking For|Requirements|Qualifications|Must.Have)',
    r'^(?:Nice to Have|Preferred|Bonus Points|Preferred Qualifications)',
    r'^(?:Compensation|Salary|Pay|What We Offer|Benefits)',
    r'^(?:About Us|About the Company|Who We Are)',
    r'^(?:Location|Work Environment|Remote|Hybrid)',
]

COMPILED_HEADERS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in JD_HEADER_PATTERNS]

def chunk_job_description_text(
    text: str,
    jd_id: str,
    min_section_tokens: int = 30,
    max_section_tokens: int = 500
) -> list[dict]:
    """
    Split JD into section-based chunks, preserving semantic boundaries.
    """
    # Find all header positions
    header_positions = []
    for pattern in COMPILED_HEADERS:
        for match in pattern.finditer(text):
            header_positions.append((match.start(), match.group().strip()))

    header_positions.sort(key=lambda x: x[0])

    if not header_positions:
        # Fallback: no clear headers — use paragraph-based splitting
        return chunk_by_paragraphs(text, jd_id, max_section_tokens)

    # Extract sections between headers
    chunks = []
    for i, (start, header) in enumerate(header_positions):
        end = header_positions[i + 1][0] if i + 1 < len(header_positions) else len(text)
        section_text = text[start:end].strip()

        token_count = count_tokens(section_text)
        if token_count < min_section_tokens:
            continue  # Skip near-empty sections

        # If section is too long, split at bullet boundaries
        if token_count > max_section_tokens:
            sub_chunks = split_section_at_bullets(section_text, jd_id, header, max_section_tokens)
            chunks.extend(sub_chunks)
        else:
            chunks.append({
                "chunk_id": f"{jd_id}_{slugify(header)}",
                "content": section_text,
                "token_count": token_count,
                "metadata": {
                    "jd_id": jd_id,
                    "section_header": header,
                    "chunk_type": "jd_section"
                }
            })

    return chunks


def split_section_at_bullets(
    text: str,
    jd_id: str,
    header: str,
    max_tokens: int
) -> list[dict]:
    """Split an oversized section at bullet point boundaries."""
    lines = text.split('\n')
    current_chunk_lines = []
    current_tokens = 0
    sub_chunks = []
    sub_index = 0

    for line in lines:
        line_tokens = count_tokens(line)
        if current_tokens + line_tokens > max_tokens and current_chunk_lines:
            sub_chunks.append({
                "chunk_id": f"{jd_id}_{slugify(header)}_p{sub_index}",
                "content": "\n".join(current_chunk_lines),
                "token_count": current_tokens,
                "metadata": {
                    "jd_id": jd_id,
                    "section_header": header,
                    "sub_index": sub_index,
                    "chunk_type": "jd_section_split"
                }
            })
            current_chunk_lines = [line]
            current_tokens = line_tokens
            sub_index += 1
        else:
            current_chunk_lines.append(line)
            current_tokens += line_tokens

    if current_chunk_lines:
        sub_chunks.append({
            "chunk_id": f"{jd_id}_{slugify(header)}_p{sub_index}",
            "content": "\n".join(current_chunk_lines),
            "token_count": current_tokens,
            "metadata": {
                "jd_id": jd_id,
                "section_header": header,
                "sub_index": sub_index,
                "chunk_type": "jd_section_split"
            }
        })

    return sub_chunks
```

---

## Strategy 3: Sliding Window Chunking

For dense technical documents where context must span chunk boundaries.

```python
def sliding_window_chunk(
    text: str,
    doc_id: str,
    chunk_size: int = 400,
    overlap: int = 80,
    respect_sentence_boundaries: bool = True
) -> list[dict]:
    """
    Sliding window chunking with configurable overlap.
    Sentence-boundary-aware when enabled.
    """
    if respect_sentence_boundaries:
        # Split into sentences first, then group into window-sized chunks
        sentences = split_into_sentences(text)
        return _chunk_sentences_with_overlap(sentences, doc_id, chunk_size, overlap)
    else:
        # Pure token-based sliding window
        tokens = ENCODER.encode(text)
        chunks = []
        start = 0
        chunk_index = 0

        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = ENCODER.decode(chunk_tokens)

            chunks.append({
                "chunk_id": f"{doc_id}_sw_{chunk_index:04d}",
                "content": chunk_text,
                "token_count": len(chunk_tokens),
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_index": chunk_index,
                    "start_token": start,
                    "end_token": end,
                    "chunk_type": "sliding_window"
                }
            })

            start += (chunk_size - overlap)
            chunk_index += 1

        return chunks


def split_into_sentences(text: str) -> list[str]:
    """Simple sentence splitter — use spacy or nltk for production."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]


def _chunk_sentences_with_overlap(
    sentences: list[str],
    doc_id: str,
    chunk_size: int,
    overlap_tokens: int
) -> list[dict]:
    chunks = []
    current_sentences = []
    current_tokens = 0
    chunk_index = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if current_tokens + sentence_tokens > chunk_size and current_sentences:
            # Emit chunk
            content = " ".join(current_sentences)
            chunks.append({
                "chunk_id": f"{doc_id}_sw_{chunk_index:04d}",
                "content": content,
                "token_count": current_tokens,
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_index": chunk_index,
                    "chunk_type": "sliding_window_sentence"
                }
            })
            chunk_index += 1

            # Keep overlap: retain sentences from the tail
            overlap_sentences = []
            overlap_count = 0
            for s in reversed(current_sentences):
                t = count_tokens(s)
                if overlap_count + t <= overlap_tokens:
                    overlap_sentences.insert(0, s)
                    overlap_count += t
                else:
                    break

            current_sentences = overlap_sentences + [sentence]
            current_tokens = overlap_count + sentence_tokens
        else:
            current_sentences.append(sentence)
            current_tokens += sentence_tokens

    # Emit final chunk
    if current_sentences:
        chunks.append({
            "chunk_id": f"{doc_id}_sw_{chunk_index:04d}",
            "content": " ".join(current_sentences),
            "token_count": current_tokens,
            "metadata": {
                "doc_id": doc_id,
                "chunk_index": chunk_index,
                "chunk_type": "sliding_window_sentence"
            }
        })

    return chunks
```

---

## Context Enrichment (Critical — Most Teams Skip This)

Raw chunks lose context when retrieved in isolation. Always enrich before indexing.

```python
def enrich_chunk_with_context(
    chunk: dict,
    document_summary: str,
    prev_chunk_summary: Optional[str] = None
) -> dict:
    """
    Prepend document-level and neighbouring context to chunk content.
    This dramatically improves retrieval relevance for mid-document chunks.
    """
    context_prefix = f"[Document context: {document_summary}]"
    if prev_chunk_summary:
        context_prefix += f" [Previous section: {prev_chunk_summary}]"

    enriched_content = f"{context_prefix}\n\n{chunk['content']}"

    return {
        **chunk,
        "content": enriched_content,
        "retrieval_content": chunk["content"],  # Store original for display
        "token_count": count_tokens(enriched_content)
    }
```

**Note:** Index `content` (enriched) for embedding, display `retrieval_content` (original)
to the user. Context enrichment improves embedding quality without polluting answers.

---

## Chunk Validation Checklist

Run before any indexing operation:

```python
def validate_chunk_set(chunks: list[dict], doc_id: str) -> dict:
    report = {
        "doc_id": doc_id,
        "total_chunks": len(chunks),
        "issues": [],
        "warnings": [],
        "stats": {}
    }

    token_counts = [c.get("token_count", count_tokens(c["content"])) for c in chunks]
    report["stats"] = {
        "min_tokens": min(token_counts),
        "max_tokens": max(token_counts),
        "avg_tokens": sum(token_counts) / len(token_counts),
        "total_tokens": sum(token_counts)
    }

    for c in chunks:
        tc = c.get("token_count", count_tokens(c["content"]))

        # Hard failures
        if tc < 20:
            report["issues"].append(f"{c['chunk_id']}: too short ({tc} tokens) — likely a parsing error")
        if tc > 600:
            report["issues"].append(f"{c['chunk_id']}: too long ({tc} tokens) — exceeds safe embedding range")
        if not c.get("metadata"):
            report["issues"].append(f"{c['chunk_id']}: missing metadata — cannot filter or attribute")

        # Warnings
        if tc < 50:
            report["warnings"].append(f"{c['chunk_id']}: very short ({tc} tokens) — may retrieve poorly")
        if "chunk_id" not in c:
            report["issues"].append("chunk missing chunk_id — cannot deduplicate or update")

    report["ready_to_index"] = len(report["issues"]) == 0
    return report
```

---

## Common Chunking Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Splitting mid-sentence | Retrieved chunks start/end abruptly | Use sentence-boundary-aware splitting |
| No overlap on sliding window | Queries spanning chunk boundary return nothing | 15–25% overlap of chunk size |
| Same strategy for all doc types | JD requirements mixed with company overview | Document-type-specific strategies |
| Stripping all whitespace | Bullet lists merge into prose | Preserve newlines within chunks |
| Not prepending section headers | "Python, AWS, Kubernetes" with no context | Always include section label in chunk content |
| Indexing boilerplate | "Equal opportunity employer" in every result | Strip standard boilerplate before chunking |
| No chunk length validation | Empty chunks or 2000-token monsters in index | Validate before every index operation |
