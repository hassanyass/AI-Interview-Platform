# Path2Hire – Frontend Backend Handover

## 1. System Boundary
- **Frontend**: The browser-based interface running React/Vite. Owns the presentation layer, LiveKit room connection, user input capture, and UI state routing.
- **Backend (FastAPI)**: Owns persistent data (users, resumes, interview configurations, review data, events/messages). Exposes standard REST APIs over HTTP.
- **Database (PostgreSQL via Supabase)**: The system of record. Supabase also handles JWT-based authentication.
- **Realtime (LiveKit Cloud)**: The WebRTC server that manages audio and data channels.
- **Python Agent**: The LiveKit background worker that drives the interview logic (LLM orchestration, STT, TTS, phase management).

## 2. Authentication
- **Provider**: Supabase Auth
- **Flow**: Frontend uses Supabase JS client.
- **Backend Protection**: All `/api/v1/*` routes are protected by HTTP Bearer authentication. The frontend MUST attach `Authorization: Bearer <access_token>` to every request.

## 3. Base API URL
- **Config**: Configured via `VITE_API_BASE_URL` in the frontend environment (e.g., `http://localhost:8000`).

---

# 4. Profile API (Unchanged)
Standard CRUD routes under `/api/v1/profiles`.

---

# 5. Interview Configuration API (Unchanged)
Standard CRUD routes under `/api/v1/interviews/config`.

---

# 6. Interview Session API (Updated for Phase 3)

### GET /api/v1/interviews/{session_id}/ws-token
- **PURPOSE**: Acquires the LiveKit token needed to connect the frontend to the room. Triggers agent bootstrap.
- **AUTHENTICATION**: Bearer Token required.

### GET /api/v1/interviews/{session_id}/result
- **PURPOSE**: Fetches the deterministic, immutable final interview result.
- **AUTHENTICATION**: Bearer Token required.
- **REQUEST**: None.
- **RESPONSE**:
  ```json
  {
    "session_id": "uuid",
    "status": "COMPLETED",
    "completed_at": "datetime",
    "final_result": {
      "session_id": "uuid",
      "role": "Backend Engineer",
      "level": "mid",
      "total_questions": 4,
      "completed": 2,
      "skipped": 1,
      "changed": 1,
      "question_records": [...],
      "competencies_evaluated": [...]
    }
  }
  ```
- **ERRORS**: `400 Result not available. Interview status is <status>`, `404 Interview session not found.`
- **NOTES**: The `final_result` field will only be populated after the agent explicitly transitions the session to `COMPLETED`.

---

# 7. Realtime Data Channel Protocol (LiveKit)

The frontend uses the LiveKit Data Channel to communicate intents directly to the Agent.

### A. Allowed Actions by Phase
The backend sends the frontend its current `state` (via Data Channel `state_update` messages) containing `allowed_controls`.

Possible `allowed_controls`:
- `REQUEST_HINT`: Request a predefined hint (Phase 3C)
- `CHANGE_QUESTION`: Swap the active question for a new one (Phase 3D)
- `SKIP_QUESTION`: Skip the current question without answering (Phase 3A)
- `END_INTERVIEW`: Explicitly end the interview from the candidate side.

### B. Sending Intents to the Agent
To invoke an allowed candidate control, the frontend must publish a message on the Data Channel using the `ui_command` topic. The payload should be formatted as follows:

```json
{
  "command": "REQUEST_HINT"
}
```

The agent will intercept this and, if allowed by the current phase and constraints (e.g. `max_hints`), execute the requested action. The LLM handles the conversational acknowledgment.

### C. In-Flight Constraints
- **Hints**: The agent enforces a maximum number of hints per question. Requesting beyond this limit results in a conversational rejection, but does NOT decrement counters or alter the current question.
- **Change Question**: Limited to EXACTLY ONE per technical section. 
- **Completed Sessions**: Once a session reaches `COMPLETED`, it becomes immutable. The agent will no longer process voice input or control intents.

## 8. Frontend Responsibilities
1. Do not invent your own scoring or results. Fetch `/api/v1/interviews/{session_id}/result` to display the post-interview screen.
2. Read the `allowed_controls` array sent by the agent over the Data Channel. Hide or disable UI buttons for controls that are not currently permitted.
3. Send `ui_command` messages properly over the Data Channel when the user clicks control buttons (e.g., "Hint").
