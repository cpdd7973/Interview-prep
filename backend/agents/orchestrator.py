"""
Agent Orchestrator
Defines the LangGraph StateGraph that connects all agents together.
"""
import logging
from langgraph.graph import StateGraph, START, END

from agents.state import InterviewState
from agents.scheduler_agent import schedule_interview_node
from agents.interviewer_agent import interviewer_node
from agents.evaluator_agent import evaluator_node
from agents.report_agent import report_node

logger = logging.getLogger(__name__)

def route_after_interview(state: InterviewState) -> str:
    """
    Decides where to go after the interviewer node finishes its turn.
    If the interview is complete, it triggers evaluation.
    Otherwise, it returns to the user.
    """
    status = state.get("status")
    if status == "COMPLETED":
        return "evaluator"
    return END

def create_interview_graph() -> StateGraph:
    """
    Builds and compiles the LangGraph for the interview system.
    """
    # 1. Initialize StateGraph
    workflow = StateGraph(InterviewState)
    
    # 2. Add Nodes
    workflow.add_node("scheduler", schedule_interview_node)
    workflow.add_node("interviewer", interviewer_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("report", report_node)
    
    # 3. Define Entry Point Routing
    # We use a conditional edge from START based on session status
    def route_start(state: InterviewState) -> str:
        status = state.get("status", "PENDING")
        if status == "PENDING":
            return "scheduler"
        elif status == "ACTIVE":
            return "interviewer"
        elif status == "COMPLETED":
            return "evaluator"
        elif status == "EVALUATED":
            return "report"
        return END

    workflow.add_conditional_edges(START, route_start)
    
    # 4. Define standard edges
    workflow.add_edge("scheduler", END)
    
    # Interviewer routes conditionally
    workflow.add_conditional_edges("interviewer", route_after_interview)
    
    # Evaluator always goes to report
    workflow.add_edge("evaluator", "report")
    
    # Report ends the workflow
    workflow.add_edge("report", END)
    
    # 5. Compile Graph
    app = workflow.compile()
    logger.info("✅ Interview LangGraph compiled successfully.")
    
    return app

# Singleton compiled graph
interview_graph = create_interview_graph()
