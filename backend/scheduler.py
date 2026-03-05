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


def activate_interview(room_id: str):
    """
    Job function that activates an interview at scheduled time.
    Called by APScheduler exactly at scheduled_at datetime.
    """
    db: Session = SessionLocal()
    try:
        session = db.query(InterviewSession).filter(
            InterviewSession.room_id == room_id
        ).first()
        
        if not session:
            logger.error(f"Session {room_id} not found for activation")
            return
        
        if session.status != SessionStatus.PENDING:
            logger.warning(f"Session {room_id} is {session.status}, cannot activate")
            return
        
        # Update status to ACTIVE
        session.status = SessionStatus.ACTIVE
        session.activated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Interview {room_id} activated successfully")
        
        # Schedule expiration job (60 minutes from now)
        expire_time = datetime.utcnow() + timedelta(minutes=settings.session_timeout_minutes)
        scheduler.add_job(
            expire_interview,
            'date',
            run_date=expire_time,
            args=[room_id],
            id=f"expire_{room_id}",
            replace_existing=True
        )
        
    except Exception as e:
        logger.error(f"Error activating interview {room_id}: {e}")
        db.rollback()
    finally:
        db.close()


def expire_interview(room_id: str):
    """
    Job function that marks interview as EXPIRED if not completed.
    Called 60 minutes after activation.
    """
    db: Session = SessionLocal()
    try:
        session = db.query(InterviewSession).filter(
            InterviewSession.room_id == room_id
        ).first()
        
        if not session:
            logger.error(f"Session {room_id} not found for expiration")
            return
        
        if session.status == SessionStatus.ACTIVE:
            session.status = SessionStatus.EXPIRED
            session.completed_at = datetime.utcnow()
            db.commit()
            logger.info(f"Interview {room_id} expired (not completed in time)")
        else:
            logger.info(f"Interview {room_id} already {session.status}, skipping expiration")
        
    except Exception as e:
        logger.error(f"Error expiring interview {room_id}: {e}")
        db.rollback()
    finally:
        db.close()


def arm_activation_job(room_id: str, scheduled_at: datetime) -> bool:
    """
    Arms the activation job for a scheduled interview.
    Returns True if successful, False otherwise.
    """
    try:
        scheduler.add_job(
            activate_interview,
            'date',
            run_date=scheduled_at,
            args=[room_id],
            id=f"activate_{room_id}",
            replace_existing=True
        )
        logger.info(f"Activation job armed for {room_id} at {scheduled_at}")
        return True
    except Exception as e:
        logger.error(f"Failed to arm activation job for {room_id}: {e}")
        return False


def cancel_activation_job(room_id: str) -> bool:
    """
    Cancels a scheduled activation job (used when interview is rescheduled/cancelled).
    Returns True if successful, False otherwise.
    """
    try:
        job_id = f"activate_{room_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Activation job cancelled for {room_id}")
        
        # Also cancel expiration job if exists
        expire_job_id = f"expire_{room_id}"
        if scheduler.get_job(expire_job_id):
            scheduler.remove_job(expire_job_id)
            logger.info(f"Expiration job cancelled for {room_id}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to cancel job for {room_id}: {e}")
        return False


def start_scheduler():
    """Start the APScheduler background process."""
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started successfully")
        
        # Log existing jobs (useful after restart)
        jobs = scheduler.get_jobs()
        if jobs:
            logger.info(f"Loaded {len(jobs)} existing jobs from jobstore")
            for job in jobs:
                logger.info(f"  - {job.id} scheduled for {job.next_run_time}")
        else:
            logger.info("📋 No existing jobs in jobstore")


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
    'cancel_activation_job',
    'activate_interview',
    'expire_interview'
]
