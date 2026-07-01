"""
Interviewer Agent Node
Conducts JD-aware conversational interviews using LLMs dynamically.
Extracts skills from the Job Description, follows a progressive
foundation → core → secondary flow, and uses elapsed time + coverage
tracking to decide when to end (minimum 30 minutes).
"""

from typing import Dict, Any, List, Optional
import logging
import json
import re
from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.state import InterviewState
from utils.groq_client import llm_client
from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt: Extract structured skill plan from JD (runs once at interview start)
# ---------------------------------------------------------------------------
SKILL_EXTRACTION_PROMPT = """
Analyze this job description and extract a structured interview plan.
Return ONLY valid JSON matching this schema exactly:
{{
  "foundation_skills": ["skill1", "skill2"],
  "core_skills": ["skill1", "skill2", "skill3"],
  "secondary_skills": ["skill1", "skill2"]
}}

Rules:
- foundation_skills: Prerequisite/baseline skills the candidate must know
  (e.g. JavaScript, TypeScript for a React role; Python basics for a Django role).
  Keep to 2-3 items.
- core_skills: Primary competencies directly tied to the job title.
  Keep to 3-5 items.
- secondary_skills: Additional tools/technologies explicitly mentioned in the JD
  (e.g. AWS, Docker, CI/CD, specific databases). Keep to 2-4 items.
- If no job description is provided, infer sensible skills from the job title alone.
- Order each list by importance.

Job Title: {job_role}
Job Description:
{job_description}

WARNING: Output NOTHING but valid JSON. No markdown, no explanation.
"""

# ---------------------------------------------------------------------------
# Main Interviewer System Prompt (injected every turn)
# ---------------------------------------------------------------------------
INTERVIEWER_PROMPT = """
You are a professional technical interviewer for {company}.
You are interviewing {candidate_name} for the position of {job_role}.
Your title is {interviewer_designation}.

SKILL PLAN (extracted from the Job Description):
- Foundation skills: {foundation_skills}
- Core skills: {core_skills}
- Secondary/JD-specific skills: {secondary_skills}

INTERVIEW FLOW — follow this structure strictly:
1. INTRODUCTION: Your very first question MUST be an introductory question like
   "Could you tell me a bit about yourself, your background, and what excites you
   about this role?" Listen carefully to their response — use their background,
   experience, and interests to tailor your subsequent questions.
2. FOUNDATION: Ask 2-3 questions on prerequisite/baseline skills to gauge fundamentals.
3. CORE: Deep-dive with 3-5 questions on primary role competencies. Use follow-ups
   for weak or incomplete answers.
4. SECONDARY: Ask 2-3 questions on JD-specific technologies the candidate should know.
5. WRAP-UP: Thank the candidate warmly and end gracefully.

COVERAGE SO FAR:
- Topics already covered: {topics_covered}
- Topics remaining: {topics_remaining}
- Current phase: {current_phase}

TIME CONTEXT:
- Interview started: {interview_start_time}
- Elapsed time: {elapsed_minutes} minutes
- MINIMUM interview duration: {min_duration_minutes} minutes

ENDING RULES:
- You MUST NOT use "end_interview" before {min_duration_minutes} minutes have elapsed.
- You MUST NOT use "end_interview" if major skill categories still have uncovered topics.
- You SHOULD use "end_interview" when BOTH conditions are met:
  (a) At least {min_duration_minutes} minutes have elapsed, AND
  (b) You have adequately covered foundation, core, and secondary skills.
- EXCEPTION: If the candidate explicitly asks to stop or end the interview, you may
  end early regardless of time.
- NOTE: These rules are also enforced in code. Attempting to end early will be
  rejected and you will be asked to continue instead.

RESPONSE FORMAT — respond with a SINGLE valid JSON object, no markdown:
{{
  "score_of_last_answer": <integer 0-10, or null if this is the first turn>,
  "evaluation_notes": "<Brief private note on candidate's last answer>",
  "topic_covered": "<skill or topic this exchange assessed, e.g. 'React Hooks', or 'Introduction' for the intro>",
  "current_phase": "<introduction|foundation|core|secondary|wrap_up>",
  "action": "<follow_up|next_question|end_interview>",
  "spoken_response": "<Your conversational response/question to the candidate>"
}}

STYLE:
- Keep spoken_response conversational, concise, and under 4 sentences.
- Acknowledge good answers briefly before moving on.
- For weak answers, ask ONE targeted follow-up before moving to the next topic.
- Transition between phases naturally — do NOT announce "now entering core phase".
- Adapt questions based on the candidate's introduction and prior answers.

WARNING: Output NOTHING BUT valid JSON. No ```json markdown blocks.
"""

