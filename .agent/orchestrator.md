# Agent Orchestrator

## On every prompt, follow this sequence — no exceptions:

### Step 1: Skill consultation
Before writing any code or fixing any bug, scan `.agent/skills/` and identify
which skill(s) apply to this task. Read the relevant SKILL.md. If none apply,
note that explicitly.

### Step 2: Issue memory check
Read `.agent/issue_log.md`. If this problem or a similar one has been seen
before, apply the recorded solution first. If the previous fix failed, escalate
to self-healing (Step 6).

### Step 3: Execute the change
Apply the fix or feature using guidance from the consulted skill(s).

### Step 4: Audit — MANDATORY before proceeding
Read `.agent/auditor.md` in full.
Classify the risk level of the change just made.
Run the appropriate checklist as a separate reviewer — not as the agent that wrote the change.

- If verdict is **FAIL**: stop, fix, re-audit. Do not proceed to Step 5.
- If verdict is **PASS-WITH-WARNING**: proceed but flag in changelog and issue log.
- If verdict is **PASS**: continue.

Append the audit result to `.agent/audit_log.md`.

### Step 5: Doc sync
After audit passes, update ALL affected docs:
- `README.md` — if public API, setup, or usage changed
- `docs/ARCHITECTURE.md` — if structure or data flow changed
- `docs/API.md` — if endpoints or interfaces changed
- Any other `.md` file whose content is now stale

### Step 6: Record to issue log
Append an entry to `.agent/issue_log.md` including the audit verdict field.

### Step 7: Write changelog entry
Append to `CHANGELOG.md` using Keep a Changelog format.
Include any PASS-WITH-WARNING notes.

### Step 8: Self-heal check
If this issue has `Recurrence >= 2` OR the audit failed twice on the same change,
trigger `.agent/self_healer.md`.