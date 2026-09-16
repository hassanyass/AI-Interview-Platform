# Interview start & verbal setup — UX plan (2026-09-16)

Four findings from the live voice tests of the Background subsection, with
root causes where found, the design for each, files touched, and how each
is verified. Executed step by step, in the order below, one commit each.
No frozen files are involved in any step.

---

## Step 4 first — the camera stays on after the interview ends (root cause found)

**Symptom.** Camera light stays on after the interview is terminated or
ended, even after the earlier `releaseLocalMedia()` fix in
`InterviewWorkspace.tsx`.

**Root cause.** The intro screen's device check (`DevicePreview.tsx`) opens
its own `getUserMedia({video, audio})` stream — a *second* stream,
independent of LiveKit — and its cleanup never stops it:

```ts
const [stream, setStream] = useState<MediaStream | null>(null);
useEffect(() => {
  ...setStream(mediaStream)...
  return () => {
    if (stream) stream.getTracks().forEach(t => t.stop());   // `stream` is the value
  };                                                          // captured at mount: null
}, []);
```
The effect runs once with `stream === null`, so the closure's `stream` is
always `null` and the tracks are never stopped. When the candidate presses
Start the preview unmounts, the `<video>` goes away, but the camera and
microphone tracks keep running for the life of the page — through the
interview, and after it. `releaseLocalMedia()` only stops LiveKit's tracks,
so it could never reach this one. This is why the fix "kept persisting".

**Fix.** Keep the stream in a ref (`streamRef.current = mediaStream`) and
stop from the ref in the cleanup; also stop it in the `!active` race branch
(already done) and expose nothing else. Belt and braces: `IntroScreen`
unmounts `DevicePreview` explicitly before calling `onStart`, so the
preview's tracks are released *before* LiveKit acquires the camera (avoids
two concurrent captures on the same device, which some browsers refuse).

**Verify.** Dev-only: `navigator.mediaDevices.getUserMedia` spy counting
live tracks; manual: camera light off after (a) End before starting, (b)
End Session mid-interview, (c) fullscreen termination, (d) natural
completion.

Files: `features/interview-session/DevicePreview.tsx`, `IntroScreen.tsx`.

---

## Step 1 — standardise the verbal section setup (job authoring)

**Today.** In `SectionsEditor.tsx` an expanded VERBAL card shows three
unrelated blocks stacked: a bare "Time budget (min)" input row, the
Background settings box (checkbox + two number inputs + a summary
sentence), then the question editor. CODING/MCQ show only the time row and
the editor. Labels, spacing and control widths differ between the blocks.

**Design.** One **section setup panel** with the same anatomy for every
section type, in this order, each group a titled row (label + hint on the
left, controls on the right, same input width):

1. **Timing** — *Section time budget* (min). Hint: counts toward the job's
   advertised duration.
2. **Background conversation** (VERBAL only) — switch; when on, *Questions*
   (1–6) and *Up to* (min); hint: carved out of the section budget; the
   ≤ 50 % rule surfaced inline as today.
3. **Questions** — the existing `QuestionEditor`, headed *Discussion
   questions* for VERBAL (*Coding problems* / *Multiple-choice questions*
   otherwise) with a count.

A **summary strip** at the top of the expanded card reads the whole section
in one line, e.g. *"Verbal · 20 min — up to 5 min background (3 questions)
+ at least 15 min discussion (4 questions)"*, and turns amber when the
section is not publishable yet (no budget, no questions).

The collapsed card header gains the same summary in muted text so HR can
read every section without expanding.

Files: `routes/admin/SectionsEditor.tsx` (extract `SectionSetupPanel`,
`TimingRow`, `BackgroundRow`, `SectionSummary`), locales en/ar. Backend
untouched (same `config` keys).

**Verify.** Admin sign-in in the browser pane (yours), screenshots of
VERBAL / CODING / MCQ cards collapsed and expanded, save round-trips
through the existing endpoints, the 422 for background > 50 % still
surfaced inline.

