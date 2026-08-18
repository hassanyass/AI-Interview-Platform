# Phase 2B Implementation Plan: Product-Flow Reconstruction

This plan details the complete reconstruction of the Path2Hire candidate journey from a generic SaaS interface into a serious, modern interview product.

## 1. Architectural Strategy & Component Audit

### 1.1 Existing Components Status
* **`AppShell.tsx`** → **REFACED**: Simplified to only support the Application Environment (Dashboard, Config). Removed from the Live Interview environment.
* **`Dashboard.tsx`** → **REPLACED**: Removed generic SaaS cards and replaced with a task-oriented list of "Next Interview", "Continue", and "Past Assessments".
* **`NewInterview.tsx`** → **REPLACED**: Split into `NewInterviewConfig.tsx` and a new `PreflightLobby.tsx`.
* **`InterviewWorkspace.tsx`** → **REPLACED**: Completely rewritten as a voice-first, single-column environment devoid of dashboard chrome.
* **`FinalResult.tsx`** → **REPLACED**: Rewritten as a formal, printable assessment record rather than an analytics dashboard.
* **`InterviewRealtimeService.ts`** → **REFACTORED**: Updated to consume `topic="transcription"` data channel events and manage transcription buffering.
* **`InterviewContext.tsx`** → **REFACTORED**: Added state management for transcripts and mapped phase labels.

### 1.2 State & Data Flow (LiveKit Integration)
* **Backend:** Remains completely frozen.
* **Transcript Flow:** The `InterviewRealtimeService` intercepts `DataPacket` from the agent. If `message.topic === 'transcription'`, the text is appended/updated in the `InterviewContext` transcript buffer.
* **Controls Flow:** `InterviewWorkspace` dynamically mounts buttons (Hint, Skip, Change) purely based on `state.allowed_controls`.
* **End Interview Flow:** User clicks "End" → Local React State (Modal Open) → User Confirms → Service dispatches `END_INTERVIEW` intent.

---

## 2. Screen Plans

### 2.1 Dashboard
* **Purpose:** Direct the candidate to their next immediate action.
* **Information Hierarchy:** Welcome Header > Primary Action (Next/Continue) > Past Assessments.
* **Layout Structure:** Stacked, document-like. No grid cards.
* **Interaction:** Single clear CTA for the most important task.

### 2.2 Create New Interview (Configuration)
* **Purpose:** Configure the technical interview parameters before entering.
* **Information Hierarchy:** Title > Role > Level > Language (English/Arabic) > Duration > Action.
* **Layout Structure:** Clean forms utilizing `Container.tsx`, generous whitespace, and progressive disclosure.
* **Interaction:** Explicit dropdown for Language instead of hardcoded strings.

### 2.3 Pre-flight Lobby (NEW)
* **Purpose:** Mentally transition the candidate from browsing into the high-focus interview mode while verifying hardware.
* **Information Hierarchy:** Configuration Summary > Hardware Checklist (Mic, Audio, Network) > Enter Room CTA.
* **Layout Structure:** Centered modal-like document.
* **Interaction:** The "Enter" button remains disabled until microphone permissions are verified.

### 2.4 Live Interview Room
* **Purpose:** The core product experience. A quiet, professional environment driven by voice and typography.
* **Information Hierarchy:** Phase Label & Exit Control > Interviewer Speech (Live Transcript) > Current Question Context > Microphone Status > Secondary Controls.
* **Layout Structure:** Single central column. No application sidebars or top-level navigation.
* **Interviewer Presence:** Replaces the "AI Orb" with a highly restrained typographic or minimal geometric pulse tied to `isAgentSpeaking`.
* **Live Transcript:** Displays the most recent agent utterance above the question. Automatically fades older content. 
* **Current Question:** The strongest textual element. Uses highly readable typography (Inter) with generous line-height.
* **Microphone:** Centered at the bottom. Visually distinct with explicit states (Listening, Muted, Ready).
* **Hint / Skip / Change:** Displayed as explicit textual or minimal-icon buttons near the microphone. Only visible if permitted by the backend.

