"""
Scheduler Agent Node
Orchestrates creating the Room, Calendar Event, sending the Email, and logging the Session.

v2: Removed OAuth2 guards — gmail_mcp and calendar_mcp now handle
priority stack internally (SMTP/GWS/OAuth2 fallback).
"""
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
import uuid

from langchain_core.messages import SystemMessage, HumanMessage

from agents.state import InterviewState
from config import settings
from utils.groq_client import llm_client

# Import MCP Servers directly for programmatic access
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
    
    v2: Calendar + email calls always attempted — MCP servers handle
    the priority stack (SMTP/GWS/OAuth2) and gracefully skip if
    no method is available.
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
        
        frontend_link = f"{settings.frontend_url}/interview/{room_id}"
        
        # 3. Use LLM to draft personalized invitation context
        prompt = f"""
        Draft a brief, professional invitation email to a candidate for an AI-led interview.
        Candidate: {candidate_name}
        Role: {job_role}
        Company: {state.get('company', 'Our Company')}
        Interviewer: {state.get('interviewer_designation', 'AI Interviewer')}
        Time: {scheduled_at.strftime('%Y-%m-%d %H:%M UTC')}
        URL: {frontend_link}
        
        Keep it warm, encouraging, and under 150 words. Do NOT include pleasantries like 'Subject:' in the body.
        """
        
        try:
            email_body = llm_client.invoke([HumanMessage(content=prompt)])
        except Exception as e:
            logger.warning(f"LLM failed to draft email, using fallback. {e}")
            email_body = (
                f"Hi {candidate_name},\n\n"
                f"You are invited to an interview for the {job_role} position.\n"
                f"Please join here at the scheduled time: {frontend_link}\n\n"
                "Best,\nInterview Agent System"
            )
            
        html_body = email_body.replace("\n", "<br>")
        
        # 4. Create Calendar Event (always attempt — MCP handles priority stack)
        cal_resp = calendar_mcp.create_event(CreateEventInput(
            summary=f"Interview: {candidate_name} - {job_role}",
            start_time=scheduled_at,
            end_time=scheduled_at + timedelta(minutes=settings.max_interview_duration_minutes),
            attendees=[candidate_email],
            description=f"Generated Interview Room: {frontend_link}\n\n{email_body}"
        ))
        if cal_resp.get("success"):
            logger.info(f"✅ Created calendar event via {cal_resp.get('method', 'unknown')}")
        else:
            logger.warning(f"⚠️ Calendar event creation failed: {cal_resp.get('error')}. Continuing without it.")
            
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
        
        # 6. Send Email notification (always attempt — MCP handles priority stack)
        gmail_resp = gmail_mcp.send_email(SendEmailInput(
            to_email=candidate_email,
            subject=f"Your upcoming interview for {job_role}",
            body=html_body,
            is_html=True
        ))
        if gmail_resp.get("success"):
            logger.info(f"✅ Sent invitation email via {gmail_resp.get('method', 'unknown')}")
        else:
            logger.warning(f"⚠️ Invitation email failed: {gmail_resp.get('error')}. Continuing without it.")

        # 7. Arm Activation Job in APScheduler
        session_mcp.arm_scheduler_job(room_id=db_room_id, scheduled_at=scheduled_at)

        return {
            "room_id": db_room_id,
            "status": "PENDING",
            "daily_room_url": room_url,
            "messages": [SystemMessage(content=f"Successfully scheduled interview for {candidate_name} at {scheduled_at}. Room: {frontend_link}")]
        }
        
    except Exception as e:
        logger.error(f"❌ Scheduler agent failed: {e}")
        return {
            "error": str(e),
            "messages": [SystemMessage(content=f"Scheduler error: {str(e)}")]
        }
