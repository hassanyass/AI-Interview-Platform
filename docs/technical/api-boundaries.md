# API Boundaries

## Standard REST APIs (FastAPI)
- `POST /auth/...` (Handled mostly by Supabase frontend SDK)
- `GET /api/v1/profiles/me`, `POST /api/v1/profiles/`, `PATCH /api/v1/profiles/me`
- `GET /api/v1/resumes/`, `POST /api/v1/resumes/`
- `GET /api/v1/interviews/`, `POST /api/v1/interviews/` (Create configuration)
- `GET /api/v1/interviews/{id}`
- `POST /api/v1/interviews/{id}/start` (Returns LiveKit JWT token - Phase 3)
- `GET /api/v1/interviews/{id}/results` (Phase 6)

## Realtime Path (LiveKit WebRTC & Data Channels)
The following interactions **bypass REST** and occur over LiveKit:
- **Audio Transmission**: Candidate Mic <-> Agent Speaker.
- **Interruption/Barging**: Handled purely in the audio stream (VAD).
- **Code Sync**: Monaco editor changes sent via LiveKit Data Channel (so the AI agent sees what the user types in real-time without HTTP polling).
- **Agent State Updates**: AI agent sends current phase (e.g., "THINKING", "CODING") via Data Channel to update the React UI instantly.
