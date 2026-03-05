"""
Scheduler Agent Node
Orchestrates creating the Room, Calendar Event, sending the Email, and logging the Session.
"""
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
import uuid

from langchain_core.messages import SystemMessage, HumanMessage

from agents.state import InterviewState
from config import settings
from utils.groq_client import llm_client

# Import MCP Servers directly for programmatic access (bypassing full REST/MCP protocol overhead for local execution)
from mcp_servers.room_mcp import room_mcp, CreateRoomInput
from mcp_servers.calendar_mcp import calendar_mcp, CreateEventInput
from mcp_servers.gmail_mcp import gmail_mcp, SendEmailInput
from mcp_servers.session_mcp import session_mcp, CreateSessionInput

logger = logging.getLogger(__name__)

def schedule_interview_node(state: InterviewState) -> Dict[str, Any]:
    """
    LangGraph node for scheduling an interview.
    It provisions the Daily room, blocks the Google Calendar, registers
    the session in SQLite, and emails the candidate.
    """
    logger.info(f"⏳ Scheduler Agent active for {state.get('candidate_name')}")
    
    if state.get("status") != "PENDING":
        logger.info("Session already beyond PENDING status. Skipping scheduling.")
        return state

    try:
        candidate_name = state["candidate_name"]
        candidate_email = state["candidate_email"]
        job_role = state["job_role"]
        scheduled_at_str = state["scheduled_at"]
        
        # 1. Parse Datetime
        scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
        
        # 2. Create Daily.co Room
        room_id = str(uuid.uuid4())
        room_resp = room_mcp.create_daily_room(CreateRoomInput(
            room_id=room_id,
            duration_minutes=settings.max_interview_duration_minutes + settings.early_entry_minutes
        ))
        
        if not room_resp.get("success"):
            raise ValueError(f"Failed to create room: {room_resp.get('error')}")
            
        room_url = room_resp["room_url"]
        logger.info(f"✅ Created Daily.co room: {room_url}")
        
        # 3. Use LLM to draft personalized invitation context
        prompt = f"""
        Draft a brief, professional invitation email to a candidate for an AI-led interview.
        Candidate: {candidate_name}
        Role: {job_role}
        Company: {state.get('company', 'Our Company')}
        Interviewer: {state.get('interviewer_designation', 'AI Interviewer')}
        Time: {scheduled_at.strftime('%Y-%m-%d %H:%M UTC')}
        URL: {room_url}
        
        Keep it warm, encouraging, and under 150 words. Do NOT include pleasantries like 'Subject:' in the body.
        """
        
        try:
            email_body = llm_client.invoke([HumanMessage(content=prompt)])
        except Exception as e:
            logger.warning(f"LLM failed to draft email, using fallback. {e}")
            email_body = (
                f"Hi {candidate_name},\n\n"
                f"You are invited to an interview for the {job_role} position.\n"
                f"Please join here at the scheduled time: {room_url}\n\n"
                "Best,\nInterview Agent System"
            )
            
        html_body = email_body.replace("\n", "<br>")
        
        # 4. Create Calendar Event (Only if configured)
        if settings.google_refresh_token and settings.google_refresh_token != "your_refresh_token":
            cal_resp = calendar_mcp.create_event(CreateEventInput(
                summary=f"Interview: {candidate_name} - {job_role}",
                start_time=scheduled_at,
                end_time=scheduled_at + timedelta(minutes=settings.max_interview_duration_minutes),
                attendees=[candidate_email],
                description=f"Generated Interview Room: {room_url}\n\n{email_body}"
            ))
            if cal_resp.get("success"):
                logger.info("✅ Created Google Calendar event")
            else:
                logger.error(f"Failed to create calendar event: {cal_resp.get('error')}")
        else:
            logger.info("⚠️ Skipping Google Calendar event creation (Credentials not configured)")
            
        # 5. Create Session in Database
        sess_resp = session_mcp.create_session(CreateSessionInput(
            candidate_email=candidate_email,
            candidate_name=candidate_name,
            job_role=job_role,
            company=state.get("company", "Unknown"),
            interviewer_designation=state.get("interviewer_designation", "AI"),
            scheduled_at=scheduled_at,
            daily_room_url=room_url
        ))
        
        db_room_id = sess_resp.get("room_id", room_id)
        
        # 6. Send the Email notification via Gmail MCP Server (Only if configured)
        if settings.google_refresh_token and settings.google_refresh_token != "your_refresh_token":
            gmail_resp = gmail_mcp.send_email(SendEmailInput(
                to_email=candidate_email,
                subject=f"Your upcoming interview for {job_role}",
                body=html_body,
                is_html=True
            ))
            if gmail_resp.get("success"):
                logger.info(f"✅ Sent invitation email to candidate")
            else:
                logger.error(f"Failed to send email: {gmail_resp.get('error')}")
        else:
            logger.info("⚠️ Skipping Gmail invitation email (Credentials not configured)")

        # 7. Arm Activation Job in APScheduler
        session_mcp.arm_scheduler_job(room_id=db_room_id, scheduled_at=scheduled_at)

        return {
            "room_id": db_room_id,
            "status": "PENDING",
            "daily_room_url": room_url,
            "messages": [SystemMessage(content=f"Successfully scheduled interview for {candidate_name} at {scheduled_at}. Room: {room_url}")]
        }
        
    except Exception as e:
        logger.error(f"❌ Scheduler agent failed: {e}")
        return {
            "error": str(e),
            "messages": [SystemMessage(content=f"Scheduler error: {str(e)}")]
        }
