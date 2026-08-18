# PHASE 2B.3 FUNCTIONAL AUDIT

## A. Current Working Functionality
- **Session Configuration:** Language preferences (e.g., Arabic) are correctly saved to the PostgreSQL database via `POST /api/v1/interviews/`.
- **LiveKit Connection:** The agent successfully acquires a lease, connects to LiveKit, and initializes STT and TTS plugins.
- **Agent Payload Generation:** The agent's `VoiceInterviewAdapter` correctly generates the `state_update` and `transcription` payloads and publishes them to the LiveKit data channel using specific topics.

## B. Broken Functionality
1. **Controls:** Entirely missing from the candidate's view because the frontend never processes state updates (thus `allowed_controls` remains empty/undefined).
2. **Transcript:** No UI exists to render the agent's transcription. The frontend ignores transcription messages entirely.
3. **Language:** Arabic is stored and used to select the Arabic TTS model, but the LLM is never instructed to speak Arabic, resulting in English responses being spoken by an Arabic voice model.
4. **Phase Display:** The UI hardcodes "Technical Phase" instead of mapping the backend's internal states.
5. **Data Channel Mismatches:** Complete misalignment between how the frontend and agent format and route LiveKit messages.

## C. Exact Data Flow for Controls
1. User clicks a control (e.g., `SKIP_QUESTION`).
2. Frontend sends `{"type": "control_intent", "intent": "SKIP_QUESTION"}` via LiveKit without any topic.
3. Agent's `_on_data_received` explicitly expects `topic == "ui_command"` and a JSON body containing `{"command": "SKIP_QUESTION"}`.
4. **Result:** The agent completely ignores the frontend's command.

## D. Exact Data Flow for Transcription
1. Agent generates text from STT or LLM.
2. Agent's `VoiceInterviewAdapter` calls `_emit_transcription(speaker, text, is_final)`.
3. Agent publishes `{"id": "...", "speaker": "...", "text": "...", "isFinal": ...}` over the data channel with `topic="transcription"`.
4. **Result:** The frontend's `handleDataReceived` ignores the message because it strictly looks for a `message.type === "state_update"` property and ignores the `_topic` argument entirely.

## E. Exact Data Flow for Language
1. User selects `ar` in `NewInterview.tsx`.
2. Backend persists `language: "ar"`.
3. Agent loads `session_data` and extracts `language`.
4. Agent uses `language` to select the TTS model (e.g., `canopylabs/orpheus-arabic-saudi`).
5. Agent's `InterviewController` and `LLMProvider` **do not receive or use the language**.
6. **Result:** The LLM generates its response in English based on its English system prompts. The TTS attempts to read English text with an Arabic voice model.

## F. Backend/Agent/Frontend Contract Mismatches
- **State Update:** Frontend expects JSON property `type="state_update"`. Agent uses LiveKit topic `state_update` with raw state JSON.
- **Controls:** Frontend sends JSON property `type="control_intent"`. Agent expects LiveKit topic `ui_command` with JSON property `command`.
- **Transcription:** Frontend does not handle the `transcription` topic at all.
- **Language:** Agent fails to inject the language preference into the LLM system prompt.

## G. Minimal Implementation Required

### Frontend
1. **`InterviewRealtimeService.ts`**:
   - Update `handleDataReceived` to check the `_topic` parameter instead of `message.type`.
   - If `_topic === "state_update"`, parse the raw payload and trigger `onStateUpdate`.
   - If `_topic === "transcription"`, trigger a new `onTranscription` callback.
   - Update `sendControlIntent` to publish with `{ topic: "ui_command" }` and a payload of `{ command: intent, ...payload }`.
2. **`InterviewWorkspace.tsx`**:
   - Implement the transcript UI overlay below the interviewer presence, keeping it subtle and ensuring it updates automatically based on `onTranscription`.
   - Explicitly render control buttons as primary UI elements (not hidden in "More") based on `state.allowed_controls`.
   - Map `state.phase` to human-readable strings: `Introduction`, `Technical Interview`, `Background`, `Closing`.
   - Implement confirmation prompt for `END_INTERVIEW`.
3. **`InterviewContext.tsx`**:
   - Add state management for transcripts (e.g., `transcriptMessages` array) and `appendTranscript` action.

### Agent
1. **`agent/app/interview/controller.py`**:
   - In `_generate_next_action`, retrieve `self.context.language`. If it is not English, append a strong instruction to the `system_prompt` (e.g., `\n\nCRITICAL INSTRUCTION: You MUST respond EXCLUSIVELY in Arabic.`).

## H. Whether Any Backend Modification is Genuinely Unavoidable
Yes, **modifying the Agent's Python code is genuinely unavoidable**. 
The backend REST API successfully persists the language, but the Agent codebase (`controller.py`) currently has no logic to instruct the LLM to use the selected language. Without appending a language instruction to the LLM system prompt, the AI will perpetually respond in English. This is a functional gap, not a frontend presentation issue.
