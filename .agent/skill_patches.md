# Skill Patches

This file records skill-level corrections identified during self-healing.
Each patch corresponds to an issue in `issue_log.md` and an Amendment in the
relevant SKILL.md.

---

## Patch 001 — 2026-03-21
**Issue**: ISSUE-004  
**Skill**: `backend-api-orchestration`  
**Gap**: Skill did not mention that WebSocket operations must be individually
guarded against disconnects during long-running async tasks.  
**Amendment added**: Yes — appended to end of `backend-api-orchestration/SKILL.md`.

---

## Patch 002 — 2026-03-22
**Issue**: ISSUE-006  
**Skill**: None consulted (root cause of the regression)  
**Gap**: Agent did not consult any skill before modifying the `audio_failed`
handler. Had the agent consulted `voice-speech-integration` or
`frontend-interview-ui`, Priya/Kai's guidance about fallback reliability
and state flag safety would have prevented the regression.  
**CORE_RULES amended**: Yes — Rules #6 (Minimal Blast Radius) and #7 (Browser
API Timeout Guards) added.  
**Self-healer amended**: Yes — Pre-Fix Checklist added.
