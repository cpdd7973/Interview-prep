# Interview Preparation Agent System

An MCP-based, multi-agent AI interview system designed for resource-constrained hardware.

## Hardware Requirements
- CPU: Intel i5-8250U or equivalent
- RAM: 8GB (system uses <2GB active)
- OS: Windows 11 (cross-platform compatible)
- No GPU required

## Architecture
- **Backend**: FastAPI + LangGraph + MCP servers
- **Frontend**: Vite + React
- **Database**: SQLite
- **Vector Search**: ChromaDB
- **Scheduling**: APScheduler (SQLite jobstore)
- **LLM**: Groq API (primary), Gemini API (async fallback)
- **STT**: Native Browser Web Speech API / MediaRecorder (primary), Whisper (cloud/CPU backup)
- **TTS**: Edge-TTS (primary cloud), Browser Web Speech API (fallback)
- **WebRTC**: Daily.co

## Quick Start

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python main.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## Project Structure
See folder tree below for complete organization.

## Build Sequence
1. Database schema + migrations
2. MCP servers (session → voice → question_bank → others)
3. Agents (scheduler → interviewer → evaluator → report)
4. Frontend (dashboard → room → question bank)
5. Integration testing

## License
MIT
