"""
Session MCP Server - Base template for all MCP servers.
Manages interview session lifecycle and state transitions.

Tools exposed:
- create_session: Create new interview session
- get_session: Retrieve session details
- update_status: Update session status
- arm_scheduler_job: Schedule interview activation
- cancel_scheduler_job: Cancel scheduled activation
- log_transcript_chunk: Add conversation to transcript
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import uuid
import logging

from database import (
    SessionLocal, InterviewSession, TranscriptChunk,
    SessionStatus, Speaker, Candidate
)
from scheduler import arm_activation_job, cancel_activation_job

logger = logging.getLogger(__name__)


# Tool Input Schemas (Pydantic models)
class CreateSessionInput(BaseModel):
    """Input schema for create_session tool."""
    candidate_email: str = Field(..., description="Candidate's email address")
    candidate_name: str = Field(..., description="Candidate's full name")
    job_role: str = Field(..., description="Target job role/position")
    company: str = Field(..., description="Company name")
    interviewer_designation: str = Field(..., description="Interviewer's designation/title")
    scheduled_at: datetime = Field(..., description="Scheduled interview datetime (UTC)")
    daily_room_url: str = Field(..., description="Daily.co room URL")


class UpdateStatusInput(BaseModel):
    """Input schema for update_status tool."""
    room_id: str = Field(..., description="Session room ID")
    status: SessionStatus = Field(..., description="New status")


class LogTranscriptInput(BaseModel):
    """Input schema for log_transcript_chunk tool."""
    room_id: str = Field(..., description="Session room ID")
    speaker: Speaker = Field(..., description="Who is speaking (AI or CANDIDATE)")
    content: str = Field(..., description="Transcript content")
    question_id: Optional[int] = Field(None, description="Related question ID if applicable")


# MCP Server Class
class SessionMCPServer:
    """
    Session management MCP server.
    Provides tools for CRUD operations on interview sessions.
    """
    
    def __init__(self):
        self.name = "session-mcp-server"
        self.version = "1.0.0"
        self.tools = {
            "create_session": self.create_session,
            "get_session": self.get_session,
            "update_status": self.update_status,
            "arm_scheduler_job": self.arm_scheduler_job,
            "cancel_scheduler_job": self.cancel_scheduler_job,
            "log_transcript_chunk": self.log_transcript_chunk,
            "get_transcript": self.get_transcript,
            "list_sessions": self.list_sessions
        }
    
    def create_session(self, input_data: CreateSessionInput) -> Dict[str, Any]:
        """
        Create a new interview session.
        
        Returns:
            dict: Created session details including room_id
        """
        db: Session = SessionLocal()
        try:
            room_id = str(uuid.uuid4())
            
            # Fetch or create candidate PII
            candidate = db.query(Candidate).filter(Candidate.email == input_data.candidate_email).first()
            if not candidate:
                candidate = Candidate(email=input_data.candidate_email, name=input_data.candidate_name)
                db.add(candidate)
                db.flush() # get ID
            
            session = InterviewSession(
                room_id=room_id,
                candidate_id=candidate.id,
                job_role=input_data.job_role,
                company=input_data.company,
                interviewer_designation=input_data.interviewer_designation,
                scheduled_at=input_data.scheduled_at,
                daily_room_url=input_data.daily_room_url,
                status=SessionStatus.PENDING
            )
            
            db.add(session)
            db.commit()
            db.refresh(session)
            
            logger.info(f"✅ Created session {room_id} for candidate ID {candidate.id}")
            
            return {
                "success": True,
                "room_id": room_id,
                "status": session.status.value,
                "scheduled_at": session.scheduled_at.isoformat() + "Z",
                "message": "Session created successfully"
            }
        
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error creating session: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    def get_session(self, room_id: str) -> Dict[str, Any]:
        """
        Retrieve session details by room_id.
        
        Args:
            room_id: Session room ID
            
        Returns:
            dict: Session details or error
        """
        db: Session = SessionLocal()
        try:
            session = db.query(InterviewSession).filter(
                InterviewSession.room_id == room_id
            ).first()
            
            if not session:
                return {
                    "success": False,
                    "error": "Session not found"
                }
            
            # Calculate seconds remaining until scheduled time
            now = datetime.utcnow()
            seconds_remaining = (session.scheduled_at - now).total_seconds()
            
            return {
                "success": True,
                "room_id": session.room_id,
                "candidate_name": session.candidate.name,
                "candidate_email": session.candidate.email,
                "job_role": session.job_role,
                "company": session.company,
                "interviewer_designation": session.interviewer_designation,
                "status": session.status.value,
                "scheduled_at": session.scheduled_at.isoformat() + "Z",
                "activated_at": session.activated_at.isoformat() + "Z" if session.activated_at else None,
                "completed_at": session.completed_at.isoformat() + "Z" if session.completed_at else None,
                "finished_at": session.finished_at.isoformat() + "Z" if session.finished_at else None,
                "daily_room_url": session.daily_room_url,
                "seconds_remaining": max(0, int(seconds_remaining))
            }
        
        except Exception as e:
            logger.error(f"❌ Error retrieving session {room_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    def update_status(self, input_data: Any) -> Dict[str, Any]:
        """
        Update session status.
        
        Returns:
            dict: Success status and updated details
        """
        db: Session = SessionLocal()
        
        # Safely extract values whether input_data is a dict (MCP wrapper) or Pydantic object
        room_id = input_data.get("room_id") if isinstance(input_data, dict) else input_data.room_id
        status = input_data.get("status") if isinstance(input_data, dict) else input_data.status
        
        try:
            session = db.query(InterviewSession).filter(
                InterviewSession.room_id == room_id
            ).first()
            
            if not session:
                return {
                    "success": False,
                    "error": "Session not found"
                }
            
            old_status = session.status
            session.status = status
            session.updated_at = datetime.utcnow()
            
            # Update timestamps based on status
            now = datetime.utcnow()
            if status == SessionStatus.ACTIVE:
                if not session.activated_at:
                    session.activated_at = now
                if not session.joined_at:
                    session.joined_at = now
                session.disconnected_at = None  # Clear disconnect timer on (re)join
            elif status == SessionStatus.DISCONNECTED:
                session.disconnected_at = now
            elif status in [SessionStatus.COMPLETED, SessionStatus.EXPIRED, SessionStatus.CANCELLED]:
                if not session.finished_at:
                    session.finished_at = now
                if not session.completed_at:
                    session.completed_at = now
            
            db.commit()
            
            logger.info(f"✅ Session {room_id} status: {old_status.value} → {status if isinstance(status, str) else status.value}")
            
            return {
                "success": True,
                "room_id": room_id,
                "old_status": old_status.value,
                "new_status": status if isinstance(status, str) else status.value,
                "message": "Status updated successfully"
            }
        
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error updating status for {room_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    def arm_scheduler_job(self, room_id: str, scheduled_at: datetime) -> Dict[str, Any]:
        """
        Arm APScheduler job for interview activation.
        
        Args:
            room_id: Session room ID
            scheduled_at: When to activate the interview
            
        Returns:
            dict: Success status
        """
        try:
            success = arm_activation_job(room_id, scheduled_at)
            
            if success:
                return {
                    "success": True,
                    "room_id": room_id,
                    "scheduled_at": scheduled_at.isoformat(),
                    "message": "Activation job armed successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to arm activation job"
                }
        
        except Exception as e:
            logger.error(f"❌ Error arming scheduler job: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def cancel_scheduler_job(self, room_id: str) -> Dict[str, Any]:
        """
        Cancel scheduled activation job.
        
        Args:
            room_id: Session room ID
            
        Returns:
            dict: Success status
        """
        try:
            success = cancel_activation_job(room_id)
            
            if success:
                return {
                    "success": True,
                    "room_id": room_id,
                    "message": "Scheduler job cancelled successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to cancel scheduler job"
                }
        
        except Exception as e:
            logger.error(f"❌ Error cancelling scheduler job: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def log_transcript_chunk(self, input_data: LogTranscriptInput) -> Dict[str, Any]:
        """
        Log a chunk of conversation transcript.
        
        Returns:
            dict: Success status and chunk ID
        """
        db: Session = SessionLocal()
        try:
            chunk = TranscriptChunk(
                room_id=input_data.room_id,
                speaker=input_data.speaker,
                content=input_data.content,
                question_id=input_data.question_id
            )
            
            db.add(chunk)
            db.commit()
            db.refresh(chunk)
            
            logger.debug(f"📝 Logged transcript chunk {chunk.id} for {input_data.room_id}")
            
            return {
                "success": True,
                "chunk_id": chunk.id,
                "room_id": input_data.room_id,
                "message": "Transcript logged successfully"
            }
        
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error logging transcript: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    def get_transcript(self, room_id: str) -> Dict[str, Any]:
        """
        Retrieve full transcript for a session.
        
        Args:
            room_id: Session room ID
            
        Returns:
            dict: List of transcript chunks
        """
        db: Session = SessionLocal()
        try:
            chunks = db.query(TranscriptChunk).filter(
                TranscriptChunk.room_id == room_id
            ).order_by(TranscriptChunk.timestamp).all()
            
            transcript = [
                {
                    "id": chunk.id,
                    "speaker": chunk.speaker.value,
                    "content": chunk.content,
                    "timestamp": chunk.timestamp.isoformat() + "Z",
                    "question_id": chunk.question_id
                }
                for chunk in chunks
            ]
            
            return {
                "success": True,
                "room_id": room_id,
                "transcript": transcript,
                "total_chunks": len(transcript)
            }
        
        except Exception as e:
            logger.error(f"❌ Error retrieving transcript: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    def list_sessions(self, status: Optional[SessionStatus] = None, limit: int = 50) -> Dict[str, Any]:
        """
        List interview sessions with optional status filter.
        
        Args:
            status: Filter by status (optional)
            limit: Maximum number of sessions to return
            
        Returns:
            dict: List of sessions
        """
        db: Session = SessionLocal()
        try:
            query = db.query(InterviewSession)
            
            if status:
                query = query.filter(InterviewSession.status == status)
            
            sessions = query.order_by(
                InterviewSession.scheduled_at.desc()
            ).limit(limit).all()
            
            session_list = [
                {
                    "room_id": s.room_id,
                    "candidate_name": s.candidate.name,
                    "job_role": s.job_role,
                    "company": s.company,
                    "status": s.status.value,
                    "scheduled_at": s.scheduled_at.isoformat() + "Z",
                    "created_at": s.created_at.isoformat() + "Z",
                    "joined_at": s.joined_at.isoformat() + "Z" if s.joined_at else None,
                    "disconnected_at": s.disconnected_at.isoformat() + "Z" if s.disconnected_at else None,
                    "finished_at": s.finished_at.isoformat() + "Z" if s.finished_at else None,
                    "report_generated_at": s.report_generated_at.isoformat() + "Z" if s.report_generated_at else None,
                    "report_retry_count": getattr(s, 'report_retry_count', 0)
                }
                for s in sessions
            ]
            
            return {
                "success": True,
                "sessions": session_list,
                "total": len(session_list)
            }
        
        except Exception as e:
            logger.error(f"❌ Error listing sessions: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()


# Singleton instance
session_mcp = SessionMCPServer()
