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