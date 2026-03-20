# Agent Orchestrator

## On every prompt, follow this sequence — no exceptions:

### Step 1: Skill consultation
Before writing any code or fixing any bug, scan `.agents/skills/` and identify
which skill(s) apply to this task. Read the relevant SKILL.md. If none apply,
note that explicitly.

### Step 2: Issue memory check
Read `.agents/issue_log.md`. If this problem or a similar one has been seen
before, apply the recorded solution first. If the previous fix failed, escalate
to self-healing (Step 5).

### Step 3: Execute the change
Apply the fix or feature using guidance from the consulted skill(s).

### Step 4: Doc sync (automatic after every change)
After any code change, update ALL of the following that are affected:
- `README.md` — if public API, setup, or usage changed
- `docs/ARCHITECTURE.md` — if structure or data flow changed
- `docs/API.md` — if endpoints or interfaces changed
- Any other `.md` file whose content is now stale

### Step 5: Record to issue log
Append an entry to `.agents/issue_log.md` in the standard format.

### Step 6: Write changelog entry
Append to `CHANGELOG.md` using Keep a Changelog format.