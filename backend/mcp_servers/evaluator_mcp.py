"""
Evaluator MCP Server
Handles scoring transcripts and providing AI feedback.
"""
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import logging
import json
import os
import re

from utils.groq_client import llm_client

logger = logging.getLogger(__name__)

def extract_json(content: str) -> str:
    """Robustly extract a JSON object from a string."""
    # Strip markdown if present
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    import json_repair
    try:
        # Use json_repair or simple regex fallback
        parsed = json.loads(content)
        return json.dumps(parsed)
    except Exception:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return match.group(0)
    return content.strip()


# Load prompt template
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
prompt_path = os.path.join(base_dir, "prompts", "evaluator_system.txt")
try:
    with open(prompt_path, "r", encoding="utf-8") as f:
        EVALUATOR_PROMPT = f.read()
except Exception as e:
    logger.error(f"Failed to load evaluator prompt: {e}")
    EVALUATOR_PROMPT = ""

# Input Schemas
class ScoreAnswerInput(BaseModel):
    question: str = Field(..., description="The interview question")
    answer: str = Field(..., description="The candidate's answer")
    ideal_answer: str = Field(..., description="The ideal or model answer")

class CalculateDimensionScoresInput(BaseModel):
    transcript: List[Dict[str, Any]] = Field(..., description="Full interview transcript")
    question_bank: List[Dict[str, Any]] = Field(..., description="Questions asked with ideal answers")
    job_role: str = Field("Unknown", description="Job role for context")
    company: str = Field("Unknown", description="Company name")
    candidate_name: str = Field("Candidate", description="Candidate name")
    
class GenerateFeedbackInput(BaseModel):
    scores: Dict[str, float] = Field(..., description="Calculated scores")
    transcript: List[Dict[str, Any]] = Field(..., description="Transcript")

class EvaluatorMCPServer:
    def __init__(self):
        self.name = "evaluator-mcp-server"
        self.version = "1.0.0"
        self.tools = {
            "score_answer": self.score_answer,
            "calculate_dimension_scores": self.calculate_dimension_scores,
            "generate_feedback": self.generate_feedback
        }

    async def score_answer(self, input_data: ScoreAnswerInput) -> Dict[str, Any]:
        """Score a single response against ideal answer"""
        try:
            prompt = f"""Evaluate this interview answer. Return ONLY a JSON object with 'score' (0-10) and 'rationale' (1 sentence).
Question: {input_data.question}
Ideal Answer: {input_data.ideal_answer}
Candidate Answer: {input_data.answer}"""
            
            from langchain_core.messages import HumanMessage
            logger.info("Evaluating single answer via LLM...")
            # Use async LLM invocation
            response_text = await llm_client.invoke_async([HumanMessage(content=prompt)])
            
            logger.info(f"Answer LLM Raw Output: {response_text}")
            content = extract_json(response_text)
            
            result = json.loads(content)
            
            return {
                "success": True,
                "score": float(result.get("score", 0)),
                "rationale": result.get("rationale", "")
            }
        except Exception as e:
            logger.error(f"❌ Error scoring answer: {e}")
            return {"success": False, "error": str(e)}

    async def calculate_dimension_scores(self, input_data: CalculateDimensionScoresInput) -> Dict[str, Any]:
        """Calculates multi-dimensional scores for the entire transcript"""
        try:
            # Optimize prompt by truncating deeply massive transcripts if necessary
            formatted_transcript = "--- Transcript Start ---\n"
            for t in input_data.transcript:
                formatted_transcript += f"{t.get('speaker', 'Unknown')}: {t.get('content', '')}\n"
            formatted_transcript += "--- Transcript End ---\n"
                
            qb_str = json.dumps(input_data.question_bank, indent=2)
            
            prompt = EVALUATOR_PROMPT.format(
                job_role=input_data.job_role,
                company=input_data.company,
                candidate_name=input_data.candidate_name,
                transcript=formatted_transcript,
                question_bank=qb_str
            )
            
            # Reiterate to strictly return JSON
            prompt += "\n\nCRITICAL: YOU MUST RETURN ONLY A VALID JSON OBJECT WITH EXACTLY THESE KEYS: technical_score, communication_score, problem_solving_score, behavioral_score, confidence_score, overall_score, qualitative_feedback. DO NOT RETURN ANY OTHER TEXT."
            
            from langchain_core.messages import SystemMessage
            logger.info(f"Evaluating entire transcript for {input_data.candidate_name}...")
            # Use async LLM invocation
            response_text = await llm_client.invoke_async([SystemMessage(content=prompt)])
            
            logger.info(f"Transcript LLM Raw Output: {response_text}")
            content = extract_json(response_text)
            
            result = json.loads(content)
            
            tech = float(result.get("technical_score", 0))
            comm = float(result.get("communication_score", 0))
            prob = float(result.get("problem_solving_score", 0))
            behav = float(result.get("behavioral_score", 0))
            conf = float(result.get("confidence_score", 0))
            
            # Compute mathematically to avoid LLM hallucinations
            overall = round((tech * 0.30) + (comm * 0.20) + (prob * 0.25) + (behav * 0.15) + (conf * 0.10), 1)
            
            verdict = "PASS" if overall >= 6.0 else "FAIL"
            if 5.0 <= overall < 6.0:
                verdict = "MAYBE"
                
            feedback = result.get("qualitative_feedback", "Not provided")
            feedback = f"VERDICT: {verdict}\n\n{feedback}"
            
            return {
                "success": True,
                "scores": {
                    "technical_score": tech,
                    "communication_score": comm,
                    "problem_solving_score": prob,
                    "behavioral_score": behav,
                    "confidence_score": conf,
                    "overall_score": overall
                },
                "feedback": feedback
            }
        except Exception as e:
            logger.error(f"❌ Error calculating scores: {e}")
            return {"success": False, "error": str(e)}

    def generate_feedback(self, input_data: GenerateFeedbackInput) -> Dict[str, Any]:
        """Provides feedback summary. Largely handled in calculate_dimension_scores, kept for completeness."""
        return {
            "success": True, 
            "message": "Qualitative feedback generation is embedded in calculate_dimension_scores response.",
            "scores": input_data.scores
        }

# Singleton instance
evaluator_mcp = EvaluatorMCPServer()
