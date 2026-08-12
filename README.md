# AI Interview Platform

A demonstrable Voice AI Software Engineering Interview Platform.

## Architecture Summary
- **Frontend**: React + TypeScript + Vite (Port 5173)
- **Backend**: Python + FastAPI (Port 8000)
- **Agent**: Python + LiveKit Agents SDK
- **Database/Auth**: PostgreSQL + Supabase
- **Realtime**: LiveKit Cloud

## Repository Structure
- `frontend/` - React SPA for candidates.
- `backend/` - FastAPI backend for API and state persistence.
- `agent/` - LiveKit AI worker for real-time voice interview.
- `docs/` - Architectural documentation and Phase 0 decisions.
- `infrastructure/` - Scripts and configuration.

## Prerequisites
- Node.js 20+
- Python 3.11+
- Supabase Project
- LiveKit Cloud Project
- Groq / OpenAI API Keys

## Local Setup
1. Copy `.env.example` to `.env` and fill in credentials.

### How to start PostgreSQL
Use Docker if you want a local DB instead of Supabase remote:
```bash
docker-compose up -d postgres
```

### How to run backend
```bash
cd backend
python -m venv .venv
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### How to run frontend
```bash
cd frontend
npm install
npm run dev
```

### How to run agent foundation
```bash
cd agent
python -m venv .venv
# source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Roadmap
- Phase 0: Architecture (Complete)
- Phase 1: Infrastructure & Scaffolding (In Progress)
