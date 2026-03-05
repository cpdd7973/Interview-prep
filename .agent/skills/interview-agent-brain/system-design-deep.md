---
name: system-design-deep
description: Component-by-component system design interview guidance. Covers databases, caching, queues, API design, capacity estimation, failure modes, and signal notes for classic problems like Twitter feed, URL shortener, and distributed cache.
---

# System Design Deep Reference

Marcus's component-by-component guidance for conducting and evaluating system design interviews.

---

## How Marcus Runs a System Design Interview

### Time Budget (45 min)
```
0–5 min:   Requirements clarification (candidate drives)
5–10 min:  Capacity estimation
10–20 min: High-level architecture
20–35 min: Deep dive on 1–2 components
35–42 min: Trade-offs, failure modes, scaling
42–45 min: Candidate questions
```

If candidate spends >10 min on requirements without producing any design, nudge them:
> "Good — you've got the requirements. Let's start with a high-level sketch and we can
> refine as we go."

---

## Requirements Phase — What Marcus Listens For

**Functional requirements a strong candidate asks about:**
- Who are the users? What actions do they take?
- Read-heavy or write-heavy?
- What does success look like (latency? consistency? availability?)
- Any geographic distribution? Mobile clients?

**Non-functional a strong candidate raises unprompted:**
- Scale (DAU, QPS, data volume)
- Consistency model (eventual vs strong)
- Latency targets (P50/P99)
- Availability SLA

**Red flag:** Candidate skips requirements entirely and starts drawing boxes.
**Yellow flag:** Candidate over-specifies requirements for 20 minutes and never starts designing.

---

## Capacity Estimation

Don't require precision — require *order of magnitude* thinking and back-of-napkin comfort.

**Twitter Feed example:**
```
300M DAU × 20 requests/day = 6B reads/day = ~70K QPS read
300M DAU × 2 writes/day = 600M writes/day = ~7K QPS write
→ Read-heavy system, 10:1 ratio — candidate should note this

Average tweet: 300 bytes
7K writes/sec × 300 bytes = 2.1 MB/sec → ~180 GB/day new data
5 years retention: ~330 TB → object storage + tiered archival
```

**What to look for:**
- Comfortable with rough numbers, doesn't need a calculator
- Uses estimates to drive architectural decisions
- Flags when their estimate changes the design (e.g., "at this scale, we need sharding")

---

## Core Components — Deep Guidance

### Load Balancers
**What a strong candidate knows:**
- L4 vs L7 load balancing trade-offs
- Algorithms: round-robin, least connections, consistent hashing
- Health checks and circuit breaking
- When to use a CDN in front of the LB

**Common miss:** Treating load balancer as magic box without considering session affinity, sticky sessions, or what happens when an LB node fails.

---

### Databases

**Strong candidates distinguish between:**

| Scenario | Choice | Why |
|---|---|---|
| ACID transactions, relations | PostgreSQL / MySQL | Strong consistency, joins |
| High write throughput, flexible schema | Cassandra / DynamoDB | Wide-column, eventual consistency |
| Low-latency key lookups | Redis | In-memory, O(1) |
| Full-text search | Elasticsearch | Inverted index, relevance scoring |
| Time-series data | InfluxDB / TimescaleDB | Optimized for time-range queries |
| Blob/media storage | S3 / GCS | Object store, CDN-friendly |

**Red flag:** Using PostgreSQL for everything without acknowledging trade-offs at scale.
**Also a red flag:** Using NoSQL for everything to seem "scalable."

**Follow-up probes:**
- "How would you handle a hot partition in Cassandra?"
- "When would you choose eventual consistency over strong consistency here?"
- "Walk me through how you'd handle a database migration with zero downtime."

---

### Caching

**Layer candidates should know:**
```
Browser cache → CDN → API Gateway cache → Application cache (Redis) → DB query cache
```

**Cache invalidation is the hard part.** Ask:
> "When a user updates their profile, how do you make sure cached profile data is invalidated
> across all layers?"

**Strong answer:** Write-through vs write-behind vs cache-aside pattern explained with trade-offs, TTL strategy, cache warming approach.

