# LiveKit Architecture Investigation

## Realtime Infrastructure
- **LiveKit Cloud**: Used as the WebRTC SFU (Selective Forwarding Unit) during development/demo. It handles media routing between the browser and the agent at ultra-low latency.
- **LiveKit Agents SDK (Python)**: The framework running the AI interviewer. 

## Agent Responsibilities & State Management
- The Agent worker runs locally during development and connects to LiveKit Cloud.
- **In-Memory Runtime State**: The Agent holds critical context in memory (e.g., `current_phase=CODING`, `language=en`, `max_duration=45m`).
- **Low Latency Turn-taking**: When the candidate speaks, the audio goes to STT -> LLM -> TTS. The Agent uses its in-memory state to prompt the LLM. It **does NOT query the database** for every spoken turn.
- **Event Checkpoints**: The Agent pushes durable records (like transcripts, evaluation summaries, or phase transition logs) to the Database asynchronously at specific milestones.
- **Barge-in / Interruptions**: Handled inherently by the Agent SDK's Voice Activity Detection (VAD).

## Component Separation
- **Frontend** connects to LiveKit Room via a short-lived JWT token.
- **Agent** connects using Server API Keys (`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`).
