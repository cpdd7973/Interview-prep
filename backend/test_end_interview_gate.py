"""
Regression tests for the hard code-level gate on premature "end_interview"
decisions (agents/interviewer_agent.py). See CLAUDE.md history / plan for
the root cause: the LLM was previously trusted unconditionally, and a real
session ended at 9.9 elapsed minutes (min=30) with topics still uncovered.

Not folded into test_agent.py -- that file's test_multi_turn calls
interviewer_node synchronously without awaiting it and omits several
required InterviewState keys, so it's already broken independent of this
fix and out of scope to repair here.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from agents.interviewer_agent import interviewer_node, _is_end_interview_premature
from agents.state import InterviewState


def _base_state(topics_covered, elapsed_minutes_patch_target="agents.interviewer_agent.calculate_elapsed_minutes"):
    state: InterviewState = {
        "room_id": "test-room",
        "candidate_name": "Test Candidate",
        "candidate_email": "test@example.com",
        "job_role": "Software Engineer",
        "job_description": "",
        "company": "TestCo",
        "interviewer_designation": "Senior Engineer",
        "status": "ACTIVE",
        "scheduled_at": "",
        "daily_room_url": "",
        "messages": [HumanMessage(content="What does success look like in this role?")],
        "current_question_id": None,
        "questions_asked": [],
        "questions_state": {},
        "evaluation": None,
        "skill_plan": {
            "foundation_skills": ["A"],
            "core_skills": ["B", "C"],
            "secondary_skills": ["D", "E"],
        },
        "topics_covered": topics_covered,
        "current_phase": "core",
        "interview_started_at": "2026-07-02T00:00:00",
        "error": None,
    }
    return state


def test_is_end_interview_premature_table():
    # Under the time floor -> always premature, regardless of phase.
    assert _is_end_interview_premature(10.0, "secondary", 30) is True
    assert _is_end_interview_premature(29.9, "secondary", 30) is True
    # Time floor met but coverage phase not yet "secondary" -> still premature.
    assert _is_end_interview_premature(31.0, "core", 30) is True
    assert _is_end_interview_premature(31.0, "foundation", 30) is True
    # Both conditions satisfied -> legitimate.
    assert _is_end_interview_premature(31.0, "secondary", 30) is False
    assert _is_end_interview_premature(30.0, "secondary", 30) is False


def test_premature_end_is_blocked_and_corrected():
    """Elapsed well under the minimum: gate must block, corrective call succeeds."""
    end_attempt = (
        '{"action": "end_interview", "spoken_response": "Great, thanks! Goodbye!", '
        '"topic_covered": null, "current_phase": "wrap_up"}'
    )
    corrected = (
        '{"action": "next_question", '
        '"spoken_response": "Good question! Let\'s continue -- tell me about D."}'
    )
    responses = iter([end_attempt, corrected])

    async def fake_invoke(_messages):
        return next(responses)

    state = _base_state(topics_covered=["A", "B", "C"])

    with patch("agents.interviewer_agent.llm_client.invoke_async", new=AsyncMock(side_effect=fake_invoke)), \
         patch("agents.interviewer_agent.calculate_elapsed_minutes", return_value=10.0):
        result = asyncio.run(interviewer_node(state))

    assert result.get("status") != "COMPLETED"
    assert result["messages"][0].content == "Good question! Let's continue -- tell me about D."


def test_premature_end_falls_back_deterministically_if_correction_also_refuses():
    """If the corrective call itself tries to end again, use the deterministic fallback."""
    end_attempt = (
        '{"action": "end_interview", "spoken_response": "Goodbye!", '
        '"topic_covered": null, "current_phase": "wrap_up"}'
    )
    corrective_also_ends = '{"action": "end_interview", "spoken_response": "No really, goodbye!"}'
    responses = iter([end_attempt, corrective_also_ends])

    async def fake_invoke(_messages):
        return next(responses)

    state = _base_state(topics_covered=["A", "B", "C"])

    with patch("agents.interviewer_agent.llm_client.invoke_async", new=AsyncMock(side_effect=fake_invoke)), \
         patch("agents.interviewer_agent.calculate_elapsed_minutes", return_value=5.0):
        result = asyncio.run(interviewer_node(state))

    assert result.get("status") != "COMPLETED"
    assert "D" in result["messages"][0].content  # first remaining topic, per fallback template
    assert len(result["messages"][0].content) > 0


def test_premature_end_falls_back_if_corrective_call_raises():
    """If the corrective LLM call itself errors, fall back rather than crash or end."""
    end_attempt = (
        '{"action": "end_interview", "spoken_response": "Goodbye!", '
        '"topic_covered": null, "current_phase": "wrap_up"}'
    )
    responses = iter([end_attempt])

    async def fake_invoke(_messages):
        try:
            return next(responses)
        except StopIteration:
            raise TimeoutError("simulated LLM timeout")

    state = _base_state(topics_covered=["A", "B", "C"])

    with patch("agents.interviewer_agent.llm_client.invoke_async", new=AsyncMock(side_effect=fake_invoke)), \
         patch("agents.interviewer_agent.calculate_elapsed_minutes", return_value=5.0):
        result = asyncio.run(interviewer_node(state))

    assert result.get("status") != "COMPLETED"
    assert len(result["messages"][0].content) > 0


def test_legitimate_end_after_minimum_and_full_coverage_is_allowed():
    """Regression guard: a genuine end_interview past the minimum must still work."""
    end_attempt = (
        '{"action": "end_interview", "spoken_response": "Thanks, that concludes our interview!", '
        '"topic_covered": "D", "current_phase": "secondary"}'
    )

    async def fake_invoke(_messages):
        return end_attempt

    # foundation ["A"] and core ["B","C"] both satisfied -> determine_phase == "secondary"
    state = _base_state(topics_covered=["A", "B", "C", "D", "E"])

    with patch("agents.interviewer_agent.llm_client.invoke_async", new=AsyncMock(side_effect=fake_invoke)), \
         patch("agents.interviewer_agent.calculate_elapsed_minutes", return_value=31.0):
        result = asyncio.run(interviewer_node(state))

    assert result.get("status") == "COMPLETED"


if __name__ == "__main__":
    test_is_end_interview_premature_table()
    test_premature_end_is_blocked_and_corrected()
    test_premature_end_falls_back_deterministically_if_correction_also_refuses()
    test_premature_end_falls_back_if_corrective_call_raises()
    test_legitimate_end_after_minimum_and_full_coverage_is_allowed()
    print("All end_interview gate tests passed.")
