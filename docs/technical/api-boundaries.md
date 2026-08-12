# API Boundaries

## Standard REST APIs (FastAPI)
- `POST /auth/...` (Handled mostly by Supabase frontend SDK, but custom hooks if needed)
- `GET /profile`, `PUT /profile`
- `POST /resumes/upload`
- `POST /sessions` (Create configuration)
- `POST /sessions/{id}/start` (Returns LiveKit JWT token)
- `GET /sessions/{id}/results`

## Realtime Path (LiveKit WebRTC & Data Channels)
The following interactions **bypass REST** and occur over LiveKit:
- **Audio Transmission**: Candidate Mic <-> Agent Speaker.
- **Interruption/Barging**: Handled purely in the audio stream (VAD).
- **Code Sync**: Monaco editor changes sent via LiveKit Data Channel (so the AI agent sees what the user types in real-time without HTTP polling).
- **Agent State Updates**: AI agent sends current phase (e.g., "THINKING", "CODING") via Data Channel to update the React UI instantly.
