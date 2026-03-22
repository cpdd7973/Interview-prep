# Self-Healing Protocol

Triggered when: an issue in `issue_log.md` has `Recurrence >= 2`
OR when a fix was applied but the same symptom reappears in the next prompt.

## Self-heal steps

1. **Identify the failing skill** — which SKILL.md was consulted for the repeated issue?

2. **Analyze the gap** — what assumption in that skill's instructions was wrong?
   Write a brief diagnosis in `.agent/skill_patches.md`.

3. **Patch the skill** — append an "Amendment" section at the bottom of the
   relevant SKILL.md with the corrected guidance. Do NOT delete original content.
   Format:
```
   ## Amendment — {date}
   **Issue addressed**: ISSUE-XXX  
   **Correction**: {what was wrong and what the right approach is}
```

4. **Update the issue log** — set `Self-heal triggered: Yes` and note the skill patched.

5. **Re-attempt the fix** using the patched skill guidance.

## Pre-Fix Checklist (MANDATORY before every code change)

Added after ISSUE-006 regression analysis (2026-03-22).

Before writing ANY fix, the agent MUST answer these questions:

1. **Scope check:** "What EXACTLY did the user report as broken?" — Only fix THAT.
2. **Side-effect check:** "Does the code I'm changing currently work for ANOTHER purpose?" — If yes, DO NOT alter the working behavior. Add alongside, don't replace.
3. **Exit condition check:** "After my change, does every code path still reach a safe terminal state?" — For state flags like `isAISpeaking`, verify every branch sets it to `false` eventually, including error paths and API failures.
4. **Reliability check:** "Am I introducing a dependency on an unreliable API in a critical path?" — If so, add a hard timeout safety net.
5. **Regression check:** "Before my fix, what happened when the user did X? After my fix, does that SAME flow still work?" — Document the before/after explicitly.