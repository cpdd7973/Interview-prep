from agents.interviewer_agent import interviewer_node
from agents.state import InterviewState
import logging

# Set up logging to console to see what's happening
logging.basicConfig(level=logging.INFO)

def test_multi_turn():
    state: InterviewState = {
        "room_id": "test-room",
        "candidate_name": "Chander",
        "candidate_email": "chander@example.com",
        "job_role": "React Developer",
        "company": "Adobe",
        "interviewer_designation": "Senior Engineer",
        "status": "ACTIVE",
        "scheduled_at": "",
        "messages": [],
        "questions_asked": [],
        "current_question_id": None,
        "daily_room_url": "",
        "evaluation": None,
        "error": None
    }
    
    print("\n--- TURN 1: INITIAL GREETING ---")
    res1 = interviewer_node(state)
    print(f"AI: {res1['messages'][-1].content}")
    
    # Simulate state update like main.py
    state["messages"].extend(res1["messages"])
    if "current_question_id" in res1: state["current_question_id"] = res1["current_question_id"]
    if "questions_asked" in res1: state["questions_asked"].extend(res1["questions_asked"])
    
    print("\n--- TURN 2: CANDIDATE ANSWERS ---")
    from langchain_core.messages import HumanMessage
    state["messages"].append(HumanMessage(content="A controlled component is one where React state handles the value, while uncontrolled uses refs."))
    
    res2 = interviewer_node(state)
    print(f"AI: {res2['messages'][-1].content}")
    
    if res2.get("current_question_id") != res1.get("current_question_id") or res2.get("current_question_id") is None:
        print("\n✅ AGENT MOVED TO NEXT QUESTION (OR COMPLETED)")
    else:
        print("\n❌ AGENT STUCK ON SAME QUESTION")

if __name__ == "__main__":
    test_multi_turn()
