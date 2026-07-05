"""
FastAPI main application entry point.
Handles all HTTP endpoints and lifecycle management.
"""

import os

# CRITICAL: Disable ChromaDB telemetry before it starts to avoid 'capture()' errors
# and log-bloat on low-resource cloud instances.
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
import logging
import asyncio
import json
import time
import traceback
from datetime import datetime, timezone

# LIGHTWEIGHT imports only — heavy deps load inside interview_websocket()
from config import settings, REPORTS_DIR
from database import init_db
from scheduler import start_scheduler, shutdown_scheduler
from mcp_servers.session_mcp import session_mcp
from auth import auth_router, get_current_user

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Direct file logging for all modules
logger = logging.getLogger(__name__)

os.makedirs("logs", exist_ok=True)
LOG_PATH = "logs/backend.log"
LATEST_LOG_PATH = "logs/latest.log"

# Write handler — clears on restart
file_handler = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

# Overwrite handler for just this run
latest_file_handler = logging.FileHandler(LATEST_LOG_PATH, mode="w", encoding="utf-8")
latest_file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)


# CRITICAL: Filter out watchfiles logger from file handlers to prevent
# log-write → file-change-detected → log-write infinite loop
class ExcludeWatchfilesFilter(logging.Filter):
    def filter(self, record):
        return not record.name.startswith("watchfiles")


file_handler.addFilter(ExcludeWatchfilesFilter())
latest_file_handler.addFilter(ExcludeWatchfilesFilter())

# Attach to root logger
root_logger = logging.getLogger()
root_logger.addHandler(file_handler)
root_logger.addHandler(latest_file_handler)

logger.setLevel(logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    init_db()
    start_scheduler()
    logger.info("System ready")

    yield

    # Shutdown
    logger.info("Shutting down...")
    shutdown_scheduler()
    logger.info("Shutdown complete")


# Upper bound on a single WS binary audio frame -- comfortably above the
# largest legitimate chunk observed in testing (~1.3MB for several seconds
# of speech), bounds worst-case resource use from an oversized/malicious frame.
MAX_AUDIO_CHUNK_BYTES = 15 * 1024 * 1024  # 15MB

# Create FastAPI app
app = FastAPI(
    title="Interview Agent System",
    description="MCP-based AI interview preparation system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes
app.include_router(auth_router, prefix="/api/auth")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "interview-agent-system",
        "version": "1.0.0",
    }


@app.get("/health/ffmpeg")
async def check_ffmpeg():
    """Check if ffmpeg is installed and available."""
    import subprocess

    try:
        # Check if ffmpeg is available
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, check=True
        )
        return {
            "status": "available",
            "version": result.stdout.splitlines()[0] if result.stdout else "unknown",
        }
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


# Room status endpoint (for time gate polling)
@app.get("/api/room/{room_id}/status")
async def get_room_status(room_id: str):
    """
    Get current status of an interview room.
    Used by frontend for time gate polling.
    """
    result = session_mcp.get_session(room_id)
    return result


@app.post("/api/interviews/schedule")
async def schedule_interview(interview_data: dict, user=Depends(get_current_user)):
    """
    Schedule a new interview.
    Called by admin dashboard. Requires authentication.
    """
    # Run the orchestrator graph with PENDING status to trigger the scheduler node
    try:
        from agents.orchestrator import interview_graph

        # Verify Critical Env Vars before proceeding
        if not settings.groq_api_key or "your_" in settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is missing or using placeholder value in .env"
            )

        import os

        db_path = os.path.abspath(settings.database_path)
        if not os.path.exists(os.path.dirname(db_path)):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Run the orchestrator graph with PENDING status to trigger the scheduler node
        initial_state = {
            "room_id": "",  # Will be generated by scheduler node
            "candidate_name": interview_data.get("candidate_name", "Unknown"),
            "candidate_email": interview_data.get("candidate_email", ""),
            "job_role": interview_data.get("job_role", "Software Engineer"),
            "job_description": interview_data.get("job_description", ""),
            "company": interview_data.get("company", "Sample Corp"),
            "interviewer_designation": interview_data.get(
                "interviewer_designation", "Senior Engineer"
            ),
            "status": "PENDING",
            "scheduled_at": interview_data.get(
                "scheduled_at", datetime.now(timezone.utc).isoformat()
            ),
            "daily_room_url": "",
            "messages": [],
            "current_question_id": None,
            "questions_asked": [],
            "questions_state": {},
            "evaluation": None,
        }

        # LangGraph invoke
        result = await asyncio.to_thread(interview_graph.invoke, initial_state)

        if result.get("error"):
            return {"success": False, "error": result["error"]}

        # Tag the session with the authenticated user's ID
        room_id = result.get("room_id")
        if room_id and user:
            try:
                from database import SessionLocal, InterviewSession

                def tag_owner():
                    db = SessionLocal()
                    try:
                        session = (
                            db.query(InterviewSession)
                            .filter(InterviewSession.room_id == room_id)
                            .first()
                        )
                        if session:
                            session.created_by = user.id
                            db.commit()
                    finally:
                        db.close()

                await asyncio.to_thread(tag_owner)
            except Exception as tag_err:
                logger.warning(f"Failed to tag session owner: {tag_err}")

        return {"success": True, "room_id": room_id, "status": result.get("status")}
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"❌ CRITICAL SERVER ERROR: {e}\n{error_trace}")
        return {
            "success": False,
            "error": f"Internal Server Error: {str(e)}",
            "type": type(e).__name__,
            "trace": (
                error_trace
                if settings.log_level == "DEBUG"
                else "Check server logs for traceback"
            ),
        }


