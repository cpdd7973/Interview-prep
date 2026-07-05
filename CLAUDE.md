# CLAUDE.md — Project Memory & Core Behavior

## What this is

An MCP-based, multi-agent AI interview system. FastAPI backend runs a LangGraph
agent graph over WebSockets to conduct live, JD-aware technical interviews;
a Vite/React frontend drives the candidate/admin UI.

## Architecture

```
backend/
  main.py              ← FastAPI app: REST routes + /api/interviews/{room_id}/ws
  auth.py               ← Google OAuth + JWT (admin/interviewer accounts only)
  database.py            ← SQLAlchemy models (SQLite), Alembic migrations
  config.py              ← pydantic-settings, loads .env
  scheduler.py            ← APScheduler (SQLite jobstore) — timed interview activation
  agents/                 ← LangGraph nodes, one per interview stage
    orchestrator.py         ← wires the graph together
    scheduler_agent.py → interviewer_agent.py → evaluator_agent.py → report_agent.py
    state.py               ← InterviewState (TypedDict) shared across nodes
  mcp_servers/             ← MCP tool servers: session, voice, question_bank,
                              calendar, gmail, evaluator, report, room
  question_bank/, prompts/, reports/

frontend/
  src/context/            ← React context providers (auth, interview session)
  src/pages/, src/components/, src/services/  ← Vite + React 18, plain JS (.jsx)
```

- **LLM:** Groq primary, Gemini async fallback (`config.primary_llm`). Agent
  nodes call the LLM and parse JSON out of the response (`extract_json` in
  `interviewer_agent.py`) — the model is not guaranteed to return clean JSON.
- **Voice:** Edge-TTS (cloud, primary) / browser Web Speech API (fallback) for
  TTS; browser Web Speech API / MediaRecorder (primary) / Whisper CPU (backup)
  for STT.
- **Video/rooms:** Jitsi Meet (current). Daily.co fields still exist in config
  but are deprecated — don't add new Daily.co-only logic.
- **Vector search:** ChromaDB (question bank retrieval).

## Identity model — ALWAYS ENFORCE

There are two identity types in this system with fundamentally different trust
levels. Any change touching auth, routes, or the interview WebSocket must be
traced for **both**:

| Identity | How they authenticate | Can do |
|---|---|---|
| **User** (admin/interviewer) | Google OAuth → JWT bearer token, verified via `get_current_user` (`auth.py`) | Schedule/cancel interviews, view all sessions, question bank CRUD |
| **Candidate** | No login. Possession of the `room_id` (UUID) is the only credential — `/api/interviews/{room_id}/ws` and `/api/room/{room_id}/status` take no auth token | Join their own interview room and nothing else |

Because `room_id` *is* the candidate's credential:
1. Never log full `room_id` values alongside candidate PII in the same line (defeats the point of the secret).
2. Never add a route that enumerates or lists room_ids without `get_current_user`.
3. Any new candidate-facing endpoint must be reachable with **no** auth header — don't accidentally gate it behind `get_current_user` and silently break candidate access.

## Commands

```bash
# Backend
cd backend && pip install -r requirements.txt
cp ../.env.example ../.env   # then fill in real keys
python main.py                # uvicorn app, port 8000

# Frontend
cd frontend && npm install
npm run dev                   # Vite dev server, port 5173
npm run build                 # → frontend/dist/
npm run lint                  # eslint

# Full stack (prod-like)
docker-compose up --build     # backend :8080→8000, frontend :5173→80, behind nginx
```

## Environment (`.env`, see `.env.example`)

- LLM: `GROQ_API_KEY`, `GEMINI_API_KEY`
- Google OAuth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `ADMIN_EMAIL`, `VITE_GOOGLE_CLIENT_ID` (must match)
- WebRTC: `DAILY_API_KEY`/`DAILY_DOMAIN` (legacy)
- Whisper: `WHISPER_MODEL`, `WHISPER_DEVICE` (CPU-only target hardware — don't default to `cuda`)
- Interview timing: `EARLY_ENTRY_MINUTES`, `SESSION_TIMEOUT_MINUTES`, `MAX_INTERVIEW_DURATION_MINUTES`
- Security: `SECRET_KEY` (JWT signing), `ALLOWED_ORIGINS` (CORS — comma-separated)
- `DATABASE_PATH`, `SCHEDULER_JOBSTORE_PATH` — SQLite files, mounted as volumes in `docker-compose.yml`

---

## Core Rules (every task)

**Simplicity first.** No abstractions, factories, wrappers, or config layers unless required by multiple real use cases. Prefer existing patterns (agents/, mcp_servers/, context/, services/).

**Scope discipline.** Modify only what's required. No unrelated refactors, renames, or reformatting. Changes touching >5 files: stop, list every file + why, propose smaller alternatives, get approval before proceeding.

**Evidence-based claims.** Never say tested/verified/fixed/production-ready without evidence. Never claim fixed if root cause is unknown. Every completed task ends with **What Was Verified** (commands, results, logs) and **What Was Not Verified** (untested flows, remaining assumptions).

**Rejoin over re-greet.** The WebSocket handler decides whether to send the initial greeting by checking whether `chat_state["messages"]` is already populated (see `main.py`, `interview_websocket`) — not by any client-supplied flag. Any change to session bootstrapping must preserve "existing DB/session state wins over a fresh client connection," or a candidate refreshing mid-interview will get a duplicate greeting / lost history.

**Global standing rules live in `.agent/CORE_RULES.md`.** Non-blocking IO, context/token budgets, LLM failure-mode handling, PII logging restrictions, minimal-blast-radius edits, and Black/Ruff/Mypy/ESLint gates are defined there in full — read it, don't restate it here.

---

## Architecture Decisions (ADR)

When choosing between technologies or making a structural change, produce a brief ADR before implementing:

```
## ADR: [Title]
Status: Proposed | Accepted
Context: [What problem, what constraints]
Options: [A vs B — key trade-offs in a table]
Decision: [Chosen option + why]
Consequences: [What gets easier, what gets harder, what to revisit]
```

Use this for decisions like: Groq vs Gemini fallback strategy, SQLite→Postgres migration, new MCP server boundaries, ChromaDB schema/embedding changes, LangGraph state shape changes. ADRs live as comments in the relevant PR or as `docs/adr/` files.

---

## Workflow

Two layers work together — don't treat them as competing systems:

- **`.agent/orchestrator.md`** is the per-prompt execution sequence (skill consult → issue-log check → execute → audit → doc sync → issue-log write → changelog → self-heal). Follow it as written for every prompt.
- **`CHECKLIST.md`** is the concrete implementation gate checklist that fills in "Step 3: Execute the change" and "Step 4: Audit" above with project-specific detail. Follow its gates in order.

Gates at a glance: Plan → Pre-Flight → Implement → Review → Verify → Test Shield → Deploy

---

## Commit Hygiene

Never reference Claude, Claude Code, Anthropic, or AI assistance anywhere in version control. No `Co-Authored-By: Claude …` trailer, no "Generated with Claude Code", and no such mentions in commit messages, branch names, PR titles, or PR bodies. Commits and PRs must read as ordinary human-authored work.
