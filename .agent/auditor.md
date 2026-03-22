# Agent Auditor

Called by the orchestrator before finalizing any change.
Never skips. Never self-certifies (the agent that made the change cannot audit itself — re-read the diff as if you are a separate reviewer).

---

## Step 1: Classify the change risk

| Risk level | Criteria |
|---|---|
| **Low** | Single file changed, no core_rules surface area, no API/DB/auth touch |
| **Medium** | Multiple files changed, OR touches API, DB, auth, or a skill |
| **High** | Changes `core_rules.md`, any `SKILL.md`, schema, PII handling, or WebSocket logic |

---

## Step 2: Run the appropriate checklist

### Low-risk — quick scan (3 checks)
- [ ] Change does what the prompt asked and nothing more
- [ ] No new `logger.info()` or `print()` containing candidate data (Rule 5)
- [ ] Doc sync was actually performed, not just claimed

### Medium-risk — standard audit (all of the above plus)
- [ ] No synchronous IO introduced in async context (Rule 1)
- [ ] No raw unbounded string passed to an LLM prompt (Rule 2)
- [ ] At least 2 failure modes handled in any new critical function (Rule 3)
- [ ] State transitions use granular states or timestamps (Rule 4)
- [ ] Change does not conflict with any file touched in the last 3 issue_log entries
- [ ] The fix matches what the consulted skill actually prescribes — not a paraphrase of it

### High-risk — full audit (all of the above plus)
- [ ] Change to `core_rules.md` or a `SKILL.md` does not contradict existing rules
- [ ] Schema change has a corresponding migration or rollback note in `CHANGELOG.md`
- [ ] PII handling change reviewed against Rule 5 explicitly
- [ ] Self-healer patch (if applied) is additive — original skill content is intact
- [ ] At least one alternative approach was considered and ruled out (note it briefly)

---

## Step 3: Produce an audit verdict

Write the verdict inline in the issue log entry under a new field:
```
**Audit**: PASS | FAIL | PASS-WITH-WARNING
**Risk level**: Low | Medium | High
**Checks failed**: (list any failed checks, or "none")
**Warning**: (optional — note anything that passed but smells off)
```

---

## Step 4: On FAIL — block and fix

- Do NOT write the changelog entry
- Do NOT mark the issue log entry complete
- Return to the orchestrator at Step 3 (Execute the change) with the failed checks as constraints
- Re-audit after the fix. If it fails twice, escalate to self_healer.md

## Step 5: On PASS-WITH-WARNING

- Proceed but append the warning to `CHANGELOG.md` alongside the entry
- Flag the issue_log entry with `Needs-review: Yes` for human follow-up