# List interviews endpoint
@app.get("/api/interviews")
async def list_interviews(status: str = None, user=Depends(get_current_user)):
    """
    List interviews created by the authenticated user.
    """
    from database import SessionStatus, SessionLocal, InterviewSession

    db = SessionLocal()
    try:
        query = db.query(InterviewSession).filter(
            InterviewSession.created_by == user.id
        )

        if status:
            try:
                status_enum = SessionStatus[status.upper()]
                query = query.filter(InterviewSession.status == status_enum)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        sessions = query.order_by(InterviewSession.scheduled_at.desc()).all()

        result = []
        for s in sessions:
            result.append(
                {
                    "room_id": s.room_id,
                    "candidate_name": s.candidate.name if s.candidate else "Unknown",
                    "candidate_email": s.candidate.email if s.candidate else "",
                    "job_role": s.job_role,
                    "company": s.company,
                    "scheduled_at": (
                        s.scheduled_at.isoformat() if s.scheduled_at else None
                    ),
                    "status": s.status.value if s.status else "PENDING",
                    "daily_room_url": s.daily_room_url,
                    "activated_at": (
                        s.activated_at.isoformat() if s.activated_at else None
                    ),
                    "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                    "report_generated_at": (
                        s.report_generated_at.isoformat()
                        if s.report_generated_at
                        else None
                    ),
                    "report_retry_count": s.report_retry_count or 0,
                    "disconnected_at": (
                        s.disconnected_at.isoformat() if s.disconnected_at else None
                    ),
                }
            )

        return {"success": True, "sessions": result}
    finally:
        db.close()


