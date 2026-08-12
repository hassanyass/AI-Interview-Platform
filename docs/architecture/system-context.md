# System Context

The AI Interview Platform is designed to simulate a realistic Software Engineering interview for candidates.

## Core Actors
- **Candidate (User)**: Interacts with the web application to upload resumes, configure interviews, code, and speak via WebRTC.
- **AI Agent**: The virtual interviewer powered by LiveKit, STT, LLM, and TTS providers.

## External Systems
- **LiveKit Cloud**: Handles WebRTC signaling and media routing between the Candidate's browser and the AI Agent.
- **Deepgram**: Provides fast Speech-to-Text (STT) and Text-to-Speech (TTS).
- **OpenAI**: Provides the LLM reasoning (e.g., GPT-4o) for conversation and technical evaluation.
- **Supabase**: Provides Authentication, PostgreSQL Database, and Object Storage (for resumes).
