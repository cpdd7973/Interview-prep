"""
Interviewer Agent Node
Conducts the conversational interview using LLMs dynamically.
"""
from typing import Dict, Any
import logging
import json
import re
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.state import InterviewState
from utils.groq_client import llm_client

logger = logging.getLogger(__name__)

INTERVIEWER_PROMPT = """
You are a professional technical interviewer for {company}.
You are interviewing {candidate_name} for the position of {job_role}.
Your title is {interviewer_designation}.

You are in full control of the interview. There is no hardcoded script.
You must assess the candidate's technical skills dynamically.

INSTRUCTIONS:
1. You MUST ALWAYS respond with a SINGLE valid JSON object. Do not include markdown formatting or extra text.
2. The JSON object must match the following schema exactly:
   {{
     "score_of_last_answer": <integer 0-10, or null if first turn>,
     "evaluation_notes": "<Brief private note on candidate's performance>",
     "action": "<follow_up | next_question | end_interview>",
     "spoken_response": "<Your conversational response/question to the candidate>"
   }}
3. If this is the START of the interview, greet the candidate warmly by name, briefly explain the format, and ask the very first question using the "next_question" action.
4. Keep all your `spoken_response` text conversational, concise, and under 4 sentences.
5. Base your decisions dynamically on the conversation history. If the candidate gives a weak or incomplete answer, use "follow_up". If they answered well, score highly and move on using "next_question" to cover a different aspect of {job_role}.
6. You should aim to ask around 3 to 5 main functional questions before ending the interview.
7. End the interview gracefully when sufficient topics have been covered or if the candidate explicitly requests to stop.

WARNING: Output NOTHING BUT valid JSON. No ```json markdown blocks.
"""

def extract_json(text: str) -> dict:
    original = text
    # Strip markdown if present just in case
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM JSON: {original}")
        # Fallback heuristic
        return {"action": "next_question", "spoken_response": text, "score_of_last_answer": None}

async def interviewer_node(state: InterviewState) -> Dict[str, Any]:
    """
    LangGraph node for conducting the interview conversation dynamically.
    """
    logger.info(f"Dynamic AI Interviewer Agent initialized for session")
    
    if state.get("status") != "ACTIVE":
        return state
        
    messages = list(state.get("messages", []))
    
    # Check if candidate explicitly asked to stop in the last message
    if messages and isinstance(messages[-1], HumanMessage):
        last_human_text = messages[-1].content.lower()
        if any(w in last_human_text for w in ["stop the interview", "i'm done", "end interview", "that's all"]):
            messages.append(AIMessage(content="Thank you for your time today. That concludes our interview!"))
            return {
                "status": "COMPLETED",
                "messages": messages
            }

    # Build the Prompt
    sys_prompt = INTERVIEWER_PROMPT.format(
        company=state.get("company", "our company"),
        candidate_name=state.get("candidate_name", "the candidate"),
        job_role=state.get("job_role", "this role"),
        interviewer_designation=state.get("interviewer_designation", "Senior Engineer")
    )
    
    # Inject system prompt at the beginning of the message history
    llm_messages = [SystemMessage(content=sys_prompt)] + messages
    
    try:
        # Invoke LLM
        response_text = await llm_client.invoke_async(llm_messages)
        
        # Process JSON Response
        decision = extract_json(response_text)
        action = decision.get("action", "next_question")
        spoken_response = decision.get("spoken_response", "Could you elaborate on that?")
        
        # Log real-time evaluation logic
        score = decision.get("score_of_last_answer")
        notes = decision.get("evaluation_notes")
        if score is not None:
            logger.info(f"Answer Scored: {score}/10. Notes: {notes}")
        
        if action == "end_interview":
            messages.append(AIMessage(content=spoken_response))
            logger.info("LLM decided to end the interview.")
            return {
                "status": "COMPLETED",
                "messages": [AIMessage(content=spoken_response)] # Append the closing message
            }
            
        else:
            # next_question or follow_up
            logger.info(f"LLM decided action: {action}")
            return {
                "messages": [AIMessage(content=spoken_response)]
            }
        
    except Exception as e:
        import traceback
        logger.error(f"Interviewer agent failed: {e}")
        logger.error(traceback.format_exc())
        return {
            "error": str(e),
            "messages": [AIMessage(content="I'm sorry, I'm having a technical issue. Could you repeat that?")]
        }
