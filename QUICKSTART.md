# Quick Start Guide

## Prerequisites

- Python 3.10+ installed
- Node.js 18+ and npm installed
- Git installed
- API keys ready:
  - Groq API key (free tier: https://console.groq.com)
  - Gemini API key (free tier: https://makersuite.google.com/app/apikey)
  - Daily.co API key (free tier: https://dashboard.daily.co)
  - Google OAuth credentials (for Gmail/Calendar)

## Setup Instructions

### 1. Clone and Setup Environment

```bash
# Clone the repository
git clone <your-repo-url>
cd interview-agent

# Create Python virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install Python dependencies
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy example env file
copy .env.example .env

# Edit .env with your API keys
notepad .env
```

Required variables:
```
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
DAILY_API_KEY=your_daily_key_here
DAILY_DOMAIN=your_domain.daily.co
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token
ADMIN_EMAIL=your_email@example.com
SECRET_KEY=generate_random_key_here
```

### 3. Initialize Database

```bash
# Still in backend directory
python database.py
```

You should see: `✅ Database initialized successfully`

### 4. Start Backend Server

```bash
# In backend directory
python main.py
```

Server starts at: http://localhost:8000

Check health: http://localhost:8000/health

### 5. Setup Frontend

```bash
# Open new terminal
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend starts at: http://localhost:5173

## Testing the System

### Test 1: Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "interview-agent-system",
  "version": "1.0.0"
}
```

### Test 2: Create Test Session (via Python)

```python
from backend.mcp_servers.session_mcp import session_mcp
from backend.mcp_servers.session_mcp import CreateSessionInput
from datetime import datetime, timedelta

# Create test session
input_data = CreateSessionInput(
    candidate_email="test@example.com",
    candidate_name="Test Candidate",
    job_role="software_engineer",
    company="Test Company",
    interviewer_designation="Senior Engineer",
    scheduled_at=datetime.utcnow() + timedelta(minutes=10),
    daily_room_url="https://test.daily.co/test-room"
)

result = session_mcp.create_session(input_data)
print(result)
```

### Test 3: Access Interview Room

1. Get room_id from test session creation
2. Visit: http://localhost:5173/interview/{room_id}
3. Should see countdown timer

## Development Workflow

### Phase 1: Core Infrastructure (DONE ✅)
- Database schema
- APScheduler
- Session MCP server
- Basic FastAPI endpoints
- Interview room frontend with time gate

### Phase 2: Build MCP Servers (NEXT)

Start with Voice MCP Server:

```bash
cd backend/mcp_servers
# Edit voice_mcp.py
```

Follow the template in `session_mcp.py`:
1. Define input schemas (Pydantic models)
2. Create MCP server class
3. Implement tool methods
4. Add error handling
5. Test independently

### Phase 3: Build Agents

After all MCP servers are complete, build agents:

```bash
cd backend/agents
# Edit scheduler_agent.py
```

Use LangGraph for state management:
1. Define state schema
2. Create agent nodes
3. Define transitions
4. Add error handling
5. Test with mock data

### Phase 4: Frontend Pages

Build admin dashboard:

```bash
cd frontend/src/pages
# Edit Dashboard.jsx
```

## Common Issues

### Issue: "Module not found" errors

**Solution**: Ensure virtual environment is activated and dependencies installed:
```bash
pip install -r requirements.txt
```

### Issue: Database locked errors

**Solution**: Close all connections, delete `interview_system.db`, reinitialize:
```bash
python database.py
```

### Issue: Port already in use

**Solution**: Kill process on port 8000 or 5173:
```bash
# Windows:
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# Linux/Mac:
lsof -ti:8000 | xargs kill -9
```

### Issue: CORS errors in browser

**Solution**: Check `ALLOWED_ORIGINS` in `.env` includes frontend URL:
```
ALLOWED_ORIGINS=http://localhost:5173
```

### Issue: Whisper model download fails

**Solution**: Download manually:
```python
import whisper
model = whisper.load_model("tiny")
```

## API Documentation

Once backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
interview-agent/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── database.py          # SQLite schema
│   ├── scheduler.py         # APScheduler
│   ├── config.py            # Configuration
│   ├── mcp_servers/         # MCP tool servers
│   ├── agents/              # LangGraph agents
│   ├── prompts/             # Agent prompts
│   ├── question_bank/       # Question JSONs
│   └── utils/               # Helper modules
├── frontend/
│   ├── src/
│   │   ├── pages/           # React pages
│   │   ├── components/      # React components
│   │   └── services/        # API client
│   └── package.json
├── reports/                 # Generated PDFs
├── .env                     # Environment variables
└── requirements.txt         # Python dependencies
```

## Next Steps

1. **Get API Keys**: Sign up for Groq, Gemini, Daily.co
2. **Configure OAuth**: Set up Google OAuth for Gmail/Calendar
3. **Build Voice MCP**: Implement Whisper + Edge-TTS (Phase 2.1)
4. **Test Interview Flow**: End-to-end test with mock audio
5. **Build Dashboard**: Admin interface for scheduling (Phase 4.1)

## Getting Help

- Check `BUILD_SEQUENCE.md` for detailed build order
- Check `RISKS_AND_MITIGATIONS.md` for troubleshooting
- Review `session_mcp.py` as template for new MCP servers
- Review `InterviewRoom.jsx` for frontend patterns

## Production Deployment

**DO NOT deploy to production yet!** This is a development setup.

For production:
1. Use proper secrets management (not .env files)
2. Set up SSL/TLS certificates
3. Use production WSGI server (gunicorn)
4. Set up database backups
5. Configure monitoring and logging
6. Review security checklist in RISKS_AND_MITIGATIONS.md

---

**Ready to build?** Start with Phase 2.1 (Voice MCP Server) in BUILD_SEQUENCE.md!