**Follow-up:** "Your cache hit rate is 80%. What drives the remaining 20% misses and how do you reduce them?"

---

### Message Queues

**When a strong candidate reaches for a queue:**
- Async processing to decouple producers from consumers
- Rate-limiting/backpressure between services
- Fan-out (one event → multiple consumers)
- Retry and dead-letter queue handling

**Kafka vs SQS vs RabbitMQ — what they should know:**

| | Kafka | SQS | RabbitMQ |
|---|---|---|---|
| Retention | Long-term (days/forever) | Short (14 days max) | Until consumed |
| Ordering | Per-partition | Best effort (FIFO queue option) | Per-queue |
| Throughput | Very high | High | Moderate |
| Use case | Event streaming, audit log | Task queues, decoupling | Complex routing |

**Follow-up probe:** "A consumer is processing messages too slowly and the queue is backing up. What are your options?"

---

### API Design

**REST vs GraphQL vs gRPC — strong candidates know when each wins:**
- REST: Standard CRUD, external APIs, broad ecosystem compatibility
- GraphQL: Variable query shapes, client-driven data fetching, reduces over-fetching
- gRPC: Internal microservices, high-throughput, strong typing, streaming support

**What to probe:**
> "You've got a mobile app and a web app both hitting your API but needing different
> data shapes. How do you handle that without duplicating endpoints?"

---

## Common System Design Problems — Marcus's Signal Notes

### URL Shortener
**Core challenge:** Hash collision, redirect performance, analytics
**What separates good from great:** Custom aliases, expiration, click tracking without hot-row contention, geographic redirect

### Twitter Feed / News Feed
**Core challenge:** Fan-out on write vs read
**Signal moment:** "At what follower count does fan-out-on-write break, and how do you handle celebrities?"
**Strong answer:** Hybrid model — precompute for normal users, pull for high-follower accounts

### Notification System
**Core challenge:** Multi-channel delivery (push/email/SMS), deduplication, prioritization
**What to probe:** "How do you handle a notification that fails to deliver? Retry strategy?"
**Strong answer:** Idempotency keys, exponential backoff, dead-letter queue, user preference service

### Distributed Cache (Redis-like)
**Core challenge:** Consistent hashing for nodes, eviction policies, replication
**Signal moment:** Can they explain consistent hashing with virtual nodes without prompting?
**Strong answer:** Handles node addition/removal gracefully, discusses LRU vs LFU eviction

### Search Autocomplete
**Core challenge:** Low latency (<100ms), real-time updates, personalization
**Architecture:** Trie in-memory or Elasticsearch prefix queries, tiered caching, A/B testing infrastructure
**What to probe:** "How do you handle trending queries that weren't popular yesterday?"

---

## Failure Mode Questions — Marcus's Favorites

These reveal whether a candidate thinks in production realities, not just happy paths:

1. "Your primary database goes down. Walk me through what happens to your system."
2. "A deployment pushes bad code and your error rate spikes to 30%. How does your system respond?"
3. "One of your microservices starts responding in 10 seconds instead of 10ms. What's your blast radius?"
4. "Your cache is cold after a restart. What happens to your database?"
5. "A third-party payment provider has an outage. How does your checkout flow degrade gracefully?"

**Strong candidates:** Have answers for at least 3 of these. Use terms like circuit breaker, bulkhead, graceful degradation, retry budget, fallback.
**Weak candidates:** Haven't thought past the happy path.

---

## Staff / Principal Level Additions

For L6+ candidates, push beyond component selection into:

- **Data model design:** "Show me the schema. Now walk me through a complex query — what's your index strategy?"
- **Cross-system consistency:** "Your order service and inventory service need to stay consistent. You can't use a distributed transaction. How?"
- **Organizational impact:** "Three other teams will need to integrate with this system. How do you design the API contract and what's your versioning strategy?"
- **Build vs buy decisions:** "You could use Kafka or SQS here. Walk me through how you'd make that decision for this org, not just this system."

Staff-level signal is less about knowing the right answer and more about structuring ambiguous decisions with clear trade-off reasoning and awareness of org constraints.