# ---------------------------------------------------------------------------
# Corrective re-prompt — used ONLY when the hard end-interview gate (see
# _is_end_interview_premature) overrides a premature LLM "end_interview"
# decision. Keeps the candidate-facing response natural instead of a jarring
# non-sequitur, and hard-forbids ending again this turn.
# ---------------------------------------------------------------------------
END_OVERRIDE_CORRECTION_PROMPT = """
You are the same technical interviewer for {company}, interviewing {candidate_name}
for {job_role}.

You just attempted to end the interview, but it CANNOT end yet:
- Minimum required duration: {min_duration} minutes (only {elapsed_minutes} have elapsed)
- Skills still needing coverage: {topics_remaining}

Your previous drafted response (written as if this were the final turn) was:
"{original_spoken_response}"

INSTRUCTIONS:
- Do NOT end the interview this turn. "action" MUST be "follow_up" or "next_question" --
  NEVER "end_interview", no matter what the candidate just said.
- If the previous drafted response above already answers the candidate's last message well,
  reuse that part of it, but remove any goodbye/closing/wrap-up language.
- Then continue the interview naturally by asking a new question on one of the remaining
  topics listed above. Do not mention that a correction happened.
- Keep it conversational and under 4 sentences, consistent with normal interview style.

RESPONSE FORMAT — respond with a SINGLE valid JSON object, no markdown:
{{
  "action": "<follow_up|next_question>",
  "spoken_response": "<your corrected conversational response>"
}}

WARNING: Output NOTHING but valid JSON. No ```json markdown blocks.
"""

# Deterministic last-resort line -- used only if BOTH the original LLM call and the
# corrective re-prompt try to end early (or the corrective call fails outright).
FALLBACK_TRANSITION_TEMPLATE = (
    "Thanks for that. Before we wrap up, I'd like to cover a bit more ground -- "
    "let's talk about {topic}. Could you walk me through your experience with it?"
)


def extract_json(text: str) -> dict:
    original = text
    # Strip markdown if present just in case
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM JSON: {original}")
        # Fallback heuristic
        return {
            "action": "next_question",
            "spoken_response": text,
            "score_of_last_answer": None,
            "topic_covered": None,
            "current_phase": "core",
        }


async def extract_skill_plan(job_role: str, job_description: str) -> Dict[str, List[str]]:
    """
    Extract a structured skill plan from the JD via a fast LLM call.
    Called once at the very start of the interview.
    Returns: {"foundation_skills": [...], "core_skills": [...], "secondary_skills": [...]}
    """
    jd_text = job_description if job_description and job_description.strip() else "No explicit job description provided."

    prompt = SKILL_EXTRACTION_PROMPT.format(
        job_role=job_role,
        job_description=jd_text,
    )

    try:
        response_text = await llm_client.invoke_async(
            [SystemMessage(content=prompt)]
        )
        plan = extract_json(response_text)

        # Validate structure
        default_plan = {
            "foundation_skills": [],
            "core_skills": [job_role],
            "secondary_skills": [],
        }
        for key in default_plan:
            if key not in plan or not isinstance(plan[key], list):
                plan[key] = default_plan[key]

        logger.info(f"📋 Extracted skill plan: {json.dumps(plan)}")
        return plan

    except Exception as e:
        logger.error(f"Skill extraction failed: {e}. Using fallback plan.")
        return {
            "foundation_skills": ["General programming fundamentals"],
            "core_skills": [job_role],
            "secondary_skills": [],
        }


