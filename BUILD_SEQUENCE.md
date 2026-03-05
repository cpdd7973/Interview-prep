# Build Sequence - Interview Agent System

This document outlines the exact order to build components for optimal development flow.

## Phase 1: Foundation (COMPLETED ✅)

1. ✅ Project structure and configuration
2. ✅ Database schema (database.py)
3. ✅ APScheduler setup (scheduler.py)
4. ✅ Session MCP server (session_mcp.py) - Base template
5. ✅ FastAPI main app (main.py) with basic endpoints
6. ✅ Frontend InterviewRoom.jsx with time gate logic
7. ✅ Frontend components (CountdownTimer, WaitingScreen, VoiceIndicator)
8. ✅ API service layer (api.js)
9. ✅ Agent prompts (interviewer, evaluator, scheduler)
10. ✅ Sample question bank (software_engineer.json)

## Phase 2: Core MCP Servers (NEXT)

Build these MCP servers following the session_mcp.py template:

### 2.1 Voice MCP Server (voice_mcp.py)
**Priority: HIGH** - Required for interview functionality

Tools to implement:
- `transcribe_audio(audio_data)` - Whisper tiny transcription
- `synthesize_speech(text)` - Edge-TTS synthesis
- `detect_silence(audio_stream)` - VAD for turn-taking

Dependencies:
- openai-whisper (load model lazily, unload after use)
- edge-tts (async API calls)
- webrtcvad or similar for silence detection

RAM Budget: ~500MB during transcription, 0MB idle

### 2.2 Question Bank MCP Server (question_bank_mcp.py)
**Priority: HIGH** - Required for interview content

Tools to implement:
- `get_questions_by_role(role, difficulty=None, limit=10)`
- `add_question(question_data)`
- `edit_question(question_id, updates)`
- `delete_question(question_id)`
- `bulk_import_questions(json_file_path)`
- `semantic_search(query, role, top_k=5)` - ChromaDB

Dependencies:
- ChromaDB for semantic search
- Load question bank JSONs on startup
- Index questions in ChromaDB collection per role

RAM Budget: ~200MB for ChromaDB + embeddings

### 2.3 Room MCP Server (room_mcp.py)
**Priority: MEDIUM** - Required for scheduling

Tools to implement:
- `create_daily_room(room_id, properties)` - Daily.co API
- `get_room_status(room_id)`
- `delete_room(room_id)` - Cleanup after interview
- `list_active_rooms()`

Dependencies:
- Daily.co REST API (httpx for async calls)
- Store room URLs in session database

RAM Budget: Negligible (API calls only)

### 2.4 Gmail MCP Server (gmail_mcp.py)
**Priority: MEDIUM** - Required for notifications

Tools to implement:
- `send_email(to, subject, body, html=True)`
- `read_inbox(query, max_results=10)` - For candidate replies
- `check_schedule()` - Check admin calendar

Dependencies:
- Google Gmail API with OAuth2
- Use service account or OAuth refresh token
- Template rendering for emails

RAM Budget: Negligible

### 2.5 Calendar MCP Server (calendar_mcp.py)
**Priority: MEDIUM** - Required for scheduling

Tools to implement:
- `create_event(summary, start_time, end_time, attendees, description)`
- `find_free_slots(date, duration_minutes)`
- `cancel_event(event_id)`
- `reschedule_event(event_id, new_start_time)`

Dependencies:
- Google Calendar API with OAuth2
- Check for conflicts before scheduling

RAM Budget: Negligible

### 2.6 Evaluator MCP Server (evaluator_mcp.py)
**Priority: LOW** - Post-interview only

Tools to implement:
- `score_answer(question, answer, ideal_answer)` - Single answer scoring
- `calculate_dimension_scores(transcript, question_bank)` - Full evaluation
- `generate_feedback(scores, transcript)` - Qualitative feedback

Dependencies:
- LLM client (Groq/Gemini)
- Evaluation prompt template

RAM Budget: ~100MB during evaluation

### 2.7 Report MCP Server (report_mcp.py)
**Priority: LOW** - Post-interview only

Tools to implement:
- `compile_report(evaluation_data, session_data)` - Aggregate data
- `export_pdf(report_data, output_path)` - Generate PDF
- `email_report_to_admin(report_path, room_id)` - Send via Gmail

Dependencies:
- ReportLab for PDF generation
- Gmail MCP for sending

RAM Budget: ~50MB during PDF generation

## Phase 3: Agents (After MCP Servers)

### 3.1 SchedulerAgent (scheduler_agent.py)
**Priority: HIGH**

Responsibilities:
- Parse admin scheduling request
- Validate inputs and check conflicts
- Create Daily.co room via room_mcp
- Create session via session_mcp
- Arm APScheduler job
- Send email via gmail_mcp
- Create calendar event via calendar_mcp

LangGraph State:
```python
{
    "admin_input": str,
    "candidate_email": str,
    "candidate_name": str,
    "job_role": str,
    "company": str,
    "interviewer_designation": str,
    "scheduled_at": datetime,
    "room_id": str,
    "daily_room_url": str,
    "status": str,
    "errors": List[str]
}
```

### 3.2 InterviewerAgent (interviewer_agent.py)
**Priority: HIGH**

