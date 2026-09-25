# Sequences: apply → interview → finalize

Rewritten in H6-B from the code. The previous version described
`POST /sessions/{id}/start` (no such route), the backend "dispatching a job"
to the agent (LiveKit does that, by room), and Deepgram/OpenAI (it is Groq).
Route names below are the real ones.

## 1. Apply and prepare

The public-link flow. The invitation flow differs only at the start: HR
creates the invitation, the candidate redeems it with an OTP at
`POST /api/v1/invitations/{token}/redeem`, and arrives at the same place.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant API as backend
    participant DB as Postgres
    participant S as Supabase Storage
    participant G as Groq

    B->>API: GET /api/v1/apply/{token}
    API->>DB: published + public definition?
    API-->>B: job title, duration, sections

    B->>API: POST /api/v1/apply/{token}/register {name, email}
    Note over API: rate limited per IP (H5-B)
    API->>DB: get_or_create profile + application,<br/>new InterviewSession (CREATED)
    API-->>B: guest JWT + session id

    B->>API: POST /api/v1/interviews/{id}/cv (PDF)
    API->>DB: Resume row first (PROCESSING)
    API->>S: upload the file
    API->>G: extract a structured profile
    API->>DB: apply to the profile, mark COMPLETED
    API-->>B: what we read from your CV

    B->>API: POST /api/v1/interviews/{id}/consent
    API->>DB: store the disclosure text shown
    API-->>B: 201
```

The CV is a gate, not a nicety: `POST /livekit/token` answers `409
CV_REQUIRED` until one is attached.

## 2. The interview

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant API as backend
    participant LK as LiveKit Cloud
    participant W as agent worker
    participant G as Groq

    B->>API: POST /api/v1/livekit/token {session_id}
    API->>API: CV gate, ownership check, rate limit
    API-->>B: room token + wss URL
    API-)API: claim + start recording egress (background)

    B->>LK: connect with the token
    LK->>W: dispatch a job for this room
    W->>API: GET /internal/interviews/{id}/load
    API-->>W: job, definition, sections, questions, criteria, checkpoint
    W->>API: PATCH .../status IN_PROGRESS
    W->>API: POST .../events SESSION_STARTED
    W-)API: POST .../renew-lease (every LEASE_RENEWAL_INTERVAL_SECONDS)

    loop each turn
        B->>LK: candidate audio
        LK->>W: audio track (candidate participant only)
        W->>G: STT
        W->>G: LLM — next action, bounded by the state machine
        W->>G: TTS (fixed system lines served from the local cache)
        W->>LK: agent audio
        LK->>B: candidate hears the interviewer
        W->>API: POST .../messages, .../checkpoints
    end

    B->>LK: ui_command (End interview, Submit code, hint…)
    LK->>W: data channel packet
    W->>W: candidate-* sender, size, shape, allow-list (H5-B)
```

Barge-in: when the candidate speaks over the interviewer, the adapter clears
the audio queue (`AudioSource.clear_queue`) as well as invalidating the
in-flight generation — clearing the queue was the fix in RT-B1, because
frames already buffered by LiveKit kept playing without it.

## 3. Finalize

Three ways an interview ends, and they converge.

```mermaid
sequenceDiagram
    autonumber
    participant W as agent worker
    participant API as backend
    participant DB as Postgres
    participant LK as LiveKit Cloud
    participant R2 as R2

    alt completed normally
        W->>W: controller reaches COMPLETED
        W->>API: POST .../evaluation (the LLM's assessment)
        W->>API: PATCH .../status COMPLETED
        W->>W: ctx.shutdown(reason="completed")
    else the worker fails
        W->>API: POST .../events SESSION_DISCONNECTED
        W->>API: POST .../checkpoints (so a resume is possible)
        W->>API: PATCH .../status DISCONNECTED
        W->>W: ctx.shutdown(reason="agent_failure")
    else the lease is lost to another worker
        W->>W: stop driving, aclose, shutdown(reason="lease_lost")
        Note over W: writes no status — the other worker owns the session
    end

    Note over API,DB: while DISCONNECTED the candidate may reconnect, and build_context restores from the checkpoint

    API->>DB: sweep: DISCONNECTED longer than<br/>DISCONNECT_AUTO_FINALIZE_MINUTES?
    Note over API: one replica per interval (advisory lock)
    API->>DB: finalize_live_session — row locked FOR UPDATE, status TERMINATED
    API->>LK: stop egress, delete the room
    LK->>R2: the recording lands
```

An HR-triggered regeneration (`POST /admin/interviews/{id}/regenerate-evaluation`)
runs the same evaluation later, as a queued task, for a session that ended
with only a placeholder.

## What guarantees these sequences

| Property | Mechanism |
|---|---|
| A session never stays `IN_PROGRESS` after the worker dies | `runtime/teardown.py`, plus the sweep as a backstop |
| Two workers never drive one interview | the lease; losing it stops the worker without writing status |
| One interview, at most one recording | a conditional `UPDATE` claims the start (H5-B) |
| A message sequence never repeats after a resume | `build_context` takes the higher of checkpoint and messages |
| A candidate cannot reach another's session | owner checks on every route, tested in `test_auth_matrix.py` |
