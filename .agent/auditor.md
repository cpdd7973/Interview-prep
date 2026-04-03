# Agent Auditor

Called by the orchestrator before finalizing any change.
Never skips. Never self-certifies (the agent that made the change cannot audit itself — re-read the diff as if you are a separate reviewer).

***

## Step 1: Classify the change risk

| Risk level | Criteria                                                                          |
| ---------- | --------------------------------------------------------------------------------- |
| **Low**    | Single file changed, no core\_rules surface area, no API/DB/auth touch            |
| **Medium** | Multiple files changed, OR touches API, DB, auth, or a skill                      |
| **High**   | Changes `core_rules.md`, any `SKILL.md`, schema, PII handling, or WebSocket logic |

***

## Step 2: Run the appropriate checklist



### Universal quality gate (runs on ALL risk levels before any other checks)

* [ ] If Python file changed: mentally run `black --check` — would it reformat anything?
  If yes, reformat before proceeding. This is a hard block.
* [ ] If Python file changed: any unused imports, bare `except:`, missing type annotations?
* [ ] If JS/TS file changed: any ESLint errors (not warnings)?
* [ ] No `print()` or `console.log()` in non-test, non-debug code

### Low-risk — quick scan (3 checks)

* [ ] Change does what the prompt asked and nothing more
* [ ] No new `logger.info()` or `print()` containing candidate data (Rule 5)
* [ ] Doc sync was actually performed, not just claimed

### Medium-risk — standard audit (all of the above plus)

* [ ] No synchronous IO introduced in async context (Rule 1)
* [ ] No raw unbounded string passed to an LLM prompt (Rule 2)
* [ ] At least 2 failure modes handled in any new critical function (Rule 3)
* [ ] State transitions use granular states or timestamps (Rule 4)
* [ ] Change does not conflict with any file touched in the last 3 issue\_log entries
* [ ] The fix matches what the consulted skill actually prescribes — not a paraphrase of it

### Python quality gate (runs on every Python file change)

* [ ] No line would be reformatted by `black --check`
  (check: long lines, inconsistent quotes, missing trailing commas)
* [ ] No Ruff violations — unused imports, undefined names, bare excepts
* [ ] All functions have type annotations including return type
* [ ] No bare `except:` — always `except SpecificError:`
* [ ] No `print()` statements in non-test files

### Node.js quality gate (runs on every JS/TS file change)

* [ ] No ESLint errors (warnings acceptable)
* [ ] No `console.log()` in production code paths

### High-risk — full audit (all of the above plus)

* [ ] Change to `core_rules.md` or a `SKILL.md` does not contradict existing rules
* [ ] Schema change has a corresponding migration or rollback note in `CHANGELOG.md`
* [ ] PII handling change reviewed against Rule 5 explicitly
* [ ] Self-healer patch (if applied) is additive — original skill content is intact
* [ ] At least one alternative approach was considered and ruled out (note it briefly)

### Security gate (runs on High-risk changes AND any change touching auth, DB, or LLM calls)

* [ ] New endpoint has auth middleware applied
* [ ] DB queries use parameterized queries — no f-string or + concatenation into SQL
* [ ] Candidate PII stripped before any external API call (Claude, Deepgram, ElevenLabs)
* [ ] No secrets, tokens, or API keys in any log statement or response body
* [ ] `.env` entries for any new secrets documented in `.env.example` (not `.env`)
* [ ] Session tokens have expiry configured
* [ ] `security_checklist.md` reviewed and signed off

***

## Step 3: Produce an audit verdict

Write the verdict inline in the issue log entry under a new field:

```
**Audit**: PASS | FAIL | PASS-WITH-WARNING
**Risk level**: Low | Medium | High
**Checks failed**: (list any failed checks, or "none")
**Warning**: (optional — note anything that passed but smells off)
```

***

## Step 4: On FAIL — block and fix

* Do NOT write the changelog entry
* Do NOT mark the issue log entry complete
* Return to the orchestrator at Step 3 (Execute the change) with the failed checks as constraints
* Re-audit after the fix. If it fails twice, escalate to self\_healer.md

## Step 5: On PASS-WITH-WARNING

* Proceed but append the warning to `CHANGELOG.md` alongside the entry
* Flag the issue\_log entry with `Needs-review: Yes` for human follow-up

