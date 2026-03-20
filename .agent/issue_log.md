# Issue Log

This file is maintained automatically by the agent after every fix.
Do not edit manually unless correcting an error.

## Format
Each entry uses this structure:

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