def determine_phase(topics_covered: List[str], skill_plan: Dict[str, List[str]]) -> str:
    """Determine current interview phase based on what's been covered."""
    if not topics_covered:
        return "introduction"

    foundation = set(skill_plan.get("foundation_skills", []))
    core = set(skill_plan.get("core_skills", []))

    covered_set = set(topics_covered)

    # Check how many skills from each category have been touched
    foundation_covered = len(covered_set & foundation) if foundation else 0
    core_covered = len(covered_set & core) if core else 0

    # Introduction is only the very first exchange
    if len(topics_covered) <= 1 and "Introduction" in covered_set:
        return "introduction"

    # If we haven't covered enough foundation skills yet
    if foundation and foundation_covered < min(2, len(foundation)):
        return "foundation"

    # If we haven't covered enough core skills yet
    if core and core_covered < min(3, len(core)):
        return "core"

    # If we've covered foundation and core, move to secondary
    return "secondary"


def calculate_elapsed_minutes(interview_started_at: Optional[str]) -> float:
    """Calculate how many minutes have elapsed since interview start."""
    if not interview_started_at:
        return 0.0
    try:
        start = datetime.fromisoformat(interview_started_at.replace("Z", "+00:00"))
        # Normalize to naive UTC — start may be naive (our own naive
        # utcnow().isoformat() writes) or aware (a "Z"-suffixed string),
        # and comparing naive vs. aware datetimes raises TypeError.
        if start.tzinfo is not None:
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        now = datetime.utcnow()
        return (now - start).total_seconds() / 60.0
    except Exception:
        return 0.0


def _is_end_interview_premature(
    elapsed_minutes: float, phase: str, min_duration_minutes: int
) -> bool:
    """
    Hard code-level gate -- backstop for the prompt's ENDING RULES, which the
    LLM is not guaranteed to obey. Confirmed via a real session log: the
    model chose "end_interview" at 9.9 elapsed minutes (min=30) with 6
    skill topics still uncovered.

    `phase` MUST be the code-computed determine_phase() result, never the
    LLM's self-reported phase -- trusting the LLM's own judgment here is
    exactly what this gate exists to not do.

    Does not apply to the candidate's explicit "please stop" path
    (interviewer_node, checked earlier) -- that path returns before this
    function is ever reached.
    """
    if elapsed_minutes < min_duration_minutes:
        return True
    if phase != "secondary":
        return True
    return False


