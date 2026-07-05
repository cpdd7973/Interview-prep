# CHECKLIST.md — Implementation Gates

Work through each gate in order for every implementation task. These gates are
the concrete content behind Steps 3–4 of `.agent/orchestrator.md`.

---

## Gate 1 — Plan (no code until documented)

Document briefly:

1. **Restate the request.** Is there a simpler solution? Is the change larger than necessary?
2. **Assumptions.** List them all. Never silently choose between interpretations. If agent-graph shape, session/state schema, auth (User vs Candidate), persistence, LLM prompt contracts, or MCP tool contracts depend on one — **stop and ask.**
3. **For bugs — root cause.** Never implement a fix before identifying the likely root cause. If unknown, state competing hypotheses and gather evidence first. No speculative fixes.
4. **Affected systems.** Which of these does the change touch: LangGraph nodes (`backend/agents/`), MCP servers (`backend/mcp_servers/`), DB models (`backend/database.py`), the interview WebSocket handler (`backend/main.py`), REST routes, frontend context/hooks/pages? Explicitly: what existing flow shares this state (`InterviewState`), this DB row, or this WebSocket message shape and could break?
5. **Acceptance criteria + verification plan.**
6. **Size.** Small (1–2 files, localized) → proceed. Medium (3–5 files, multiple layers) → proceed with care. Large (>5 files or graph/schema impact) → requires plan approval (per CLAUDE.md scope discipline).

---

## Gate 2 — Pre-Flight

- Run existing tests if the environment allows: `cd backend && pytest test_agent.py test_cancel.py test_voice.py test_ws_connection.py -v`.
  **Known gotcha:** `pytest.ini` sets `testpaths = tests`, but there is no `backend/tests/` directory — the test files live directly in `backend/`. Running bare `pytest` from `backend/` will silently collect nothing. Pass filenames explicitly (as above) or fix `pytest.ini` if you're touching test infra.
- Frontend: `cd frontend && npm run lint`.
- Report exact command, results, failures, untested areas. If tests can't run, say why. If unrelated-looking tests fail: stop and confirm they're unrelated before continuing.
- For bugs: reproduce first; write a failing test if practical; then fix.

---

## Gate 3 — Implement

- **Skill routing:**
  - `backend/agents/` (LangGraph nodes) → every LLM call's output goes through JSON extraction with a non-JSON fallback (see `extract_json` pattern); never assume the LLM returns clean JSON. State returned from a node must only add/update `InterviewState` keys it owns — check `state.py` before adding a new key.
  - `backend/mcp_servers/` → keep each server's tool contract self-contained; don't reach into another MCP server's internals directly, call it as a tool.
  - `backend/main.py` (WebSocket/REST) → keep DB writes and WebSocket sends in the order the frontend expects (status update before the message that depends on it). Session bootstrap must check existing `chat_state`/DB status before re-greeting (see CLAUDE.md "Rejoin over re-greet").
  - `frontend/src/context/` → providers must never hand `null`/uninitialized values to consumers; WebSocket reconnect logic must re-sync from `/api/room/{room_id}/status`, not assume client state is current.
- **Security:** no hardcoded secrets/keys (extract to `.env` + `.env.example` immediately); every new admin route uses `Depends(get_current_user)`; every new candidate-facing route stays anchored on `room_id` only, no accidental auth gate (see CLAUDE.md identity model). Strip candidate PII (email, name, transcript text) before it hits a log line or an external API call beyond the LLM/STT/TTS providers already in scope.

---

## Gate 4 — Review

Run this lens on every change before marking verify. For any change to auth, DB writes, or LLM calls, also run the full `.agent/security_checklist.md` — its verdict gates a High-risk PASS.

### Security
- No hardcoded secrets, tokens, or keys
- Admin routes have `get_current_user`; candidate routes are still reachable with no auth header
- Candidate PII never appears in `logger.*` calls — log state transitions (`Session {room_id} → ACTIVE`), not content
- SQLAlchemy queries use the ORM/parameterized filters — no raw string interpolation
- JWT verified server-side (`auth.py`) before trusting any admin identity

### Performance
- No unbounded LLM context — check `len()`/token budget before dropping a full transcript into a prompt (per `.agent/CORE_RULES.md` rule 2)
- No N+1 queries across `InterviewSession` / `TranscriptChunk` / `Evaluation` joins
- ChromaDB and SQL queries are limited/paginated, not full-table scans
- No blocking synchronous calls (LLM, STT/TTS, DB) inside an `async def` route or WebSocket loop without `asyncio.to_thread` — a slow call freezes every other connected WebSocket

### Correctness
- Edge cases handled: empty job description, LLM returns malformed JSON, candidate disconnects mid-question, APScheduler job fires twice for the same `room_id`
- Error propagation explicit — no silent `except: pass` blocks; failures must still send a WebSocket message the frontend can react to (see `audio_failed` pattern)
- Session status transitions (`SessionStatus` enum) move forward only — verify no code path can move `COMPLETED` back to `ACTIVE`
- Race conditions checked for concurrent WebSocket messages and scheduler-vs-manual status updates