---

## Step 2 — explain fullscreen before it happens

**Today.** Start requests fullscreen immediately; the only mention is
inside the consent paragraph ("fullscreen-exit events"). The 10-second
grace and the termination consequence are never stated up front.

**Design.** A dedicated **"Fullscreen mode"** card on the intro screen,
beside *Recording & monitoring*, with an icon and three short points; the
Start button reads **"Start in fullscreen"**. Proposed copy (en; ar
mirrored):

> **The interview runs in fullscreen.**
> When you press Start, this page switches to fullscreen and stays there
> until the interview ends. This keeps you focused and gives the hiring
> team confidence that the session was completed without distractions.
>
> - If you leave fullscreen (Esc, switching windows or tabs), a **10‑second
>   countdown** appears — return to fullscreen to continue.
> - If you don't return in time, the interview **ends and is recorded as
>   terminated**; it can't be resumed.
> - Fullscreen is required to start. Closing the tab also ends the
>   interview.

Acknowledgement: the existing consent checkbox label becomes *"I
understand the fullscreen rule and consent to this recording and
monitoring."* — one checkbox, both facts (avoids a second gate). The
recorded consent text (persisted server-side via `recordConsent`) includes
the fullscreen paragraph so what was shown is what is stored.

Files: `features/interview-session/IntroScreen.tsx`,
`pages/InterviewSession.tsx` (consent text passed to `recordConsent`),
locales en/ar.

**Verify.** Intro renders the card (screenshot via the pane; no login
needed on a throwaway apply link), consent row stored with the new text,
Start still requests fullscreen first (gesture rule unchanged).

---

## Step 3 — a real start sequence instead of a generic spinner

**Today.** After Start, `AgentConnectingScreen` shows *"Starting
Interview / Connecting… → Initializing… → Preparing workspace…"* on fixed
timers (0.8 s, 2.2 s) that have nothing to do with what is happening; the
bar sits at 80 % for as long as the agent takes (room connect + `/load` +
background generation ≈ 3–5 s + the legacy TECH-GEN call ≈ 5 s + greeting
≈ 2 s — typically 10–15 s).

**Design.** Stage the loader on **real signals**, with copy that tells the
candidate what is being prepared and that waiting is expected:

| Stage | Signal | Copy | Bar |
|---|---|---|---|
| 1 | room not yet connected (`useConnectionState`) | *Connecting to the interview room…* | 15 % |
| 2 | connected, no agent participant yet (`useRemoteParticipants`) | *Your interviewer is joining…* | 40 % |
| 3 | agent present, no `state_update` yet | *Reading your CV and preparing your questions…* (or *Preparing your questions…* when no CV) | 70 % |
| 4 | first `state_update` received | *Starting…* (screen swaps to the workspace) | 100 % |

Plus a rotating reassurance line under the status every 4 s ("This usually
takes about 15 seconds", "Your microphone stays muted until you unmute
it", "You can re-read any question in the transcript"), an elapsed-time
note after 20 s (*"Taking a little longer than usual — still working"*),
and after 60 s a *Reload* action. Reduced-motion safe.

Files: `features/interview-session/InterviewWorkspace.tsx`
(`AgentConnectingScreen` → `StartSequence` with the room hooks; the agent
is identified by its participant identity prefix), locales en/ar.
Optional (agent, non-frozen, later): skip the legacy TECH-GEN call for
B2B sessions to cut ~5 s — flagged separately, not part of this step.

**Verify.** Dev preview harness for the four stages (same pattern as
`/dev/verbal-preview`), then a live run reading the stage transitions in
the console.

---

## Order and gates

4 → 1 → 2 → 3. Each step: explore the exact files again, implement,
type-check, verify in the browser pane (admin sign-in from you for step 1),
commit. The camera fix goes first because it is a privacy issue with a
known one-line cause.