async def _override_premature_end(
    conversation_messages: List[Any],
    state: InterviewState,
    original_spoken_response: str,
    topics_remaining: List[str],
    elapsed_minutes: float,
    min_duration_minutes: int,
) -> Dict[str, Any]:
    """
    Called when the LLM chose action="end_interview" before
    _is_end_interview_premature allows it. Makes ONE corrective LLM call
    instructing the model to continue instead, using its own rejected
    closing response as context so the continuation reads naturally.

    FAILURE MODES CONSIDERED:
    - Corrective call raises (timeout/network/API error) -> caught, falls
      back to a deterministic transition line. No further retry.
    - Corrective call returns malformed/unparseable JSON -> extract_json's
      regex fallback may return unusable text; guarded by the sanity check
      below before trusting it.
    - Corrective call itself returns action="end_interview" again -> not
      honored; falls back to the deterministic transition line instead.
    """
    correction_prompt = END_OVERRIDE_CORRECTION_PROMPT.format(
        company=state.get("company", "our company"),
        candidate_name=state.get("candidate_name", "the candidate"),
        job_role=state.get("job_role", "this role"),
        elapsed_minutes=f"{elapsed_minutes:.1f}",
        min_duration=min_duration_minutes,
        topics_remaining=(
            ", ".join(topics_remaining) if topics_remaining else "a few more areas"
        ),
        original_spoken_response=original_spoken_response,
    )
    corrective_messages = [SystemMessage(content=correction_prompt)] + conversation_messages

    try:
        corrective_text = await llm_client.invoke_async(corrective_messages)
        corrected = extract_json(corrective_text)
        corrected_action = corrected.get("action", "next_question")
        corrected_response = corrected.get("spoken_response")

        usable = (
            corrected_action != "end_interview"
            and corrected_response
            and 0 < len(corrected_response) <= 1000
        )
        if usable:
            logger.info("✅ Corrective re-prompt succeeded; interview will continue.")
            return {"spoken_response": corrected_response}

        logger.error(
            f"⛔ Corrective re-prompt unusable (action={corrected_action}, "
            f"response_len={len(corrected_response) if corrected_response else 0}). "
            "Using deterministic fallback."
        )
    except Exception as e:
        logger.error(
            f"⛔ Corrective re-prompt LLM call failed: {e}. Using deterministic fallback."
        )

    fallback_topic = (
        topics_remaining[0] if topics_remaining else "a few more areas relevant to the role"
    )
    return {"spoken_response": FALLBACK_TRANSITION_TEMPLATE.format(topic=fallback_topic)}


