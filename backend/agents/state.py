"""
State definitions for LangGraph agents.
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
import operator


class InterviewState(TypedDict):
    """
    State dictionary matching the InterviewSession schema but
    live for the LangGraph execution.
    """

    # Core identifying info
    room_id: str
    candidate_name: str
    candidate_email: str
    job_role: str
    job_description: Optional[str]
    company: str
    interviewer_designation: str

    # Session state
    status: str
    scheduled_at: str
    daily_room_url: str

    # LangGraph conversational state
    # Annotated with operator.add so messages append instead of overwrite
    messages: Annotated[List[BaseMessage], operator.add]

    # Internal agent scratchpad / workflow state
    current_question_id: Optional[int]
    questions_asked: Annotated[List[int], operator.add]
    questions_state: Dict[int, str]
    evaluation: Optional[Dict[str, Any]]

    # JD-aware interview tracking
    skill_plan: Optional[Dict[str, List[str]]]  # Extracted from JD at start
    topics_covered: List[str]  # Skills assessed so far
    current_phase: str  # introduction|foundation|core|secondary|wrap_up
    interview_started_at: Optional[str]  # ISO timestamp for 30-min tracking

    # Adaptive difficulty tracking -- transient (not persisted to the DB), a
    # reconnect losing a turn or two of "difficulty momentum" is a minor UX
    # blip, not a correctness bug worth a schema change.
    recent_scores: List[int]  # last few score_of_last_answer values, most recent last

    # Post-interview pipeline output
    report_path: Optional[str]
    email_failed: Optional[bool]

    # Error state
    error: Optional[str]
