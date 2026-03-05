"""
SQLite database schema and connection management.
All tables designed for low-memory footprint and fast queries.
"""
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, DateTime, 
    Text, JSON, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum
from config import settings

# Database engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    pool_pre_ping=True,
    echo=settings.log_level == "DEBUG"
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Enums
class SessionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class QuestionDifficulty(str, enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class QuestionType(str, enum.Enum):
    TECHNICAL = "TECHNICAL"
    BEHAVIORAL = "BEHAVIORAL"
    SITUATIONAL = "SITUATIONAL"


class Speaker(str, enum.Enum):
    AI = "AI"
    CANDIDATE = "CANDIDATE"


# Models
class Candidate(Base):
    """Stores candidate PII separately for GDPR compliance."""
    __tablename__ = "candidates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sessions = relationship("InterviewSession", back_populates="candidate", cascade="all, delete-orphan")


class InterviewSession(Base):
    """Represents a scheduled or active interview session."""
    __tablename__ = "interview_sessions"
    
    room_id = Column(String(36), primary_key=True)  # UUID
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    job_role = Column(String(100), nullable=False, index=True)
    company = Column(String(255), nullable=False)
    interviewer_designation = Column(String(255), nullable=False)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    status = Column(SQLEnum(SessionStatus), default=SessionStatus.PENDING, index=True)
    daily_room_url = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    candidate = relationship("Candidate", back_populates="sessions")
    transcript_chunks = relationship("TranscriptChunk", back_populates="session", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", back_populates="session", uselist=False, cascade="all, delete-orphan")


class TranscriptChunk(Base):
    """Stores conversation transcript in chunks."""
    __tablename__ = "transcript_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(String(36), ForeignKey("interview_sessions.room_id"), nullable=False, index=True)
    speaker = Column(SQLEnum(Speaker), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    
    # Relationships
    session = relationship("InterviewSession", back_populates="transcript_chunks")
    question = relationship("Question")


class Question(Base):
    """Question bank for different roles and topics."""
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(100), nullable=False, index=True)
    topic = Column(String(255), nullable=False, index=True)
    difficulty = Column(SQLEnum(QuestionDifficulty), nullable=False, index=True)
    type = Column(SQLEnum(QuestionType), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    ideal_answer = Column(Text, nullable=True)  # For evaluation reference
    tags = Column(JSON, default=list)  # Array of strings
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Evaluation(Base):
    """Stores evaluation scores and feedback for completed interviews."""
    __tablename__ = "evaluations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(String(36), ForeignKey("interview_sessions.room_id"), nullable=False, unique=True, index=True)
    technical_score = Column(Float, nullable=False)  # 0-10
    communication_score = Column(Float, nullable=False)  # 0-10
    problem_solving_score = Column(Float, nullable=False)  # 0-10
    behavioral_score = Column(Float, nullable=False)  # 0-10
    confidence_score = Column(Float, nullable=False)  # 0-10
    overall_score = Column(Float, nullable=False)  # 0-10
    qualitative_feedback = Column(Text, nullable=True)
    report_path = Column(String(500), nullable=True)  # Path to generated PDF
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    session = relationship("InterviewSession", back_populates="evaluation")


# Database initialization
def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully")


def get_db():
    """Dependency for FastAPI routes to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    # Run this file directly to initialize the database
    init_db()
