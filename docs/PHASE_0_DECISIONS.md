# Phase 0 Decision Record

## Approved Architecture
- **[APPROVED]** Monorepo architecture (`frontend/`, `backend/`, `agent/`, `docs/`, `infrastructure/`).
- **[APPROVED]** System Context: Frontend -> Backend (REST) | Frontend <-> LiveKit <-> Python Agent (WebRTC).
- **[APPROVED]** Principle: "The LLM is the interviewer intelligence; the application controls the interview."

## Approved Technologies
- **[APPROVED]** Frontend: React, TS, Tailwind, shadcn, Monaco Editor.
- **[APPROVED]** Backend: Python, FastAPI.
- **[APPROVED]** Realtime: LiveKit Cloud (for signaling/routing) & LiveKit Agents Python SDK.
- **[APPROVED]** AI Models: Deepgram (STT), OpenAI (LLM), Deepgram (TTS - with flexible abstraction for future evaluation like ElevenLabs).
- **[APPROVED]** DB/Auth/Storage: PostgreSQL (via Supabase), Supabase Auth, Supabase Storage.
- **[APPROVED]** Resume Parsing: PyMuPDF.

## Important Architectural Amendments
- **State Machine Structure**: Separated into **Interview Phases** (controlled by the application) and **Conversational Actions** (flexible LLM behavior within the phase).
- **Runtime vs Persistent State**: LiveKit Agent maintains an in-memory runtime state for low-latency turns. No database round-trips for every conversational turn. Durable persistence to PostgreSQL happens at event checkpoints.
- **Model Configuration**: Model names (e.g., specific OpenAI or Deepgram models) must be injected via environment variables, not hardcoded.
- **Language Support**: Arabic is not a separate architecture. The interview configuration uses a `language` field (`en` or `ar`). The same agent architecture supports both.
- **Simplicity Rule**: Explicitly excluded LangChain, LlamaIndex, Redis, Kafka, vector DBs, and extra microservices to keep the architecture intentionally simple.
- **Deployment Priority**: Development prioritizes local frontend, local backend, local agent worker, LiveKit Cloud, and Supabase. No deployment pipelines yet.

## Open Decisions / Next Steps
- Phase 1 Prerequisites: Provision actual accounts (Supabase, LiveKit, OpenAI, Deepgram) and generate API keys locally. Initialize the monorepo structure.