async def interviewer_node(state: InterviewState) -> Dict[str, Any]:
    """
    LangGraph node for conducting JD-aware interview conversation.
    Manages skill extraction, progressive questioning, and coverage tracking.
    """
    logger.info("Dynamic AI Interviewer Agent initialized for session")

    if state.get("status") != "ACTIVE":
        return state

    messages = list(state.get("messages", []))

    # Check if candidate explicitly asked to stop in the last message
    if messages and isinstance(messages[-1], HumanMessage):
        last_human_text = messages[-1].content.lower()
        if any(
            w in last_human_text
            for w in ["stop the interview", "i'm done", "end interview", "that's all"]
        ):
            messages.append(
                AIMessage(
                    content="Thank you for your time today. That concludes our interview!"
                )
            )
            return {"status": "COMPLETED", "messages": messages}

    # --- Step 1: Extract skill plan (runs only on first call) ---
    skill_plan = state.get("skill_plan")
    skill_plan_is_new = False

    if not skill_plan:
        job_role = state.get("job_role", "Software Engineer")
        job_description = state.get("job_description", "")
        skill_plan = await extract_skill_plan(job_role, job_description)
        skill_plan_is_new = True
        logger.info(f"🎯 Skill plan extracted for {job_role}")

    # --- Step 2: Calculate coverage context ---
    topics_covered = list(state.get("topics_covered", []))
    all_skills = (
        skill_plan.get("foundation_skills", [])
        + skill_plan.get("core_skills", [])
        + skill_plan.get("secondary_skills", [])
    )
    topics_remaining = [s for s in all_skills if s.lower() not in [t.lower() for t in topics_covered]]

    # --- Step 3: Calculate elapsed time ---
    elapsed_minutes = calculate_elapsed_minutes(state.get("interview_started_at"))

    # --- Step 4: Determine current phase ---
    current_phase = determine_phase(topics_covered, skill_plan)

    # --- Step 5: Build the prompt ---
    jd_text = state.get("job_description")
    if not jd_text or not jd_text.strip():
        jd_text = "No explicit job description provided."

    sys_prompt = INTERVIEWER_PROMPT.format(
        company=state.get("company", "our company"),
        candidate_name=state.get("candidate_name", "the candidate"),
        job_role=state.get("job_role", "this role"),
        interviewer_designation=state.get("interviewer_designation", "Senior Engineer"),
        foundation_skills=", ".join(skill_plan.get("foundation_skills", [])) or "N/A",
        core_skills=", ".join(skill_plan.get("core_skills", [])) or "N/A",
        secondary_skills=", ".join(skill_plan.get("secondary_skills", [])) or "N/A",
        topics_covered=", ".join(topics_covered) if topics_covered else "None yet",
        topics_remaining=", ".join(topics_remaining) if topics_remaining else "All topics covered",
        current_phase=current_phase,
        interview_start_time=state.get("interview_started_at", "just now"),
        elapsed_minutes=f"{elapsed_minutes:.1f}",
        min_duration_minutes=settings.min_interview_duration_minutes,
    )

    # Inject system prompt at the beginning of the message history
    llm_messages = [SystemMessage(content=sys_prompt)] + messages

    try:
        # Invoke LLM
        response_text = await llm_client.invoke_async(llm_messages)

        # Process JSON Response
        decision = extract_json(response_text)
        action = decision.get("action", "next_question")
        spoken_response = decision.get(
            "spoken_response", "Could you elaborate on that?"
        )

        # Log real-time evaluation logic
        score = decision.get("score_of_last_answer")
        notes = decision.get("evaluation_notes")
        if score is not None:
            logger.info(f"Answer Scored: {score}/10. Notes: {notes}")

        # Track topic coverage
        topic = decision.get("topic_covered")
        new_topics = []
        if topic and topic not in topics_covered:
            new_topics.append(topic)
            topics_covered.append(topic)

        # Recompute deterministically, post-turn, for the end-interview gate --
        # do not reuse the LLM's self-reported phase here, since that is
        # exactly what caused the premature end_interview decision.
        topics_remaining_now = [
            s for s in all_skills if s.lower() not in [t.lower() for t in topics_covered]
        ]
        phase_now = determine_phase(topics_covered, skill_plan)

        # Track phase from LLM response
        reported_phase = decision.get("current_phase", current_phase)

        logger.info(
            f"📊 Phase: {reported_phase} | Topics covered: {len(topics_covered)} | "
            f"Remaining: {len(topics_remaining)} | Elapsed: {elapsed_minutes:.1f}min | Action: {action}"
        )

        # Build result
        result: Dict[str, Any] = {
            "messages": [AIMessage(content=spoken_response)],
            "topics_covered": topics_covered,
            "current_phase": reported_phase,
        }

        # Include skill_plan if it was just extracted
        if skill_plan_is_new:
            result["skill_plan"] = skill_plan

        if action == "end_interview":
            if _is_end_interview_premature(
                elapsed_minutes, phase_now, settings.min_interview_duration_minutes
            ):
                logger.warning(
                    f"⛔ Blocked premature end_interview -- elapsed={elapsed_minutes:.1f}min "
                    f"(min={settings.min_interview_duration_minutes}), phase={phase_now}, "
                    f"topics_remaining={len(topics_remaining_now)}"
                )
                override = await _override_premature_end(
                    conversation_messages=messages,
                    state=state,
                    original_spoken_response=spoken_response,
                    topics_remaining=topics_remaining_now,
                    elapsed_minutes=elapsed_minutes,
                    min_duration_minutes=settings.min_interview_duration_minutes,
                )
                result["messages"] = [AIMessage(content=override["spoken_response"])]
                result["current_phase"] = phase_now
                # status intentionally left unset -> stays ACTIVE, interview continues
            else:
                logger.info("LLM decided to end the interview.")
                result["status"] = "COMPLETED"

        return result

    except Exception as e:
        import traceback

        logger.error(f"Interviewer agent failed: {e}")
        logger.error(traceback.format_exc())

        result: Dict[str, Any] = {
            "error": str(e),
            "messages": [
                AIMessage(
                    content="I'm sorry, I'm having a technical issue. Could you repeat that?"
                )
            ],
        }
        if skill_plan_is_new:
            result["skill_plan"] = skill_plan
        return result