### 2.5 End Interview Confirmation
* **Purpose:** Prevent accidental exits.
* **Information Hierarchy:** Warning Text > Cancel (Primary visual weight) > End Interview (Destructive).
* **Layout Structure:** Centered dialog overlaying the room.

### 2.6 Closing State
* **Purpose:** Calm transition after the interview concludes.
* **Information Hierarchy:** "Interview Complete" > "Please wait..."
* **Layout Structure:** Centered, minimal text replacing the live room while the backend finalizes the assessment.

### 2.7 Final Assessment Record
* **Purpose:** A formal, credible log of the candidate's performance.
* **Information Hierarchy:** Title & Metadata > Summary (Counts) > Question Log (Detailed).
* **Layout Structure:** Printable document layout. No score rings, no generic KPI widgets.

---

## 3. Global Requirements

### 3.1 Phase Labels
Backend raw states (`BOOTSTRAP`, `TECHNICAL_INTRO`, `BACKGROUND`, `TECHNICAL`, `CLOSING`) will be mapped to calm, human-readable strings via a frontend utility (e.g., "Technical Interview", "Wrapping up").

### 3.2 Responsive Behavior
* **Mobile Strategy:** The Live Room preserves the hierarchy: Transcript (top) -> Question (center) -> Microphone (bottom anchor). Secondary controls collapse gracefully to fit the safe area without overcrowding the microphone.
* **Dashboard:** Stacks cleanly without horizontal scrolling.

### 3.3 Accessibility
* **Keyboard Navigation:** All controls (Mic, Hint, Skip) must be fully focusable with logical tab orders.
* **Screen Readers:** Dialogs use `aria-modal`, Live Transcripts use `aria-live="polite"` to avoid interrupting screen readers over the agent's actual voice, and the microphone announces its state changes.
* **Reduced Motion:** Handled by the previously established `@media (prefers-reduced-motion)` tokens.

---

## 4. Phased Implementation Roadmap & Acceptance Criteria

### Phase 2B.2: Application Shell & Dashboard
* **Scope:** Rebuild `Dashboard.tsx`, `AppShell.tsx`, and `NewInterview.tsx` (Config portion).
* **Acceptance Criteria:**
  * Application shell has no generic dashboard features.
  * Dashboard prioritizes "Next/Continue Interview" with a clear CTA.
  * Configuration screen explicitly allows 'en' or 'ar' Language selection.

### Phase 2B.3: Pre-flight Lobby
* **Scope:** Create `PreflightLobby.tsx` and link it between Configuration and the Live Room.
* **Acceptance Criteria:**
  * Candidate sees a clear summary of their config.
  * Microphone and browser support are verified before the "Enter" button is enabled.

### Phase 2B.4: Live Interview Core (Room, Transcript, Controls)
* **Scope:** Rewrite `InterviewWorkspace.tsx`, update `InterviewContext.tsx`, and modify `InterviewRealtimeService.ts`.
* **Acceptance Criteria:**
  * The generic layout and "AI Orb" are completely removed.
  * `InterviewRealtimeService` successfully parses `topic="transcription"` data.
  * The agent's speech is visible in a smooth, fading live transcript.
  * The current question dominates the visual hierarchy.
  * Controls (Hint/Skip/Change) appear ONLY when dictated by `allowed_controls`.
  * Clicking "End Interview" triggers a secondary confirmation dialog.

### Phase 2B.5: Closing & Final Assessment Record
* **Scope:** Implement transition states and rewrite `FinalResult.tsx`.
* **Acceptance Criteria:**
  * Entering `CLOSING` phase shows a calm "Please wait" state in the room.
  * `FinalResult.tsx` renders as a formal document without gamified KPI widgets.

### Phase 2B.6: Polish & QA
* **Scope:** Responsive testing, accessibility audits, and visual QA across all screens.
* **Acceptance Criteria:**
  * Mobile view of the Live Room is fully usable without overlapping elements.
  * Keyboard navigation successfully traverses the entire application.
