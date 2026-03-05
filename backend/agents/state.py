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
    
    # Error state
    error: Optional[str]
