"""
Evaluator Agent Node
Processes the interview transcript and passes it to the Evaluator MCP
to generate dimension scores and qualitative feedback.
"""
from typing import Dict, Any, List
import logging
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage

from agents.state import InterviewState
from mcp_servers.evaluator_mcp import evaluator_mcp, CalculateDimensionScoresInput
from mcp_servers.question_bank_mcp import question_bank_mcp, GetQuestionsInput
from database import SessionLocal, Evaluation

logger = logging.getLogger(__name__)

async def evaluator_node(state: InterviewState) -> Dict[str, Any]:
    """
    LangGraph node for evaluating the completed interview.
    """
    logger.info(f"📊 Evaluator Agent processing interview for {state.get('candidate_name')}")
    
    # Check if we should evaluate
    if state.get("status") not in ["COMPLETED", "ACTIVE"]:
        logger.info("Session is not COMPLETED/ACTIVE. Skipping evaluation.")
        return state
        
    messages = state.get("messages", [])
    if not messages:
        logger.warning("No transcript messages to evaluate.")
        return state
        
    # 1. Format Transcript
    formatted_transcript = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            # System instructions, skip from transcript payload
            continue
        elif isinstance(msg, AIMessage):
            formatted_transcript.append({"speaker": "AI", "content": msg.content})
        elif isinstance(msg, HumanMessage):
             formatted_transcript.append({"speaker": "CANDIDATE", "content": msg.content})
        else:
            # Fallback for dict or other types in state
            speaker = "AI" if getattr(msg, "type", "") == "ai" else "CANDIDATE"
            content = getattr(msg, "content", str(msg))
            formatted_transcript.append({"speaker": speaker, "content": content})

    # 2. Build Question Bank Context
    asked_ids = state.get("questions_asked", [])
    question_bank_context = []
    
    if asked_ids:
        # Fetch questions to provide the ideal answers to the evaluator
        resp = question_bank_mcp.get_questions_by_role(GetQuestionsInput(role=state["job_role"], limit=20))
        if resp.get("success"):
            for q in resp["questions"]:
                if q["id"] in asked_ids:
                    question_bank_context.append({
                        "question": q["question_text"],
                        "ideal_answer": q["ideal_answer"] or "Not specified."
                    })
    
    # 3. Call Evaluator MCP
    logger.info("Submitting transcript to Evaluator MCP Server...")
    eval_resp = await evaluator_mcp.calculate_dimension_scores(CalculateDimensionScoresInput(
        transcript=formatted_transcript,
        question_bank=question_bank_context,
        job_role=state.get("job_role", "Unknown"),
        company=state.get("company", "Unknown"),
        candidate_name=state.get("candidate_name", "Unknown")
    ))
    
    if not eval_resp.get("success"):
        logger.error(f"❌ Evaluator failed: {eval_resp.get('error')}")
        return {
            "error": f"Evaluation failed: {eval_resp.get('error')}"
        }
        
    evaluation_data = {
        "scores": eval_resp.get("scores", {}),
        "feedback": eval_resp.get("feedback", "")
    }
    
    # Save to SQLite
    db = SessionLocal()
    try:
        room_id = state.get("room_id")
        if room_id:
            db_eval = Evaluation(
                room_id=room_id,
                technical_score=evaluation_data["scores"].get("technical_score", 0),
                communication_score=evaluation_data["scores"].get("communication_score", 0),
                problem_solving_score=evaluation_data["scores"].get("problem_solving_score", 0),
                behavioral_score=evaluation_data["scores"].get("behavioral_score", 0),
                confidence_score=evaluation_data["scores"].get("confidence_score", 0),
                overall_score=evaluation_data["scores"].get("overall_score", 0),
                qualitative_feedback=evaluation_data["feedback"]
            )
            # Find and delete old if needed (or assume 1-1)
            existing = db.query(Evaluation).filter(Evaluation.room_id == room_id).first()
            if existing:
                db.delete(existing)
            db.add(db_eval)
            db.commit()
            logger.info("💾 Saved Evaluation to SQLite Database.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save evaluation to DB: {e}")
    finally:
        db.close()
    
    logger.info("✅ Evaluation complete.")
    
    # Update State
    return {
        "status": "EVALUATED",
        "evaluation": evaluation_data
    }
