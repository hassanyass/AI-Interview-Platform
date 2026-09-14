# System Architecture

The platform uses an intentionally simple, decoupled Monorepo architecture:

## Monorepo Structure
- `frontend/`: React SPA UI.
- `backend/`: FastAPI REST endpoints.
- `agent/`: LiveKit Python worker.
- `docs/`: System documentation.
- `infrastructure/`: Configs/deployment scripts (future).

## Core Components
1. **Frontend (React + TypeScript)**
   - Manages user dashboard, configuration, and the Monaco Editor UI.
   - Connects to Backend for REST APIs.
   - Connects to LiveKit Cloud for WebRTC audio/data channels.

2. **Backend (Python + FastAPI)**
   - Exposes REST APIs for Auth, Profiles, and Sessions.
   - Generates LiveKit access tokens.
   - Manages durable state in PostgreSQL (via Supabase).

3. **Interview Engine / Agent (LiveKit Agents SDK - Python)**
   - Connects to the LiveKit Room as a worker.
   - **In-Memory Runtime State**: Maintains session context (current phase, config, timing, guardrails) in memory. **No database round-trips for every conversational turn** to ensure ultra-low latency.
   - Executes STT -> LLM -> TTS pipeline based on runtime state.
   - Persists data to PostgreSQL (via Backend API or direct DB client) only at major checkpoints (phase changes, code submissions, interview end).

4. **Database (PostgreSQL via Supabase)**
   - Persistent storage for Users, Profiles, Sessions, Questions, and Results.
   
## Architectural Constraints
- **Keep it Simple**: No LangChain, LlamaIndex, Redis, Kafka, or Vector DBs.
- **Flexible Models**: LLM and STT/TTS model names are injected via environment variables.
- **Single Agent Architecture**: A unified agent handles both English and Arabic based on the session's `language` configuration.
