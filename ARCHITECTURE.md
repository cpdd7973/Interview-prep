# System Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         ADMIN DASHBOARD                          │
│                    (React + Vite Frontend)                       │
│  - Schedule interviews                                           │
│  - Manage question bank                                          │
│  - View reports                                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/REST
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                             │
│                    (Python 3.10+)                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              LANGGRAPH ORCHESTRATOR                       │   │
│  │  State Machine: SCHEDULE → WAIT → ACTIVATE → INTERVIEW   │   │
│  │                 → EVALUATE → REPORT                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                        │
│  ┌──────────────────────┴──────────────────────────────────┐   │
│  │                    AGENTS                                 │   │
│  │  - SchedulerAgent    - InterviewerAgent                  │   │
│  │  - EvaluatorAgent    - ReportAgent                       │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │                                        │
│  ┌──────────────────────┴──────────────────────────────────┐   │
│  │                 MCP SERVERS (Tools)                       │   │
│  │  - session_mcp       - voice_mcp                         │   │
│  │  - question_bank_mcp - room_mcp                          │   │
│  │  - gmail_mcp         - calendar_mcp                      │   │
│  │  - evaluator_mcp     - report_mcp                        │   │
│  └──────────────────────┬──────────────────────────────────┘   │
└────────────────────────┬┴──────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌──────────┐
    │ SQLite  │    │APSched  │    │ChromaDB  │
    │Database │    │Jobstore │    │Vector DB │
    └─────────┘    └─────────┘    └──────────┘
```

## Component Details

### 1. Frontend Layer

```
┌─────────────────────────────────────────────────────────────┐
│                    REACT FRONTEND                            │
├─────────────────────────────────────────────────────────────┤
│  Pages:                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Dashboard   │  │ InterviewRoom│  │ QuestionBank │     │
│  │              │  │              │  │              │     │
│  │ - Schedule   │  │ - Time Gate  │  │ - Add/Edit   │     │
│  │ - List       │  │ - Countdown  │  │ - Import     │     │
│  │ - Cancel     │  │ - Daily.co   │  │ - Search     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  Components:                                                 │
│  - CountdownTimer    - WaitingScreen                        │
│  - VoiceIndicator    - ReportCard                           │
│                                                              │
│  Services:                                                   │
│  - api.js (HTTP client)                                     │
│  - roomPoller.js (30s polling)                              │
└─────────────────────────────────────────────────────────────┘
```

### 2. Backend Layer - Agents

```
┌─────────────────────────────────────────────────────────────┐
│                    LANGGRAPH AGENTS                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  SCHEDULER AGENT                                    │    │
│  │  Input: Admin scheduling request                    │    │
│  │  Tools: calendar_mcp, gmail_mcp, room_mcp,         │    │
│  │         session_mcp                                 │    │
│  │  Output: Session created, email sent, job armed    │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼ (APScheduler triggers)            │
│  ┌────────────────────────────────────────────────────┐    │
│  │  INTERVIEWER AGENT                                  │    │
│  │  Input: Activated session                           │    │
│  │  Tools: voice_mcp, question_bank_mcp, session_mcp  │    │
│  │  Loop:                                              │    │
│  │    1. Get question from bank                        │    │
│  │    2. Synthesize speech (Edge-TTS)                  │    │
│  │    3. Listen for answer                             │    │
│  │    4. Transcribe (Whisper)                          │    │
│  │    5. Log transcript                                │    │
│  │    6. LLM decides next question                     │    │
│  │    7. Repeat until complete                         │    │
│  │  Output: Complete transcript                        │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │  EVALUATOR AGENT                                    │    │
│  │  Input: Transcript + question bank                  │    │
│  │  Tools: evaluator_mcp, session_mcp                  │    │
│  │  Process:                                           │    │
│  │    1. Score each answer                             │    │
│  │    2. Calculate dimension scores                    │    │
│  │    3. Generate qualitative feedback                 │    │
│  │  Output: Evaluation record                          │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │  REPORT AGENT                                       │    │
│  │  Input: Evaluation data                             │    │
│  │  Tools: report_mcp, gmail_mcp                       │    │
│  │  Process:                                           │    │
│  │    1. Compile report data                           │    │
│  │    2. Generate PDF                                  │    │
│  │    3. Email to admin                                │    │
│  │  Output: PDF report sent                            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3. Backend Layer - MCP Servers

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP SERVERS                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  session_mcp     │  │  voice_mcp       │               │
│  │                  │  │                  │               │
│  │ - create_session │  │ - transcribe     │               │
│  │ - get_session    │  │ - synthesize     │               │
│  │ - update_status  │  │ - detect_silence │               │
│  │ - log_transcript │  │                  │               │
│  │ - arm_job        │  │ Uses:            │               │
│  │ - cancel_job     │  │ - Whisper tiny   │               │
│  │                  │  │ - Edge-TTS       │               │
│  └──────────────────┘  └──────────────────┘               │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ question_bank_mcp│  │  room_mcp        │               │
│  │                  │  │                  │               │
│  │ - get_questions  │  │ - create_room    │               │
│  │ - add_question   │  │ - get_status     │               │
│  │ - edit_question  │  │ - delete_room    │               │
│  │ - delete_question│  │                  │               │
│  │ - bulk_import    │  │ Uses:            │               │
│  │ - semantic_search│  │ - Daily.co API   │               │
│  │                  │  │                  │               │
│  │ Uses: ChromaDB   │  └──────────────────┘               │
│  └──────────────────┘                                       │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  gmail_mcp       │  │  calendar_mcp    │               │
│  │                  │  │                  │               │
│  │ - send_email     │  │ - create_event   │               │
│  │ - read_inbox     │  │ - find_slots     │               │
│  │ - check_schedule │  │ - cancel_event   │               │
│  │                  │  │ - reschedule     │               │
│  │ Uses:            │  │                  │               │
│  │ - Gmail API      │  │ Uses:            │               │
│  │ - OAuth2         │  │ - Calendar API   │               │
│  └──────────────────┘  └──────────────────┘               │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  evaluator_mcp   │  │  report_mcp      │               │
│  │                  │  │                  │               │
│  │ - score_answer   │  │ - compile_report │               │
│  │ - calc_scores    │  │ - export_pdf     │               │
│  │ - gen_feedback   │  │ - email_report   │               │
│  │                  │  │                  │               │
│  │ Uses:            │  │ Uses:            │               │
│  │ - Groq/Gemini    │  │ - ReportLab      │               │
│  └──────────────────┘  └──────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4. Data Layer

