# Global Agent Engineering Standards (CORE_RULES)

**CRITICAL INSTRUCTION:** These rules apply unconditionally to ALL agents and skills across the system. No skill persona (no matter how senior) is allowed to violate these rules. Read these before writing any code.

---

## 0. Agent Behavior — Mandatory on Every Prompt

Before doing anything else on every prompt, the agent MUST follow this sequence:

1. Read `.agent/orchestrator.md` and follow the full execution sequence.
2. Consult relevant skill(s) in `.agent/skills/` — never skip this even for simple fixes.
3. Check `.agent/issue_log.md` for prior occurrences of this problem before attempting a fix.
4. After every change, trigger doc sync per `.agent/doc_sync.md`.
5. Log every fix to `.agent/issue_log.md` and append a changelog entry to `CHANGELOG.md`.
6. If the same issue has recurred 2+ times, trigger `.agent/self_healer.md` before re-applying any fix.

---

## 1. Non-Blocking IO is Non-Negotiable
- **Rule:** Never execute synchronous network calls, LLM invocations, or database queries inside the main event loop (e.g., FastAPI route handlers or APScheduler jobs without thread pools).
- **Why:** Re-entrancy and deadlocks. A single synchronous LLM call taking 30 seconds will freeze all active WebSockets and dashboard polling.
- **Enforcement:** Always use `async`/`await` for network IO. For async-to-sync boundaries (like LangGraph invoking synchronous nodes), you MUST wrap the execution in `asyncio.to_thread()` or `asyncio.create_task()`.

## 2. Unbounded Context Prohibition (The "Loose String" Rule)
- **Rule:** Never pass raw, un-chunked data (like full interview transcripts or unbounded arrays) directly into an LLM prompt without counting tokens, applying safety truncation limits, or using summarization.
- **Why:** Context window overflows cause silent degradation. The model will lose its JSON structure or start hallucinating.
- **Enforcement:** Always calculate `len(string)`. If processing a transcript, implement logic like "keep the last N turns" or "chunk into 4k token sections".

## 3. Mandatory Failure Mode Handling
- **Rule:** Before writing any critical function (system prompts, tool execution, DB writes), you MUST identify and handle at least 2 common failure modes.
- **Why:** APIs timeout. LLMs return markdown instead of JSON. Transcriptions fail.
- **Enforcement:** Write a `# FAILURE MODES CONSIDERED:` comment block above critical functions. Use tools like `json_repair` for LLM outputs and catch block fallbacks for third-party APIs.

## 4. State Machine Defensiveness
- **Rule:** When modifying database statuses (e.g., `ACTIVE` to `COMPLETED`), assume there is a delay in background processing.
- **Why:** Frontends rely on these statuses. Intermediate states (like "Generating Report") need to be explicitly managed so the frontend doesn't drop the user back into an unclosed state.
- **Enforcement:** Prefer granular states (`REPORT_GENERATING`) or expose precise timestamps (like `finished_at`) alongside statuses to decouple long-running background jobs from immediate UI transitions.

## 5. Security and Data Privacy (PII)
- **Rule:** Never write sensitive candidate data (emails, URLs, raw transcripts) to general application logs (e.g., `logger.info(transcript)`).
- **Why:** Leaking PII into generic text logs is a catastrophic compliance failure.
- **Enforcement:** Log state machine transitions (`logger.info(f"Session {room_id} finished")`), not content.

## 6. Minimal Blast Radius — Do Not Change Working Code
- **Rule:** When fixing bug X, do NOT modify code paths that are already working. Only touch the broken code path. If a handler correctly unblocks a downstream process (e.g., `setIsAISpeaking(false)` → mic starts), do not replace that logic with something else unless the user SPECIFICALLY asks.
- **Why:** ISSUE-006 — Agent changed the `audio_failed` handler to call `speechSynthesis.speak()` which set `isAISpeaking = true`. The `onend` event never fired → mic permanently blocked. The original handler (`setIsAISpeaking(false)`) was working correctly and should not have been touched.
- **Enforcement:** Before editing any handler/function, answer: "Was this code path working before?" If yes, preserve its behavior. Add NEW code alongside, don't REPLACE existing fallbacks. Always verify: "Does my change preserve the original exit condition?"

## 7. Browser APIs in Critical Paths Must Have Timeout Guards
- **Rule:** Never gate a critical state transition (like mic activation) on the completion of an unreliable browser API (`speechSynthesis`, `getUserMedia`, etc.) without a hard timeout fallback.
- **Why:** `window.speechSynthesis.speak()` may fail silently; `onend` may never fire on many browsers. If `isAISpeaking` is set to `true` waiting for `onend`, the mic is blocked forever.
- **Enforcement:** Any time you call an async browser API that controls a state flag, add a `setTimeout` safety net that forces the state to the safe value (e.g., `setTimeout(() => setIsAISpeaking(false), maxDuration + 2000)`).