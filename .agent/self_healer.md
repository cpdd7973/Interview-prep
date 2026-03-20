# Self-Healing Protocol

Triggered when: an issue in `issue_log.md` has `Recurrence >= 2`
OR when a fix was applied but the same symptom reappears in the next prompt.

## Self-heal steps

1. **Identify the failing skill** — which SKILL.md was consulted for the repeated issue?

2. **Analyze the gap** — what assumption in that skill's instructions was wrong?
   Write a brief diagnosis in `.agents/skill_patches.md`.

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