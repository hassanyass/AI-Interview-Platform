# Phase 2B.2 — Frontend Product Flow Audit

This document outlines the UX/Product-Flow audit of the Path2Hire frontend against the frozen backend architecture.

## 1. Current Frontend Flow
The current flow is structurally sparse and skips necessary candidate journey steps:
`Dashboard -> NewInterview (Hardcoded 'en' language, immediate entry) -> InterviewWorkspace (No transcript, floating menu controls) -> FinalResult`

### Identified Gaps:
- **No Distinct "Resume":** There is no distinction in the Dashboard between creating a new session and resuming an `IN_PROGRESS` session.
- **Language Setup Missing:** `NewInterview.tsx` silently passes `language: 'en'` without letting the user choose (even though the backend API supports `'en'` and `'ar'`).
- **Transcript Missing:** The agent publishes `topic="transcription"` payloads over the LiveKit data channel, but the frontend's `InterviewRealtimeService` only listens for `state_update` payloads, silently dropping the transcript.
- **Vague Controls:** Secondary controls (Hint, Skip, Change, End) are hidden in a generic "More options" dropdown rather than being treated as explicit interview primitives.

## 2. Capability Audit

| Feature / Flow | Status | Notes |
|---|---|---|
| **Language Selection** | [BACKEND SUPPORTED — UI MISSING] | API accepts `language: str` ('en'/'ar'). `NewInterview.tsx` must expose this. |
| **Microphone Check** | [EXISTS] | Present in `NewInterview.tsx` but visually disconnected from a "Pre-flight" checklist. |
| **Live Transcript** | [BACKEND SUPPORTED — UI MISSING] | Backend agent publishes `topic="transcription"`. Frontend ignores it. |
| **End Interview flow** | [FRONTEND IMPLEMENTATION REQUIRED] | Exists in backend, but frontend needs a confirmation dialog to prevent accidental termination. |
| **Phase Transitions** | [BACKEND SUPPORTED — UI MISSING] | `state.phase` is exposed (e.g., `TECHNICAL`, `CLOSING`) but not translated to calm, candidate-facing terminology in the UI. |
| **Resume Session** | [BACKEND SUPPORTED — UI MISSING] | Dashboard has no way to fetch `IN_PROGRESS` sessions and resume them. |
| **Allowed Controls** | [EXISTS] | The frontend currently checks `state.allowed_controls`. |

## 3. Candidate Journey Roadmap
1. **Dashboard:** Differentiate "Your next interview" (New) from "Continue Assessment" (Resume) and "Past Assessments" (Completed).
2. **Setup/Configuration:** Clean form to select Role, Level, and Language.
3. **Pre-flight Lobby:** Checklist for hardware, network, and candidate readiness.
4. **Live Interview (Voice-first):**
   - **Transcript:** Displayed subtly above the current question.
   - **Current Question:** Dead center focus.
   - **Phase Label:** E.g., "Technical questions" instead of `TECHNICAL`.
   - **Microphone:** Bottom center anchor.
   - **Secondary Controls:** Surrounding the microphone.
   - **End Interview:** Placed defensively (e.g., top-right or bottom-left corner) with a confirmation modal.
5. **Assessment Record (Result):** Read-only view of the final state.

## 4. Live Interview Information Hierarchy
Based on the principle "The interface disappears so the candidate's voice becomes the only interaction":

```
[ Top Bar: Path2Hire | Role | Phase Label | End Interview ]

           ( Interviewer Presence - Minimal Audio Waveform )
           "Explain how you would design a distributed locking 
            mechanism using Redis..." (Agent Transcript)

           [ CURRENT QUESTION ]
           Explain how you would design a distributed locking
           mechanism using Redis.

           ( Candidate Transcript - optional / subtle )

                         ( MIC )
                     Listening / Muted

                 [ Hint ]  [ Skip ]  [ Change ]
```
*Note: The transcript replaces the glowing orb as the primary visual representation of the interviewer's speech.*

## 5. Architectural Proposal (Phase 2B.2 - 2B.5)

### Phase 2B.2: Application Shell & Dashboard
- **`AppShell.tsx`**: Add persistent top navigation.
- **`Dashboard.tsx`**: Add tabs or clear sections for `Active` vs `Completed` sessions. (Requires a backend endpoint to list sessions, or we mock the list for now if the API doesn't exist).

### Phase 2B.3: Configuration & Pre-flight
- **`NewInterview.tsx` (Config):** Explicit language dropdown.
- **`PreflightLobby.tsx`:** New component. Shows summary of configuration, mic check, and "Enter Room" button. 

### Phase 2B.4: Live Interview & Transcript
- **`InterviewRealtimeService.ts`**: Update to intercept `topic="transcription"` or `message.type === 'transcription'` and fire an `onTranscript` callback.
- **`InterviewContext.tsx`**: Add `transcript: { speaker: string, text: string }[]` state.
- **`InterviewWorkspace.tsx`**: Recompose into a single-column voice experience.
- **`ControlBar.tsx`**: Explicit bottom row containing the microphone and secondary actions (no longer hidden in a More menu).
- **`EndInterviewModal.tsx`**: Confirmation interceptor for `END_INTERVIEW`.

### Phase 2B.5: Final Result
- **`FinalResult.tsx`**: Reformat into a formal, printable document layout without SaaS KPI cards.

## 6. Risks
- **Transcript Overlap:** If the transcript is very long, it may visually crowd the current question. We must implement fading or scrolling for the transcript (e.g., showing only the last 2-3 lines).
- **Backend History Limit:** If the backend does not supply previous messages upon reconnect, the transcript will start empty on resume. (This is a known constraint of LiveKit data channels unless state sync is explicitly coded).

## 7. Acceptance Criteria (For Implementation phases)
- Language selection correctly populates the POST `/api/v1/interviews/` payload.
- Transcripts appear in real-time when the agent speaks.
- Secondary controls (Hint/Skip) appear distinctly when `allowed_controls` dictates, without using an obscure dropdown.
- Candidate is warned before terminating the interview.
- `TECHNICAL_INTRO` and `CLOSING` phases map to human-readable text.