```
┌─────────────────────────────────────────────────────────────┐
│                      DATA LAYER                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  SQLite Database (interview_system.db)             │    │
│  │                                                     │    │
│  │  Tables:                                            │    │
│  │  ┌──────────────────┐  ┌──────────────────┐       │    │
│  │  │interview_sessions│  │transcript_chunks │       │    │
│  │  │                  │  │                  │       │    │
│  │  │ - room_id (PK)   │  │ - id (PK)        │       │    │
│  │  │ - candidate_*    │  │ - room_id (FK)   │       │    │
│  │  │ - job_role       │  │ - speaker        │       │    │
│  │  │ - scheduled_at   │  │ - content        │       │    │
│  │  │ - status         │  │ - timestamp      │       │    │
│  │  │ - daily_room_url │  │ - question_id    │       │    │
│  │  └──────────────────┘  └──────────────────┘       │    │
│  │                                                     │    │
│  │  ┌──────────────────┐  ┌──────────────────┐       │    │
│  │  │   questions      │  │  evaluations     │       │    │
│  │  │                  │  │                  │       │    │
│  │  │ - id (PK)        │  │ - id (PK)        │       │    │
│  │  │ - role           │  │ - room_id (FK)   │       │    │
│  │  │ - topic          │  │ - *_score        │       │    │
│  │  │ - difficulty     │  │ - feedback       │       │    │
│  │  │ - type           │  │ - report_path    │       │    │
│  │  │ - question_text  │  │                  │       │    │
│  │  │ - ideal_answer   │  │                  │       │    │
│  │  │ - tags           │  │                  │       │    │
│  │  └──────────────────┘  └──────────────────┘       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  APScheduler Jobstore (scheduler_jobs.db)          │    │
│  │                                                     │    │
│  │  - Persists scheduled jobs across restarts         │    │
│  │  - Jobs: activate_interview, expire_interview      │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  ChromaDB (in-memory collections)                  │    │
│  │                                                     │    │
│  │  Collections (one per role):                       │    │
│  │  - software_engineer_questions                     │    │
│  │  - product_manager_questions                       │    │
│  │  - devops_engineer_questions                       │    │
│  │  - data_analyst_questions                          │    │
│  │                                                     │    │
│  │  Used for semantic search of questions             │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5. External Services

```
┌─────────────────────────────────────────────────────────────┐
│                   EXTERNAL SERVICES                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  Groq API        │  │  Gemini API      │               │
│  │  (Primary LLM)   │  │  (Fallback LLM)  │               │
│  │                  │  │                  │               │
│  │ - mixtral/llama3 │  │ - gemini-pro     │               │
│  │ - Free tier      │  │ - Free tier      │               │
│  │ - Fast inference │  │ - Async Lazy-Init│               │
│  └──────────────────┘  └──────────────────┘               │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  Daily.co        │  │  Edge-TTS        │               │
│  │  (WebRTC)        │  │  (Text-to-Speech)│               │
│  │                  │  │                  │               │
│  │ - Room creation  │  │ - Cloud API      │               │
│  │ - 5 rooms free   │  │ - Zero local RAM │               │
│  │ - 20 min/session │  │ - Multiple voices│               │
│  └──────────────────┘  └──────────────────┘               │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  Gmail API       │  │  Calendar API    │               │
│  │  (Email)         │  │  (Scheduling)    │               │
│  │                  │  │                  │               │
│  │ - Send emails    │  │ - Create events  │               │
│  │ - OAuth2         │  │ - Check conflicts│               │
│  │ - 500/day limit  │  │ - OAuth2         │               │
│  └──────────────────┘  └──────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow - Complete Interview Lifecycle