### Maintainability
- No magic numbers for timing (`EARLY_ENTRY_MINUTES`, `SESSION_TIMEOUT_MINUTES`, etc.) — pull from `config.settings`, don't hardcode a duplicate constant
- Non-obvious logic has a comment explaining why, not what
- Single responsibility — one LangGraph node, one concern

---

## Gate 5 — Verify

**Full-stack trace** (if REST routes, the WebSocket contract, `InterviewState`, DB schema, or an MCP tool contract changed):

```
Client (REST/WS) → main.py route/handler → agents/*.py node → LLM (Groq/Gemini) or mcp_servers/*.py tool → database.py (SQLAlchemy) → WebSocket send → frontend context/hook → UI
```

**Edge cases — evaluate each:** empty / loading / error states; candidate refresh mid-interview (must rejoin, not re-greet); WebSocket reconnect after network blip; duplicate WebSocket messages; LLM returns non-JSON or truncated JSON; empty or missing job description; Whisper/Edge-TTS failure (must fall back, not hang); APScheduler firing a job for an already-cancelled session; simultaneous admin actions on the same `room_id` (e.g. cancel while candidate is joining).

**If the WebSocket message shape or `InterviewState` schema changed:**
- `frontend/src/context/` — consumers parse the new shape without throwing on missing fields
- `frontend/src/services/` — any REST/WS client wrapper updated for the new contract
- `grep 'websocket.send_json\|await websocket.receive' backend/main.py` — every send/receive site updated
- `backend/agents/state.py` — new keys have sane defaults so older in-flight sessions don't KeyError

**Regression surface:** list directly affected agent nodes/routes/components, potentially affected consumers (other MCP servers, other nodes reading the same `InterviewState` keys, frontend contexts), and what must be retested.

---

## Gate 6 — Test Shield

Every bug fix or feature must include tests protecting the modified execution path. Apply the right level:

```
Unit        → pure functions (extract_json, calculate_elapsed_minutes, determine_phase), LangGraph node logic in isolation
Integration → REST endpoints, DB operations, MCP tool calls, WebSocket handler flow (see test_ws_connection.py, test_agent.py)
E2E         → schedule → join room → interview → evaluate → report critical path
```

Focus coverage on: session state transitions, LLM JSON-parsing fallback paths, WebSocket reconnect/rejoin, auth boundaries (User vs Candidate), report generation. Skip: trivial getters/setters, framework internals, one-off scripts (`clean_db.py`, `reset_db.py`, etc.).

Do not mark complete until:
- [ ] Tests pass (explicit filenames — see Gate 2 pytest gotcha)
- [ ] Each acceptance criterion verified individually
- [ ] Edge cases evaluated
- [ ] Frontend/backend contract compatibility verified (WebSocket message shapes, REST response shapes)
- [ ] Rejoin/reconnect verified (refresh mid-interview does not duplicate the greeting or lose transcript)
- [ ] Both User (JWT) and Candidate (room_id-only) paths traced, if auth or routing touched

Close with **What Was Verified / What Was Not Verified** per CLAUDE.md communication standards.

---

## Gate 7 — Deploy (Docker Compose + nginx, self-hosted)

Before pushing to production (`prep.interviewer.dpdns.org`):

- [ ] `cd frontend && npm run build` passes locally with zero errors
- [ ] `docker-compose up --build` succeeds for both `backend` and `frontend` services, healthchecks pass (`/health` for backend, `/` for frontend)
- [ ] No `.env` values hardcoded anywhere in the build output or `docker-compose.yml`
- [ ] `nginx_interviewer.conf` still routes `/` → frontend (5173) and `/api` → backend (8080) with WebSocket upgrade headers intact; `maintenance.html` still served on 502/503/504
- [ ] `VITE_API_BASE_URL` / `VITE_GOOGLE_CLIENT_ID` build args match the target environment (not localhost)
- [ ] SQLite volumes (`interview_system.db`, `scheduler_jobs.db`) are mounted, not baked into the image — a rebuild must not wipe session/job data
- [ ] No migration required, or Alembic migration tested locally first
- [ ] Rollback plan: identify the last stable commit hash / image tag before deploying

State explicitly: **what was verified** and **what was not verified**.

---

## Deep Debugging Protocol

For session/state-desync bugs where static analysis fails:

1. **Database verification:** run a local query script against the actual SQLite DB (`interview_system.db`) — check `InterviewSession.status`, `TranscriptChunk` ordering, `Evaluation` rows directly. Don't assume schema defaults.
2. **Boundary tracing:** temporary logging at three layers — on WebSocket `receive`, before/after the LangGraph node call, on the DB write. Never log candidate PII at any of these points (per CLAUDE.md/CORE_RULES).
3. **End-to-end proof:** run the dev server or `docker-compose up`, trigger the broken action, read `backend/logs/` and `docker logs`. Not fixed until logs prove the correct value traversed the entire stack.
