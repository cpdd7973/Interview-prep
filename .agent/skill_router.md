# Skill Router

Maps user intents to the appropriate skill(s). The agent consults this table
during Step 1 of `orchestrator.md` to decide which SKILL.md to read.

## Routing Table

| User Intent / Keywords | Primary Skill | Secondary Skill |
|---|---|---|
| WebSocket, API design, backend error, FastAPI, session management | `backend-api-orchestration` | — |
| Interview room UI, React component, chat interface, streaming render | `frontend-interview-ui` | `ux-designer` |
| Mic not working, audio, STT, TTS, Whisper, Edge-TTS, voice | `voice-speech-integration` | `frontend-interview-ui` |
| Scoring, evaluation, rubric, pass/fail, candidate feedback | `candidate-evaluation-engine` | — |
| Database schema, query, storage, migration, indexing | `database-storage-design` | — |
| Docker, deploy, CI/CD, Kubernetes, monitoring, Oracle Cloud | `devops-deployment` | — |
| Auth, JWT, GDPR, PII, encryption, RBAC, security | `auth-security-layer` | — |
| RAG, embeddings, vector search, document ingestion, knowledge base | `rag-knowledge-base-builder` | — |
| Analytics, dashboard, score trends, funnel, bias detection | `analytics-reporting` | — |
| Conversation memory, context window, session persistence | `conversation-memory-manager` | — |
| System design, architecture review, scaling, trade-offs | `senior-ai-architect` | — |
| UX, user flow, design system, wireframe, visual hierarchy | `ux-designer` | `frontend-interview-ui` |
| Create/edit skill, skill performance, evals | `skill-creator` | — |

## Routing Rules

1. **Always consult the primary skill first.** Read its full SKILL.md before writing code.
2. **If a task spans two domains** (e.g., "fix audio in the interview room"), consult BOTH the primary and secondary skills.
3. **If no skill matches**, note that explicitly in the issue log and proceed with general engineering judgment.
4. **CORE_RULES.md always takes precedence** over any skill-specific guidance.