### Phase 1: Scheduling

```
Admin Dashboard
    │
    │ POST /api/interviews/schedule
    │ {candidate_email, job_role, scheduled_at, ...}
    ▼
SchedulerAgent
    │
    ├─► room_mcp.create_daily_room()
    │   └─► Daily.co API → room_url
    │
    ├─► session_mcp.create_session()
    │   └─► SQLite → room_id, status=PENDING
    │
    ├─► session_mcp.arm_scheduler_job()
    │   └─► APScheduler → job scheduled
    │
    ├─► gmail_mcp.send_email()
    │   └─► Gmail API → email sent to candidate
    │
    └─► calendar_mcp.create_event()
        └─► Calendar API → event created
```

### Phase 2: Time Gate (Candidate Side)

```
Candidate visits: /interview/{room_id}
    │
    │ GET /api/room/{room_id}/status
    ▼
session_mcp.get_session()
    │
    └─► SQLite → session data + seconds_remaining
        │
        ├─► If seconds_remaining > 300 (5 min)
        │   └─► Frontend shows CountdownTimer
        │
        ├─► If 0 < seconds_remaining ≤ 300
        │   └─► Frontend shows WaitingScreen
        │
        └─► If status == ACTIVE
            └─► Frontend loads Daily.co iframe

Frontend polls every 30 seconds until ACTIVE
```

### Phase 3: Activation (APScheduler)

```
APScheduler triggers at scheduled_at
    │
    │ activate_interview(room_id)
    ▼
scheduler.py
    │
    ├─► session_mcp.update_status(ACTIVE)
    │   └─► SQLite → status=ACTIVE, activated_at=now
    │
    └─► Schedule expire_interview(room_id) in 60 min
        └─► APScheduler → expiration job armed
```

### Phase 4: Interview (Voice Loop)

```
InterviewerAgent activates
    │
    ├─► question_bank_mcp.get_questions_by_role()
    │   └─► SQLite + ChromaDB → question list
    │
    └─► For each question:
        │
        ├─► voice_mcp.synthesize_speech(question_text)
        │   └─► Edge-TTS API → audio stream
        │
        ├─► Daily.co room plays audio
        │
        ├─► Frontend records audio (MediaRecorder) or Browser STT (`webkitSpeechRecognition`)
        │
        ├─► voice_mcp.transcribe_audio(audio_chunk) (Fallback if Browser STT disabled)
        │   └─► Whisper tiny (CPU) → transcript text
        │
        ├─► session_mcp.log_transcript_chunk()
        │   └─► SQLite → transcript saved
        │
        ├─► Python heuristic state machine determines next state
        │   └─► LLM generates reply based on `unasked`, `asked`, `answered` context
        │
        └─► Repeat until interview complete

session_mcp.update_status(COMPLETED)
    └─► SQLite → status=COMPLETED, completed_at=now
```

### Phase 5: Evaluation

```
EvaluatorAgent triggers
    │
    ├─► session_mcp.get_transcript(room_id)
    │   └─► SQLite → full transcript
    │
    ├─► question_bank_mcp.get_questions_by_role()
    │   └─► SQLite → ideal answers
    │
    ├─► evaluator_mcp.calculate_dimension_scores()
    │   └─► Groq API → scores + feedback
    │
    └─► SQLite → evaluation record saved
```

