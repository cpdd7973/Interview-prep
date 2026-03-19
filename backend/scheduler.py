"""
APScheduler setup with SQLite jobstore for persistent scheduling.
Handles time-gated interview activation and session expiration.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging
import threading
import asyncio
from config import settings
from database import SessionLocal, InterviewSession, SessionStatus

logger = logging.getLogger(__name__)

# APScheduler configuration
jobstores = {
    'default': SQLAlchemyJobStore(url=f'sqlite:///{settings.scheduler_jobstore_path}')
}

executors = {
    'default': ThreadPoolExecutor(max_workers=1)  # Sequential execution only
}

job_defaults = {
    'coalesce': True,  # Combine missed runs into one
    'max_instances': 1,  # Never run same job in parallel
    'misfire_grace_time': 300  # 5 minutes grace for missed jobs
}

# Global scheduler instance
scheduler = BackgroundScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
    timezone='UTC'
)


def _run_eval_pipeline_in_background(room_id: str, now: datetime):
    """Runs the async graph in a new event loop inside a background thread."""
    from agents.orchestrator import interview_graph
    
    chat_state = {
        "messages": [],
        "room_id": room_id,
        "status": "COMPLETED"
    }
    
    try:
        logger.info(f"🚀 Sweeper: Starting post-interview pipeline for {room_id} in background thread")
        # Run the graph in a dedicated event loop for this thread
        asyncio.run(interview_graph.ainvoke(chat_state))
        
        db = SessionLocal()
        session = db.query(InterviewSession).filter(InterviewSession.room_id == room_id).first()
        if session:
            session.report_generated_at = now
            session.status = SessionStatus.COMPLETED
            db.commit()
            logger.info(f"✅ Sweeper: Report generated and completed {room_id}")
        db.close()
        
    except Exception as eval_err:
        logger.error(f"❌ Sweeper: Evaluation failed for {room_id}: {eval_err}", exc_info=True)
        db = SessionLocal()
        session = db.query(InterviewSession).filter(InterviewSession.room_id == room_id).first()
        if session:
            session.report_retry_count = getattr(session, 'report_retry_count', 0) + 1
            session.status = SessionStatus.ACTIVE  # Keep active to show Report Failed
            db.commit()
        db.close()

def trigger_evaluation(room_id: str, db: Session, session: InterviewSession, now: datetime):
    """Run the evaluation and report pipeline for a completed or disconnected interview."""
    # Spawn a background thread to avoid blocking the scheduler's single worker thread
    thread = threading.Thread(target=_run_eval_pipeline_in_background, args=(room_id, now))
    thread.daemon = True
    thread.start()


def state_machine_sweeper():
    """
    Runs every 60 seconds to enforce state machine rules:
    1. PENDING > scheduled_at + 15m -> EXPIRED
    2. DISCONNECTED > disconnected_at + 15m -> artificial finish -> EVALUATE -> COMPLETED
    3. ACTIVE (Report generation retries or absolute timeouts) -> EVALUATE
    """
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        
        # 1. Process PENDING -> EXPIRED
        pending_sessions = db.query(InterviewSession).filter(
            InterviewSession.status == SessionStatus.PENDING
        ).all()
        
        for session in pending_sessions:
            if now > session.scheduled_at + timedelta(minutes=15):
                logger.info(f"Sweeper: Session {session.room_id} EXPIRED (No show)")
                session.status = SessionStatus.EXPIRED
                session.updated_at = now
        
        # 2. Process DISCONNECTED -> COMPLETED
        disconnected_sessions = db.query(InterviewSession).filter(
            InterviewSession.status == SessionStatus.DISCONNECTED
        ).all()
        
        for session in disconnected_sessions:
            if session.disconnected_at and now > session.disconnected_at + timedelta(minutes=15):
                logger.info(f"Sweeper: Session {session.room_id} dropped for 15m. Forcing completion.")
                session.finished_at = now
                session.updated_at = now
                db.commit() # Commit the finished_at first
                
                # Trigger eval
                trigger_evaluation(session.room_id, db, session, now)
                
        # 3. Process ACTIVE requiring report retry or timeout
        active_sessions = db.query(InterviewSession).filter(
            InterviewSession.status == SessionStatus.ACTIVE
        ).all()
        
        for session in active_sessions:
            # If it's already finished (from WebSocket) but we don't have a report yet, and we haven't hit the retry limit
            if session.finished_at and not session.report_generated_at and session.report_retry_count < 3:
                # Add a 2 minute delay between retries
                if session.updated_at and now > session.updated_at + timedelta(minutes=2):
                    logger.info(f"Sweeper: Retrying report generation for {session.room_id}")
                    session.updated_at = now
                    db.commit()
                    trigger_evaluation(session.room_id, db, session, now)
            
            # Hard fallback: if active for over 2 hours, force finish
            if getattr(session, 'activated_at', None) and not session.finished_at:
                if now > session.activated_at + timedelta(minutes=120):
                    logger.warning(f"Sweeper: Session {session.room_id} active for >2hrs. Force closing.")
                    session.finished_at = now
                    session.updated_at = now
                    db.commit()
                    trigger_evaluation(session.room_id, db, session, now)

        db.commit()
    except Exception as e:
        logger.error(f"Sweeper error: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def arm_activation_job(room_id: str, scheduled_at: datetime) -> bool:
    """Deprecated: State is managed by the sweeper."""
    return True

def cancel_activation_job(room_id: str) -> bool:
    """Deprecated: State is managed by the sweeper."""
    return True


def start_scheduler():
    """Start the APScheduler background process."""
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started successfully")
        
        # Completely remove any legacy point-in-time jobs from jobstore
        legacy_jobs = scheduler.get_jobs()
        for job in legacy_jobs:
            if job.id.startswith('activate_') or job.id.startswith('expire_'):
                scheduler.remove_job(job.id)
                logger.info(f"Removed legacy point-in-time job: {job.id}")
        
        # Add the singular sweeper job if it doesn't exist
        scheduler.add_job(
            state_machine_sweeper,
            'interval',
            seconds=60,
            id='state_machine_sweeper',
            replace_existing=True,
            misfire_grace_time=30
        )
        logger.info("Registered 60-second state_machine_sweeper job.")


def shutdown_scheduler():
    """Gracefully shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("APScheduler shut down gracefully")


# Expose scheduler instance for external use
__all__ = [
    'scheduler',
    'start_scheduler',
    'shutdown_scheduler',
    'arm_activation_job',
    'cancel_activation_job'
]