# Cancel interview endpoint
@app.post("/api/interviews/{room_id}/cancel")
async def cancel_interview(room_id: str, user=Depends(get_current_user)):
    """
    Cancel a scheduled interview. Only the creator can cancel.
    """
    from database import SessionStatus, SessionLocal, InterviewSession
    from mcp_servers.session_mcp import UpdateStatusInput

    # Verify ownership
    db = SessionLocal()
    try:
        session = (
            db.query(InterviewSession)
            .filter(InterviewSession.room_id == room_id)
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Interview not found")
        if session.created_by != user.id:
            raise HTTPException(
                status_code=403, detail="You can only cancel your own interviews"
            )
    finally:
        db.close()

    # Update status to CANCELLED
    result = session_mcp.update_status(
        UpdateStatusInput(room_id=room_id, status=SessionStatus.CANCELLED)
    )

    if result.get("success"):
        # Cancel scheduler job
        session_mcp.cancel_scheduler_job(room_id)

    return result


# Get transcript endpoint
@app.get("/api/interviews/{room_id}/transcript")
async def get_transcript(room_id: str, user=Depends(get_current_user)):
    """
    Get full transcript for an interview. Only the creator can view it.
    """
    from database import SessionLocal, InterviewSession

    db = SessionLocal()
    try:
        session = (
            db.query(InterviewSession)
            .filter(InterviewSession.room_id == room_id)
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Interview not found")
        if session.created_by != user.id:
            raise HTTPException(
                status_code=403, detail="You can only view your own interviews"
            )
    finally:
        db.close()

    result = session_mcp.get_transcript(room_id)
    return result


# Questions endpoints
@app.get("/api/questions")
async def get_questions(role: str = None, user=Depends(get_current_user)):
    """Get questions by role."""
    from mcp_servers.question_bank_mcp import question_bank_mcp, GetQuestionsInput

    if not role:
        return {"success": False, "error": "Role parameter is required"}

    result = question_bank_mcp.get_questions_by_role(
        GetQuestionsInput(role=role, limit=50)
    )
    return result


@app.post("/api/questions")
async def add_question(question_data: dict, user=Depends(get_current_user)):
    """Add a new question."""
    from mcp_servers.question_bank_mcp import question_bank_mcp, AddQuestionInput
    from database import DifficultyLevel

    try:
        difficulty_enum = DifficultyLevel[
            question_data.get("difficulty", "MEDIUM").upper()
        ]

        input_data = AddQuestionInput(
            role=question_data.get("role"),
            topic=question_data.get("topic"),
            difficulty=difficulty_enum,
            question_text=question_data.get("question_text"),
            ideal_answer=question_data.get("ideal_answer"),
            tags=question_data.get("tags"),
        )

        result = question_bank_mcp.add_question(input_data)
        return result
    except Exception as e:
        logger.error(f"Error adding question: {e}")
        return {"success": False, "error": str(e)}


# Evaluation endpoint
@app.get("/api/evaluations/{room_id}")
async def get_evaluation(room_id: str, user=Depends(get_current_user)):
    """Get evaluation report for an interview. Only the creator can view it."""
    from database import SessionLocal, Evaluation, InterviewSession

    db: Session = SessionLocal()
    try:
        eval_record = db.query(Evaluation).filter(Evaluation.room_id == room_id).first()
        session_record = (
            db.query(InterviewSession)
            .filter(InterviewSession.room_id == room_id)
            .first()
        )

        if not eval_record or not session_record:
            return {"success": False, "error": "Evaluation not found for this room"}

        if session_record.created_by != user.id:
            raise HTTPException(
                status_code=403, detail="You can only view your own evaluations"
            )

        return {
            "success": True,
            "evaluation": {
                "candidate_name": session_record.candidate.name,
                "job_role": session_record.job_role,
                "company": session_record.company,
                "scheduled_at": session_record.scheduled_at.isoformat(),
                "completed_at": (
                    session_record.completed_at.isoformat()
                    if session_record.completed_at
                    else None
                ),
                "technical_score": eval_record.technical_score,
                "communication_score": eval_record.communication_score,
                "problem_solving_score": eval_record.problem_solving_score,
                "behavioral_score": eval_record.behavioral_score,
                "confidence_score": eval_record.confidence_score,
                "overall_score": eval_record.overall_score,
                "qualitative_feedback": eval_record.qualitative_feedback,
                "criteria_reasoning": eval_record.criteria_reasoning or {},
                "report_path": eval_record.report_path,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching evaluation: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@app.get("/api/evaluations/{room_id}/pdf")
async def get_evaluation_pdf(room_id: str, user=Depends(get_current_user)):
    """Download the evaluation report PDF. Only the creator can download it."""
    from database import SessionLocal, Evaluation, InterviewSession
    from fastapi.responses import FileResponse

    db: Session = SessionLocal()
    try:
        eval_record = db.query(Evaluation).filter(Evaluation.room_id == room_id).first()
        session_record = (
            db.query(InterviewSession)
            .filter(InterviewSession.room_id == room_id)
            .first()
        )

        if not eval_record or not session_record or not eval_record.report_path:
            raise HTTPException(
                status_code=404, detail="Report PDF not found for this room"
            )

        if session_record.created_by != user.id:
            raise HTTPException(
                status_code=403, detail="You can only view your own evaluations"
            )

        # Resolve the stored path in an OS-agnostic way. Reports generated on a
        # Windows host store backslash paths (reports\...pdf) that os.path.exists
        # can't resolve on Linux/Docker, even though the file is present. Try the
        # stored path, a forward-slash normalized form, and REPORTS_DIR/basename.
        stored = eval_record.report_path
        normalized = stored.replace("\\", "/")
        filename = os.path.basename(normalized)
        candidates = [stored, normalized, os.path.join(str(REPORTS_DIR), filename)]
        resolved = next((p for p in candidates if os.path.exists(p)), None)

        if resolved is None:
            raise HTTPException(
                status_code=404, detail="Report PDF file is missing on disk"
            )

        return FileResponse(resolved, media_type="application/pdf", filename=filename)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching evaluation PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.websocket("/api/interviews/{room_id}/ws")
async def interview_websocket(websocket: WebSocket, room_id: str):
    """
    WebSocket endpoint for real-time WebRTC/Audio streaming between Candidate and Agent.
    """
    logger.info(f"WebSocket connection attempt for room: {room_id}")
    await websocket.accept()
    logger.info(f"WebSocket handshake complete for room: {room_id}")

    # 0. Signal to frontend that handshake is Done (prevents client-side timeout)
    await websocket.send_json({"type": "connection_ready"})

    # Heavy imports — loaded once per process, cached by Python after first call
    from mcp_servers.voice_mcp import (
        voice_mcp,
        SynthesizeSpeechInput,
    )
    from mcp_servers.session_mcp import UpdateStatusInput, LogTranscriptInput
    from agents.state import InterviewState
    from agents.interviewer_agent import interviewer_node
    from database import SessionLocal, InterviewSession, SessionStatus, Speaker
    from langchain_core.messages import HumanMessage, AIMessage

    # 1. Fetch Session (in a thread to avoid blocking async loop)
    def fetch_session():
        db: Session = SessionLocal()
        session = (
            db.query(InterviewSession)
            .filter(InterviewSession.room_id == room_id)
            .first()
        )
        if not session:
            db.close()
            return None
        data = {
            "candidate_name": session.candidate.name,
            "candidate_email": session.candidate.email,
            "job_role": session.job_role,
            "job_description": session.job_description,
            "company": session.company,
            "interviewer_designation": session.interviewer_designation,
            "scheduled_at_iso": (
                session.scheduled_at.isoformat() if session.scheduled_at else ""
            ),
            "daily_room_url": session.daily_room_url or "",
            "skill_plan": session.skill_plan,
            "topics_covered": session.topics_covered,
            "current_phase": session.current_phase,
            "interview_started_at": (
                session.interview_started_at.isoformat()
                if session.interview_started_at
                else None
            ),
        }
        db.close()
        return data

    session_data = await asyncio.to_thread(fetch_session)
    logger.info(f"Session data fetch result: {session_data}")

    if not session_data:
        await websocket.close(code=1008, reason="Session not found")
        return

    candidate_name = session_data["candidate_name"]
    job_role = session_data["job_role"]
    job_description = session_data.get("job_description")
    company = session_data["company"]
    interviewer_designation = session_data["interviewer_designation"]

    # 2. Reconstruct Chat State
    transcript_resp = await asyncio.to_thread(session_mcp.get_transcript, room_id)
    existing_messages = []
    questions_asked = []
    questions_state = {}
    current_q_id = None

    if transcript_resp.get("success"):
        for chunk in transcript_resp["transcript"]:
            if chunk["speaker"] == "AI":
                existing_messages.append(AIMessage(content=chunk["content"]))
            else:
                existing_messages.append(HumanMessage(content=chunk["content"]))

            qid = chunk.get("question_id")
            if qid is not None:
                current_q_id = qid
                if qid not in questions_asked:
                    questions_asked.append(qid)
                questions_state[qid] = "asked"

    chat_state: InterviewState = {
        "room_id": room_id,
        "candidate_name": candidate_name,
        "candidate_email": session_data["candidate_email"],
        "job_role": job_role,
        "job_description": job_description,
        "company": company,
        "interviewer_designation": interviewer_designation,
        "scheduled_at": session_data["scheduled_at_iso"],
        "status": "ACTIVE",
        "daily_room_url": session_data["daily_room_url"],
        "messages": existing_messages,
        "questions_asked": questions_asked,
        "questions_state": questions_state,
        "current_question_id": current_q_id,
        "evaluation": None,
        "error": None,
        # JD-aware interview tracking — restored from the DB so a
        # reconnect doesn't reset the skill plan/phase/30-min timer.
        "skill_plan": session_data.get("skill_plan"),
        "topics_covered": session_data.get("topics_covered") or [],
        "current_phase": session_data.get("current_phase") or "introduction",
        "interview_started_at": session_data.get("interview_started_at")
        or datetime.utcnow().isoformat(),
    }

    # Persist interview_started_at exactly once, on the very first connection
    # for this room. Subsequent reconnects read it back instead of overwriting it.
    if not session_data.get("interview_started_at"):
        await asyncio.to_thread(
            session_mcp.update_interview_state,
            room_id=room_id,
            interview_started_at=chat_state["interview_started_at"],
        )

    try:
        # Wait for the frontend to signal it is ready before sending the initial greeting
        logger.info(f"Waiting for frontend 'start' signal for room {room_id}...")

        while True:
            try:
                init_msg = await websocket.receive()
                if init_msg.get("type") == "websocket.disconnect":
                    logger.info(
                        f"Frontend disconnected before greeting in room {room_id}"
                    )
                    return

                if init_msg.get("text"):
                    try:
                        init_data = json.loads(init_msg["text"])
                        if init_data.get("type") == "start":
                            logger.info(
                                "Frontend ready signal received. Proceeding with initial greeting."
                            )

                            # 🚀 CRITICAL: Update database status to ACTIVE to prevent 15m timeout sweeper
                            def activate_session():
                                db_session = SessionLocal()
                                try:
                                    s = (
                                        db_session.query(InterviewSession)
                                        .filter(InterviewSession.room_id == room_id)
                                        .first()
                                    )
                                    if s:
                                        now = datetime.utcnow()
                                        s.status = SessionStatus.ACTIVE
                                        s.activated_at = now
                                        s.joined_at = now
                                        db_session.commit()
                                        logger.info(
                                            f"✅ Session {room_id} status updated to ACTIVE in database."
                                        )
                                finally:
                                    db_session.close()

                            await asyncio.to_thread(activate_session)
                            break
                    except json.JSONDecodeError:
                        pass
            except (WebSocketDisconnect, RuntimeError) as e:
                logger.warning(
                    f"WebSocket closed while waiting for 'start' in room {room_id}: {e}"
                )
                return

        # 3. Initial Greeting - IDEMPOTENT CHECK
        # Only greet if the session is absolutely fresh (no messages in DB)
        if chat_state["messages"]:
            logger.info(
                f"Session {room_id} already has {len(chat_state['messages'])} messages. Skipping initial greeting."
            )
            await websocket.send_json({"type": "connection_ready", "rejoined": True})
        else:
            logger.info(f"Sending initial greeting for room {room_id}")
            # Signal to frontend specifically about preparation status
            await websocket.send_json(
                {"type": "status", "text": "AI is preparing the first question..."}
            )

            try:
                # 1. Generate Greeting
                try:
                    agent_result = await asyncio.wait_for(
                        interviewer_node(chat_state), timeout=60.0
                    )
                    if "messages" in agent_result:
                        chat_state["messages"].extend(agent_result["messages"])
                    if "current_question_id" in agent_result:
                        chat_state["current_question_id"] = agent_result[
                            "current_question_id"
                        ]
                    if "questions_asked" in agent_result:
                        chat_state["questions_asked"].extend(
                            agent_result["questions_asked"]
                        )
                    # JD-aware state propagation
                    jd_state_update = {}
                    if "skill_plan" in agent_result:
                        chat_state["skill_plan"] = agent_result["skill_plan"]
                        jd_state_update["skill_plan"] = agent_result["skill_plan"]
                    if "topics_covered" in agent_result:
                        chat_state["topics_covered"] = agent_result["topics_covered"]
                        jd_state_update["topics_covered"] = agent_result[
                            "topics_covered"
                        ]
                    if "current_phase" in agent_result:
                        chat_state["current_phase"] = agent_result["current_phase"]
                        jd_state_update["current_phase"] = agent_result["current_phase"]
                    if jd_state_update:
                        await asyncio.to_thread(
                            session_mcp.update_interview_state,
                            room_id=room_id,
                            **jd_state_update,
                        )

                    initial_response = agent_result["messages"][-1].content
                except Exception as agent_err:
                    logger.error(
                        f"interviewer_node failed in room {room_id}: {agent_err}"
                    )
                    initial_response = f"Hello {candidate_name}! Welcome. I'm ready to begin the interview."
                    chat_state["messages"].append(AIMessage(content=initial_response))

                logger.info(f"Initial AI Greeting: {initial_response}")

                # 2. Send Transcript to Frontend
                await websocket.send_json(
                    {"type": "transcript", "speaker": "AI", "text": initial_response}
                )

                # 3. Log to DB
                await asyncio.to_thread(
                    session_mcp.log_transcript_chunk,
                    LogTranscriptInput(
                        room_id=room_id,
                        speaker=Speaker.AI,
                        content=initial_response,
                        question_id=chat_state.get("current_question_id"),
                    ),
                )

                # 4. Generate & Send Audio
                try:
                    tts_result = await asyncio.wait_for(
                        voice_mcp.synthesize_speech(
                            SynthesizeSpeechInput(text=initial_response)
                        ),
                        timeout=30.0,
                    )
                    if tts_result.get("success"):
                        with open(tts_result["audio_path"], "rb") as f:
                            await websocket.send_bytes(f.read())
                        os.remove(tts_result["audio_path"])
                    else:
                        logger.error(
                            f"Initial TTS failed (success=False): {tts_result.get('error')}"
                        )
                        await websocket.send_json({"type": "audio_failed"})
                except Exception as tts_err:
                    logger.error(f"Initial TTS failed for room {room_id}: {tts_err}")
                    await websocket.send_json({"type": "audio_failed"})

            except (WebSocketDisconnect, RuntimeError) as ws_err:
                logger.warning(
                    f"WebSocket closed during initial greeting in room {room_id}: {ws_err}"
                )
                return
            except Exception as e:
                logger.error(
                    f"Error during initial greeting in room {room_id}: {e}",
                    exc_info=True,
                )
                await websocket.send_json({"type": "audio_failed"})

    except Exception as outer_e:
        logger.error(
            f"Critical error in room {room_id} setup phase: {outer_e}", exc_info=True
        )
        return

    try:
        # Loop for continuous conversation

        # Deduplication state for room
        last_chunk_size = 0
        last_chunk_at = 0

        while True:
            try:
                # 1. Receive message from frontend
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    logger.info(f"Frontend disconnected gracefully from room {room_id}")
                    break

                if "text" in message:
                    try:
                        data = json.loads(message["text"])
                        msg_type = data.get("type", "")

                        # Dmitri's heartbeat: respond to ping with pong
                        if msg_type == "ping":
                            await websocket.send_json({"type": "pong"})
                            continue

                        # Frontend signals readiness
                        if msg_type == "start":
                            logger.info(f"[{room_id}] Frontend signalled ready")
                            continue

                        if msg_type == "browser_stt":
                            spoken_text = data.get("text", "")
                            if len(spoken_text.strip()) < 3:
                                continue
                            logger.info(f"[{room_id} (Browser STT)]: {spoken_text}")
                        else:
                            continue
                    except Exception as e:
                        logger.warning(
                            f"[{room_id}] Failed to parse WS text message: {e}"
                        )
                        continue

                elif "bytes" in message:
                    # Each blob is a complete WebM file (frontend stop/restarts MediaRecorder)
                    audio_data = message["bytes"]
                    now = time.time()

                    # LOGGING for Oracle Cloud debugging
                    logger.debug(
                        f"[{room_id}] Received binary chunk: {len(audio_data)} bytes"
                    )

                    # Deduplication (Defense in depth)
                    if (
                        len(audio_data) == last_chunk_size
                        and (now - last_chunk_at) < 2.0
                    ):
                        logger.warning(
                            f"[{room_id}] 🛡️ Ignoring duplicate binary chunk (size={len(audio_data)})"
                        )
                        continue

                    last_chunk_size = len(audio_data)
                    last_chunk_at = now

                    if len(audio_data) < 1000:
                        # Too small — probably silence
                        continue

                    if len(audio_data) > MAX_AUDIO_CHUNK_BYTES:
                        # Comfortably above the largest legitimate chunk observed
                        # in testing (~1.3MB for several seconds of speech) --
                        # reject rather than decode/upload an oversized frame,
                        # which could otherwise exhaust disk/memory/CPU.
                        logger.warning(
                            f"[{room_id}] 🛡️ Rejecting oversized binary chunk "
                            f"(size={len(audio_data)}, max={MAX_AUDIO_CHUNK_BYTES})"
                        )
                        continue

                    logger.info(
                        f"[{room_id}] Transcribing {len(audio_data)} bytes via Groq Whisper..."
                    )

                    try:
                        result = await asyncio.to_thread(
                            voice_mcp.transcribe_audio_groq, audio_data
                        )

                        if result.get("success") and result.get("text", "").strip():
                            spoken_text = result["text"].strip()
                            if len(spoken_text) < 3:
                                continue

                            # Hallucination/echo filtering (silence, video-outro
                            # boilerplate, speaker echo, repeated phrases, etc.)
                            # is handled entirely inside voice_mcp.transcribe_audio_groq
                            # -- see is_hallucinated_transcript(). Previously this
                            # handler had its own separate, smaller, divergent
                            # phrase list here (including "yes"/"no", which
                            # incorrectly filtered legitimate candidate answers to
                            # yes/no questions); consolidated into one filter to
                            # avoid the two lists drifting apart.
                            logger.info(f"[{room_id} (Groq Whisper)]: {spoken_text}")
                        else:
                            logger.debug(
                                f"[{room_id}] Whisper returned empty/failed: {result}"
                            )
                            continue
                    except Exception as e:
                        logger.error(f"[{room_id}] Groq Whisper error: {e}")
                        continue
                else:
                    continue

                # Send transcription to Frontend chat IMMEDIATELY
                await websocket.send_json(
                    {
                        "type": "transcript",
                        "speaker": candidate_name,
                        "text": spoken_text,
                    }
                )

                await asyncio.to_thread(
                    session_mcp.log_transcript_chunk,
                    LogTranscriptInput(
                        room_id=room_id,
                        speaker=Speaker.CANDIDATE,
                        content=spoken_text,
                        question_id=chat_state.get("current_question_id"),
                    ),
                )

                # 4. Feed into Agent Dialog Manager
                chat_state["messages"].append(HumanMessage(content=spoken_text))

                agent_result = await interviewer_node(chat_state)

                # Update local state
                if "messages" in agent_result:
                    chat_state["messages"].extend(agent_result["messages"])
                if "current_question_id" in agent_result:
                    chat_state["current_question_id"] = agent_result[
                        "current_question_id"
                    ]
                if "questions_asked" in agent_result:
                    chat_state["questions_asked"].extend(
                        agent_result["questions_asked"]
                    )
                # JD-aware state propagation
                jd_state_update = {}
                if "skill_plan" in agent_result:
                    chat_state["skill_plan"] = agent_result["skill_plan"]
                    jd_state_update["skill_plan"] = agent_result["skill_plan"]
                if "topics_covered" in agent_result:
                    chat_state["topics_covered"] = agent_result["topics_covered"]
                    jd_state_update["topics_covered"] = agent_result["topics_covered"]
                if "current_phase" in agent_result:
                    chat_state["current_phase"] = agent_result["current_phase"]
                    jd_state_update["current_phase"] = agent_result["current_phase"]
                if jd_state_update:
                    await asyncio.to_thread(
                        session_mcp.update_interview_state,
                        room_id=room_id,
                        **jd_state_update,
                    )

                ai_response = agent_result["messages"][-1].content
                logger.info(f"[AI]: {ai_response}")

                # 5. Send AI text back IMMEDIATELY (Before TTS to reduce perceived latency)
                await websocket.send_json(
                    {"type": "transcript", "speaker": "AI", "text": ai_response}
                )

                await asyncio.to_thread(
                    session_mcp.log_transcript_chunk,
                    LogTranscriptInput(
                        room_id=room_id,
                        speaker=Speaker.AI,
                        content=ai_response,
                        question_id=chat_state.get("current_question_id"),
                    ),
                )

                # 6. Synthesize TTS (Now async)
                tts_result = await voice_mcp.synthesize_speech(
                    SynthesizeSpeechInput(text=ai_response)
                )
                if tts_result.get("success"):
                    audio_path = tts_result["audio_path"]

                    logger.info("Sending AI audio payload back to client...")
                    # Send back the raw synthesized audio
                    with open(audio_path, "rb") as f:
                        mp3_bytes = f.read()

                    await websocket.send_bytes(mp3_bytes)
                    os.remove(audio_path)
                else:
                    logger.error(f"TTS Synthesis failed: {tts_result}")

                # 7. Check if interview is completed
                if agent_result.get("status") == "COMPLETED":
                    chat_state["status"] = "COMPLETED"
                    logger.info(f"Interview {room_id} completed. Updating status.")

                    # Do NOT set status to COMPLETED yet. Set finished_at and keep ACTIVE.
                    def mark_finished():
                        db = SessionLocal()
                        try:
                            s = (
                                db.query(InterviewSession)
                                .filter(InterviewSession.room_id == room_id)
                                .first()
                            )
                            if s:
                                s.finished_at = datetime.utcnow()
                                db.commit()
                        finally:
                            db.close()

                    await asyncio.to_thread(mark_finished)

                    # Notify frontend that interview is complete
                    await websocket.send_json(
                        {
                            "type": "interview_complete",
                            "message": "Interview completed. Your evaluation report is being generated.",
                        }
                    )

                    # Run evaluation + report pipeline in background
                    # (don't block the WebSocket close)
                    async def run_post_interview_pipeline(state):
                        from agents.orchestrator import interview_graph

                        db = SessionLocal()
                        try:
                            logger.info(
                                "🚀 Starting post-interview pipeline (evaluate → report)"
                            )
                            result = await interview_graph.ainvoke(state)

                            session = (
                                db.query(InterviewSession)
                                .filter(InterviewSession.room_id == room_id)
                                .first()
                            )
                            if session:
                                result_status = result.get("status")
                                if result_status == "REPORTED":
                                    session.report_generated_at = datetime.utcnow()
                                    session.status = SessionStatus.COMPLETED
                                    session.pipeline_error = None
                                    logger.info(
                                        f"✅ Post-interview pipeline completed for {room_id}"
                                    )
                                elif result_status == "EVALUATION_FAILED":
                                    session.status = SessionStatus.EVALUATION_FAILED
                                    session.pipeline_error = result.get("error")
                                    session.report_retry_count = (
                                        session.report_retry_count or 0
                                    ) + 1
                                    logger.error(
                                        f"❌ Evaluation failed for {room_id}: {result.get('error')}"
                                    )
                                elif result_status == "REPORT_FAILED":
                                    session.status = SessionStatus.REPORT_FAILED
                                    session.pipeline_error = result.get("error")
                                    session.report_retry_count = (
                                        session.report_retry_count or 0
                                    ) + 1
                                    logger.error(
                                        f"❌ Report generation failed for {room_id}: {result.get('error')}"
                                    )
                                else:
                                    # Graph ended in an unexpected state -- don't
                                    # silently mark it complete.
                                    session.status = SessionStatus.EVALUATION_FAILED
                                    session.pipeline_error = f"Pipeline ended in unexpected status: {result_status}"
                                    logger.error(
                                        f"❌ Post-interview pipeline for {room_id} ended in "
                                        f"unexpected status: {result_status}"
                                    )
                                db.commit()
                        except Exception as pipe_err:
                            logger.error(
                                f"❌ Post-interview pipeline failed: {pipe_err}",
                                exc_info=True,
                            )
                            session = (
                                db.query(InterviewSession)
                                .filter(InterviewSession.room_id == room_id)
                                .first()
                            )
                            if session:
                                session.report_retry_count = (
                                    getattr(session, "report_retry_count", 0) + 1
                                )
                                session.status = SessionStatus.EVALUATION_FAILED
                                session.pipeline_error = str(pipe_err)
                                db.commit()
                        finally:
                            db.close()

                    asyncio.create_task(run_post_interview_pipeline(chat_state))

                    # Prevent network race condition: Give the browser time to receive the final Audio Blob and JSON
                    # before severing the TCP connection.
                    await asyncio.sleep(3.0)
                    await websocket.close(code=1000, reason="Interview Completed")
                    break

            except (WebSocketDisconnect, RuntimeError) as e:
                logger.warning(f"WebSocket closed in room {room_id}: {e}")

                # Update status and exit
                await asyncio.to_thread(
                    session_mcp.update_status,
                    UpdateStatusInput(
                        room_id=room_id, status=SessionStatus.DISCONNECTED
                    ),
                )
                break
            except Exception as inner_e:
                logger.error(
                    f"Error during audio processing pipeline loop in room {room_id}: {inner_e}"
                )
                logger.error(traceback.format_exc())

                # BREAK loop on critical socket errors to prevent infinite spinning
                error_msg = str(inner_e)
                if any(
                    x in error_msg
                    for x in [
                        "already closed",
                        "once a disconnect message",
                        "ConnectionClosed",
                        "was closed",
                    ]
                ):
                    logger.warning(
                        f"Socket closed via exception ({error_msg}). Breaking loop."
                    )
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for room {room_id}")
        await asyncio.to_thread(
            session_mcp.update_status,
            UpdateStatusInput(room_id=room_id, status=SessionStatus.DISCONNECTED),
        )
    except Exception as e:
        logger.error(f"WebSocket critical error: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
        await asyncio.to_thread(
            session_mcp.update_status,
            UpdateStatusInput(room_id=room_id, status=SessionStatus.DISCONNECTED),
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # nosec
        port=8000,
        reload=False,
        log_level=settings.log_level.lower(),
    )