### Phase 6: Report Generation

```
ReportAgent triggers
    │
    ├─► report_mcp.compile_report()
    │   └─► Fetch evaluation + session data
    │
    ├─► report_mcp.export_pdf()
    │   └─► ReportLab → PDF file generated
    │
    ├─► report_mcp.email_report_to_admin()
    │   └─► Gmail API → PDF emailed to admin
    │
    └─► SQLite → report_path updated
```

## State Machine (LangGraph)

```
┌─────────────┐
│   SCHEDULE  │ ← Admin creates interview
└──────┬──────┘
       │
       │ session_mcp.arm_scheduler_job()
       ▼
┌─────────────┐
│    WAIT     │ ← APScheduler waits for scheduled_at
└──────┬──────┘
       │
       │ Time reaches scheduled_at
       ▼
┌─────────────┐
│  ACTIVATE   │ ← Status → ACTIVE, candidate can join
└──────┬──────┘
       │
       │ InterviewerAgent starts
       ▼
┌─────────────┐
│  INTERVIEW  │ ← Voice Q&A loop
└──────┬──────┘
       │
       │ Interview completes
       ▼
┌─────────────┐
│  EVALUATE   │ ← EvaluatorAgent scores transcript
└──────┬──────┘
       │
       │ Evaluation complete
       ▼
┌─────────────┐
│   REPORT    │ ← ReportAgent generates PDF
└──────┬──────┘
       │
       │ Report sent
       ▼
┌─────────────┐
│    DONE     │
└─────────────┘

Error transitions:
- Any state → CANCELLED (admin cancels)
- WAIT → EXPIRED (60 min after scheduled_at, no join)
- INTERVIEW → INCOMPLETE (network failure, timeout)
```

## RAM Budget Allocation

```
Component                 Idle    Active   Peak
─────────────────────────────────────────────────
FastAPI + SQLite         100MB    150MB   150MB
APScheduler               20MB     30MB    30MB
ChromaDB                 100MB    200MB   250MB
Whisper tiny (lazy)        0MB    300MB   500MB
LLM API calls              0MB     50MB   100MB
Transcript buffers         0MB     20MB    50MB
─────────────────────────────────────────────────
TOTAL                    220MB    750MB  1080MB

Peak during transcription: ~1.1GB
Well within 2GB budget ✅
```

## Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. API Keys (Environment Variables)                        │
│     - Never committed to git                                │
│     - Loaded from .env file                                 │
│     - Rotated quarterly                                     │
│                                                              │
│  2. Room Access Control                                     │
│     - UUID-based room IDs (hard to guess)                   │
│     - Daily.co private rooms                                │
│     - Optional room passwords                               │
│                                                              │
│  3. Data Privacy                                            │
│     - No audio files stored (only transcripts)              │
│     - PII removed before evaluation                         │
│     - 90-day data retention policy                          │
│     - Candidate consent required                            │
│                                                              │
│  4. CORS Protection                                         │
│     - Whitelist frontend origins only                       │
│     - No wildcard origins in production                     │
│                                                              │
│  5. Input Validation                                        │
│     - Pydantic schemas for all inputs                       │
│     - SQL injection prevention (SQLAlchemy ORM)             │
│     - XSS prevention (React escapes by default)             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Architecture (Future)

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION SETUP                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Frontend (Static Hosting)                                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Vercel / Netlify / Cloudflare Pages               │    │
│  │  - React build artifacts                            │    │
│  │  - CDN distribution                                 │    │
│  │  - SSL/TLS certificates                             │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          │ HTTPS                             │
│                          ▼                                   │
│  Backend (VPS / Cloud)                                      │
│  ┌────────────────────────────────────────────────────┐    │
│  │  DigitalOcean Droplet / AWS EC2 / Hetzner          │    │
│  │  - Ubuntu 22.04 LTS                                 │    │
│  │  - Gunicorn (WSGI server)                           │    │
│  │  - Nginx (reverse proxy)                            │    │
│  │  - Supervisor (process management)                  │    │
│  │  - SSL/TLS (Let's Encrypt)                          │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  Database (Persistent Storage)                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  SQLite file on disk                                │    │
│  │  - Daily backups to S3 / Backblaze                  │    │
│  │  - WAL mode enabled                                 │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

**Architecture Version**: 1.0  
**Last Updated**: Phase 1 Complete  
**Next Review**: After Phase 2 (MCP Servers) Complete
