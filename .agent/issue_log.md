# Issue Log

This file is maintained automatically by the agent after every fix.
Do not edit manually unless correcting an error.

## Format
Each entry uses this structure:

---
**ID**: ISSUE-001  
**Date**: YYYY-MM-DD  
**Symptom**: What the user reported or what broke  
**Root cause**: What was actually wrong  
**Skill consulted**: e.g. `backend-api-orchestration`  
**Fix applied**: Short description of what changed  
**Files changed**: list of files  
**Recurrence**: 0  
**Self-heal triggered**: No  
---

## Log
---
**ID**: ISSUE-001  
**Date**: 2026-03-19  
**Symptom**: White screen after joining meeting room.  
**Root cause**: Component returned null on DISCONNECTED status and polling stopped.  
**Skill consulted**: `frontend-interview-ui`  
**Fix applied**: Updated `getViewState` to handle DISCONNECTED, added Reconnecting UI, and fixed polling logic.  
**Files changed**: `InterviewRoom.jsx`, `.env`  
**Recurrence**: 0  
**Self-heal triggered**: No  
---
**ID**: ISSUE-002  
**Date**: 2026-03-20  
**Symptom**: AI voice not heard and candidate audio not capturing on Oracle Cloud.  
**Root cause**: Edge-TTS returned 403 Forbidden (datacenter block) and MediaRecorder mimeType mismatch.  
**Skill consulted**: `voice-speech-integration`, `frontend-interview-ui`  
**Fix applied**: Added Browser TTS fallback, hardened MediaRecorder cycle, and added diagnostic telemetry.  
**Files changed**: `InterviewRoom.jsx`, `main.py`, `README.md`, `CHANGELOG.md`  
**Recurrence**: 0  
**Self-heal triggered**: No  
---
**ID**: ISSUE-003  
**Date**: 2026-03-21  
**Symptom**: AI responding twice; garbage text in transcript.  
**Root cause**: Duplicate WebSocket sends in frontend; VAD too sensitive.  
**Skill consulted**: `voice-speech-integration`  
**Fix applied**: Removed redundant `ws.send`, increased VAD threshold to 6, and added backend dedup.  
**Files changed**: `InterviewRoom.jsx`, `main.py`  
**Recurrence**: 0  
**Self-heal triggered**: No  
---
**ID**: ISSUE-004  
**Date**: 2026-03-21  
**Symptom**: Backend RuntimeError: "Cannot call 'receive' once a disconnect message has been received."  
**Root cause**: WebSocket receiver loop not gracefully catching disconnect exceptions during greeting phase; send operations missing guards.  
**Skill consulted**: `backend-api-orchestration`  
**Fix applied**: Wrapped ALL WebSocket operations (`receive`, `send_json`, `send_bytes`) in `try...except (WebSocketDisconnect, RuntimeError)`.  
**Files changed**: `main.py`  
**Recurrence**: 1  
**Self-heal triggered**: Yes (Patched `backend-api-orchestration` skill)  
---
**ID**: ISSUE-005  
**Date**: 2026-03-20  
**Symptom**: Backend container stuck on "unhealthy" status on Oracle Cloud.  
**Root cause**: Heavy top-level Python imports (ChromaDB, LangGraph, Whisper) blocked uvicorn startup for 60-90s, exceeding Docker healthcheck timeout. Multiple failed fix attempts before identifying the true import chain + healthcheck budget interaction.  
**Skill consulted**: `senior-ai-architect`, `backend-api-orchestration`  
**Fix applied**: (1) Moved heavy imports inside function bodies. (2) Added `start_period: 120s` to Docker healthcheck. (3) Changed healthcheck to `/health` endpoint.  
**Files changed**: `main.py`, `docker-compose.yml`  
**Recurrence**: 0  
**Self-heal triggered**: Yes — multiple failed fix attempts before root cause found. Required full architect-level audit.  
**Lessons**: Always trace the FULL import chain. Docker `start_period` is the correct lever for slow-starting apps, not longer intervals.  
---
**ID**: ISSUE-006  
**Date**: 2026-03-22  
**Symptom**: After ISSUE-002 recurrence fix, mic stuck on IDLE indefinitely.  
**Root cause**: **Agent-introduced regression.** The original `audio_failed` handler correctly set `isAISpeaking = false`, which unblocked the mic (verified working — console showed `[VAD] 👂 Hearing something...`). Agent changed the handler to call `window.speechSynthesis.speak()` which set `isAISpeaking = true`. Browser `speechSynthesis` is unreliable — `onend` event may never fire on many browsers/environments → `isAISpeaking` stays `true` forever → mic permanently blocked.  
**Skill consulted**: None (agent acted without consulting)  
**Fix applied**: Implemented `_speakWithSafetyNet` helper in `InterviewRoom.jsx` with a hard text-length-based timeout guard (CORE Rule #7). This ensures `isAISpeaking` always returns to `false` within a bounded time, even if `window.speechSynthesis` hangs.  
**Files changed**: `InterviewRoom.jsx`  
**Recurrence**: 0  
**Self-heal triggered**: Yes  
**Agent anti-patterns identified**:  
1. **Changed working code the user didn't ask to change.** The mic was working. The user only reported AI voice not playing. Agent should have ONLY fixed the voice, not touched the mic-unblocking logic.  
2. **Introduced unreliable API in critical path without timeout guard.** `window.speechSynthesis` is notoriously unreliable. Should never gate mic activation on its completion without a hard timeout fallback.  
3. **Did not verify the original behavior was preserved.** Before my fix, `audio_failed` → mic works. After my fix, `audio_failed` → mic broken. A simple side-by-side analysis would have caught this.  
4. **Scope creep.** User asked to fix "AI not asking questions". Agent expanded scope to refactor the entire audio_failed flow.  
---
**ID**: ISSUE-007  
**Date**: 2026-03-22  
**Symptom**: Mic and VAD Status remain IDLE after AI greeting.  
**Root cause**: Recording trigger was only tied to `isAISpeaking` transitions. If the mic wasn't ready when the greeting finished, the recording cycle was never started.  
**Skill consulted**: `frontend-interview-ui`  
**Fix applied**:
- [x] ISSUE-007: Fix Mic/VAD IDLE state at start
- [x] ISSUE-008: Fix Dashboard Refresh Loop (HMR)
- [x] ISSUE-009: Prevent Double AI Voice (TTS + Binary overlap)
- [x] ISSUE-013: Fix Button Interactivity (Leave/Cancel)
- [x] ISSUE-014: Fix 15-minute Session Timeout
- [x] Finalize Walkthrough & Logs
- [x] Push to Git for Server Testing
**Files changed**: `InterviewRoom.jsx`, `vite.config.js`
**Recurrence**: 1  
**Self-heal triggered**: No  
---
**ID**: ISSUE-008  
**Date**: 2026-03-22  
**Symptom**: Dashboard page keeps refreshing every few seconds, wiping form data.  
**Root cause**: Hardcoded production HMR host in `vite.config.js` caused constant WebSocket failures and full-page reloads in local development.  
**Skill consulted**: `devops-deployment`  
**Fix applied**: Commented out the production HMR host in `vite.config.js`.  
**Files changed**: `vite.config.js`  
**Recurrence**: 0  
**Self-heal triggered**: No  
---
**ID**: ISSUE-013  
**Date**: 2026-03-22  
**Symptom**: "Leave Interview" and "Cancel" buttons reported as non-functional/stuck.  
**Root cause**: Reliance on `window.confirm` and `window.location.href`, which can be unreliable or blocked in certain browser contexts.  
**Skill consulted**: `frontend-interview-ui`  
**Fix applied**:  
1. **Removed `window.confirm`**: Replaced blocking browser dialogs with a two-step "Click-to-Confirm" UI pattern (e.g., "Leave" → "Confirm Exit?") in both `InterviewRoom.jsx` and `Dashboard.jsx`. This eliminates the risk of browser-level dialog blocking.
2. **Transitioned to `useNavigate`**: Switched to React Router's `useNavigate` for more reliable routing without full page reloads.
3. **Explicit Socket Cleanup**: Added direct `ws.close()` calls in the room exit handler.
4. **Enhanced UI Feedback**: Added diagnostic logging and a dedicated CSS class (`.btn-warning`) for the confirmation state.
**Files changed**: `InterviewRoom.jsx`, `Dashboard.jsx`  
**Recurrence**: 0  
**Self-heal triggered**: No  
---
**ID**: ISSUE-009  
**Date**: 2026-03-22  
**Symptom**: Hearing two AI voices simultaneously (overlapping).  
**Root cause**: Race condition where the browser TTS fallback was not cancelled when actual binary audio arrived.  
**Skill consulted**: `frontend-interview-ui`  
**Fix applied**: 
1. Increased fallback timeout to 5000ms (to accommodate slow Oracle Cloud inference).
2. Added `clearTimeout(ttsFallbackTimerRef.current)` to the binary audio handler.
3. Added `window.speechSynthesis.cancel()` to the binary audio handler to immediately silence any overlapping fallback voice.
4. Added an `if (ttsFallbackTimerRef.current)` guard inside the timeout callback to prevent late triggers.
**Files changed**: `InterviewRoom.jsx`  
**Recurrence**: 0  
**Self-heal triggered**: No  
---