Responsibilities:
- Activate when APScheduler triggers
- Load question bank for role
- Greet candidate by name
- Run voice Q&A loop:
  1. Synthesize question via voice_mcp
  2. Wait for candidate response
  3. Transcribe via voice_mcp
  4. Log transcript via session_mcp
  5. Use LLM to decide next question/follow-up
  6. Repeat until complete
- End interview gracefully
- Mark session COMPLETED

LangGraph State:
```python
{
    "room_id": str,
    "session_data": dict,
    "question_bank": List[dict],
    "current_question_idx": int,
    "transcript": List[dict],
    "interview_phase": str,  # greeting, questioning, closing
    "questions_asked": int,
    "max_questions": int
}
```

### 3.3 EvaluatorAgent (evaluator_agent.py)
**Priority: MEDIUM**

Responsibilities:
- Triggered after interview COMPLETED
- Fetch transcript via session_mcp
- Fetch question bank via question_bank_mcp
- Score each answer via evaluator_mcp
- Calculate dimension scores
- Generate qualitative feedback
- Store evaluation in database

LangGraph State:
```python
{
    "room_id": str,
    "transcript": List[dict],
    "question_bank": List[dict],
    "scores": dict,
    "feedback": str,
    "status": str
}
```

### 3.4 ReportAgent (report_agent.py)
**Priority: MEDIUM**

Responsibilities:
- Triggered after evaluation complete
- Compile report via report_mcp
- Generate PDF via report_mcp
- Email to admin via gmail_mcp
- Update evaluation record with report path

LangGraph State:
```python
{
    "room_id": str,
    "evaluation_data": dict,
    "session_data": dict,
    "report_path": str,
    "email_sent": bool,
    "status": str
}
```

### 3.5 Orchestrator (orchestrator.py)
**Priority: HIGH** - Build after all agents

LangGraph workflow:
```
SCHEDULE → WAIT → ACTIVATE → INTERVIEW → EVALUATE → REPORT
```

State machine transitions:
- SCHEDULE: SchedulerAgent creates session, arms job
- WAIT: APScheduler waits for scheduled_at
- ACTIVATE: APScheduler triggers, updates status to ACTIVE
- INTERVIEW: InterviewerAgent runs Q&A loop
- EVALUATE: EvaluatorAgent scores transcript
- REPORT: ReportAgent generates and emails PDF

## Phase 4: Frontend Pages

### 4.1 Dashboard.jsx
**Priority: HIGH**

Features:
- Schedule new interview form
- List all interviews (tabs: Pending, Active, Completed)
- Cancel/reschedule actions
- View session details

### 4.2 QuestionBank.jsx
**Priority: MEDIUM**

Features:
- List questions by role
- Add/edit/delete questions
- Bulk import from JSON
- Filter by difficulty/type/tags

### 4.3 Report.jsx
**Priority: LOW**

Features:
- View evaluation scores
- Display dimension breakdown
- Show qualitative feedback
- Download PDF report

## Phase 5: Integration & Testing

### 5.1 End-to-End Flow Test
1. Admin schedules interview via Dashboard
2. Verify email sent to candidate
3. Verify calendar event created
4. Verify APScheduler job armed
5. Candidate visits room URL before time → sees countdown
6. 5 minutes before → sees waiting screen
7. At scheduled time → status flips to ACTIVE
8. Interview runs (can mock with test audio)
9. Interview completes → evaluation runs
10. Report generated and emailed to admin

### 5.2 Edge Cases to Test
- Candidate never joins → session expires after 60 min
- Backend restarts → APScheduler reloads jobs from SQLite
- Admin cancels interview → job cancelled, email sent
- Admin reschedules → old job cancelled, new job armed
- Concurrent interviews → no conflicts, sequential execution
- LLM API failure → fallback to Gemini works
- Whisper transcription error → graceful handling

## Phase 6: Optimization & Polish

### 6.1 RAM Optimization
- Lazy load Whisper model (load on first use, unload after)
- Limit ChromaDB collection size
- Clear transcript chunks from memory after logging to DB
- Use streaming for audio processing

### 6.2 Error Handling
- Retry logic for API calls (exponential backoff)
- Graceful degradation (e.g., skip semantic search if ChromaDB fails)
- User-friendly error messages in frontend
- Admin notifications for system errors

### 6.3 UI/UX Polish
- Loading states and spinners
- Toast notifications for actions
- Responsive design for mobile
- Accessibility (ARIA labels, keyboard navigation)

## RAM Budget Breakdown

| Component | Idle | Active | Peak |
|-----------|------|--------|------|
| FastAPI + SQLite | 100MB | 150MB | 150MB |
| APScheduler | 20MB | 30MB | 30MB |
| Whisper tiny | 0MB | 300MB | 500MB |
| ChromaDB | 100MB | 200MB | 250MB |
| LLM API calls | 0MB | 50MB | 100MB |
| Frontend (browser) | N/A | 200MB | 300MB |
| **TOTAL** | **220MB** | **930MB** | **1.33GB** |

✅ Well within 2GB budget

## Development Tips

1. **Test each MCP server independently** before integrating with agents
2. **Use mock data** for faster iteration (mock LLM responses, mock audio)
3. **Log everything** - use structured logging for debugging
4. **Version control** - commit after each working component
5. **Document as you go** - update README with setup instructions

## Next Steps

Start with Phase 2.1 (Voice MCP Server) as it's the most complex.
Once voice is working, the rest will fall into place quickly.

Ask me which component you want to build next!
