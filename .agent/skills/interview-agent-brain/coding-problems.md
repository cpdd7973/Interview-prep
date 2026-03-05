---
name: coding-problems
description: Curated coding problem bank for technical interviews, organized by difficulty. Includes signal notes, strong vs weak answer descriptions, and follow-up probes for each problem.
---

# Coding Problems Reference Bank

A curated set of problems Marcus uses, with signal notes and probing guidance.

---

## Easy / Warm-up

### Two Sum (variant)
> "Given an array of integers and a target, return the indices of two numbers that add up
> to the target. Now — what if the array is sorted? What if you need all pairs?"

**Signal to look for:**
- Brute force → hashmap → two-pointer progression shows problem-solving instinct
- Edge cases: duplicates, no solution, negative numbers

**Strong answer:** Hashmap O(n) immediately, explains trade-off (space vs time), handles edge cases unprompted
**Weak answer:** Only gives brute force, can't optimize when pushed

**Follow-up probe:** "What's your space complexity? Can we do this with O(1) space?"

---

### Valid Parentheses (variant)
> "Given a string of brackets, determine if it's valid. Now extend it — what if you want
> to return the minimum number of brackets to add to make it valid?"

**Signal:** Stack usage is table stakes. The extension tests if they can adapt.

**Follow-up probe:** "What if we also need to handle escaped characters inside strings?"

---

### Move Zeroes
> "Move all zeroes in an array to the end while preserving order of non-zero elements.
> Do it in-place."

**Signal:** Two-pointer pattern. Tests in-place manipulation without overthinking.

**Strong answer:** Single pass, two pointers, O(n) time O(1) space, explains why
**Red flag:** Creates a new array immediately without considering in-place constraint

---

## Medium

### LRU Cache
> "Design a data structure that implements a Least Recently Used cache with O(1) get and put."

**Signal:** This is a design + implementation problem. Tests doubly linked list + hashmap combo.

**What to listen for:**
- Do they think about the data structure before writing code?
- Do they explain why a doubly linked list (vs singly) is needed?
- Do they handle the eviction logic correctly?

**Follow-up probes:**
- "What happens under concurrent access?"
- "How would you make this thread-safe?"
- "Could you implement this without a built-in OrderedDict?"

---

### Meeting Rooms II
> "Given a list of meeting time intervals, find the minimum number of conference rooms required."

**Signal:** Sorting + min-heap or two-pointer. Tests if they can model a real-world problem.

**Strong answer:** Sort by start time, use min-heap tracking end times, O(n log n)
**Weak answer:** Brute force O(n²) comparison without recognizing the heap pattern

**Follow-up:** "What if meetings have priorities and you need to cancel the lowest-priority one?"

---

### Flatten Nested List Iterator
> "Implement an iterator that flattens a nested list of integers. Each element is either
> an integer or a list of integers (which can be nested arbitrarily deep)."

**Signal:** Tests recursion vs stack-based iteration thinking, lazy vs eager evaluation.

**Strong answer:** Uses a stack, avoids full pre-flattening, explains memory implications
**Follow-up:** "Why might a lazy iterator be preferable here at scale?"

---

### Binary Search on Answer
> "You have a list of packages with weights. Ships have a capacity limit. Find the minimum
> capacity needed to ship all packages within D days."

**Signal:** Tests whether candidates can recognize binary search applies to non-array problems.

**What to look for:**
- Do they identify the search space (max single weight → total weight)?
- Do they write a clean `canShip(capacity)` helper?
- Do they test boundary conditions?

---

## Hard

### Design a Rate Limiter (Hybrid Design/Code)
> "Implement a rate limiter that allows N requests per second per user. 
> Start with a single server, then scale to distributed."

**Signal:** This is a systems-thinking problem masquerading as a coding problem.

**Strong answer progression:**
1. Token bucket or sliding window counter — explains trade-offs
2. Redis-based distributed solution (atomic INCR + TTL or Lua script)
3. Handles race conditions, clock skew, Redis failure gracefully

**Follow-up probes:**
- "What happens if Redis goes down?"
- "How do you handle bursty traffic vs sustained load differently?"
- "Token bucket vs sliding window — when does each win?"

---

### Median of Two Sorted Arrays
> "Find the median of two sorted arrays in O(log(m+n)) time."

**Signal:** Binary search on partition. Tests comfort with hard algorithmic problems under pressure.

**What to watch:**
- Do they attempt it genuinely or give up early?
- Can they explain the partition concept even if the code isn't perfect?
- How do they handle odd vs even total length?

**Marcus's note:** This problem is less about getting it perfectly right and more about watching
someone engage with genuine difficulty. Candidates who think out loud and make progress
despite imperfection often outperform those who either nail it mechanically or shut down.

---

### Word Ladder
> "Given two words and a word list, find the shortest transformation sequence from
> begin to end where each step changes exactly one letter."

**Signal:** BFS pattern recognition. Tests graph thinking applied to strings.

**Strong answer:** BFS, bidirectional BFS optimization, preprocessed neighbor graph
**Follow-up:** "How would you handle a dictionary of 10 million words?"

---

## Problem Delivery Tips

- Always give a concrete example with input → output
- Don't mention the algorithm name or pattern in the problem statement
- Let silence sit for 30–60 seconds before probing — candidates need thinking time
- If they're stuck: "What would the brute force look like?" — not the answer
- If they're flying: throw the hardest follow-up you have

---

## What Interviewers Miss

1. **Testing behavior** — great engineers test proactively. Ask: "How would you test this?"
2. **Code readability** — messy variable names (`x`, `tmp`, `res2`) in an interview are a signal
3. **Talking through complexity** — don't accept "it's fast" — push for Big O analysis
4. **Handling wrong answers gracefully** — can they accept a correction and adapt?
