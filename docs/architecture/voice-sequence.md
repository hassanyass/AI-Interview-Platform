# Voice Architecture Sequence

This outlines how a voice session is established and executed.

1. **Session Creation**:
   - Candidate requests to start interview via Frontend.
   - Frontend calls Backend `POST /sessions/{id}/start`.
   - Backend creates a LiveKit Room and generates a Client Token.
   - Backend dispatches a job for the AI Agent to join the room.
   
2. **Connection**:
   - Frontend connects to LiveKit Room using the Client Token.
   - AI Agent connects to the LiveKit Room using a Server Token.
   
3. **Conversation Loop**:
   - Candidate speaks -> Frontend captures mic -> LiveKit Cloud.
   - AI Agent receives audio track -> Deepgram STT transcribes.
   - Agent State Machine updates context -> passes to OpenAI LLM.
   - OpenAI LLM generates response -> Deepgram TTS synthesizes audio.
   - AI Agent publishes audio track -> LiveKit Cloud -> Candidate hears response.

4. **Interruption (Barge-in)**:
   - If Candidate speaks while AI is speaking, STT detects voice.
   - AI Agent interrupts TTS playback immediately, clears speech queue, and listens to Candidate.
