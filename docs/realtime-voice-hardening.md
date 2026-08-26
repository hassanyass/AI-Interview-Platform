# Real-Time Voice Pipeline Hardening
## Diagnosis-First Plan

This is not a Transition Phase — it's a quality/reliability hardening pass
on the existing voice engine, sitting between Phase 9 and the rebrand per
current sequencing. Reference this doc directly in prompts (it isn't
auto-loaded by the transition-phase skill, since it's outside that
numbering).

## Reported symptoms, as described
1. **Intermittent delay** — sometimes solid, sometimes the TTS response
   lags noticeably.
2. **Audio clashing** — the agent's voice and something else (candidate
   speech, or a new agent utterance) overlap/collide.
3. **Premature cutoff / topic jump** — the agent cuts off what it's saying
   mid-thought and starts talking about something new.

## Likely mechanism map — hypothesis, not confirmed
Existing mechanisms already in the codebase (with test coverage) that
plausibly govern these symptoms:

| Symptom | Likely mechanism(s) to investigate first |
|---|---|
| Intermittent delay | STT finalization/endpointing timing; Groq API call latency variance (no fallback provider — flagged as pre-existing MEDIUM debt in the original audit); TTS generation start latency |
| Audio clashing | `test_tts_interruption_invalidates_pending_generation` — is a new TTS generation actually cancelling the prior one's audio output, or just its internal state? A state-level cancellation that doesn't actually stop already-buffered audio from playing would produce exactly this symptom. |
| Premature cutoff / topic jump | `test_vad_segments_are_coalesced_into_one_candidate_turn` and `test_duplicate_final_turn_is_ignored` — if VAD is splitting one continuous candidate utterance into multiple "final" turns, the agent could be reacting to a partial thought as if it were complete, then generating a new response before the candidate actually finished |

**Do not assume this map is correct.** It's a starting hypothesis to make
the exploration step concrete, not a diagnosis.

## Sub-phase RT-A — Exploration & diagnosis (no fixes yet)

1. **Read the actual pipeline code**, not just the tests: VAD configuration
   (Silero settings — sensitivity, min-speech-duration, silence timeout),
   STT streaming/finalization logic, TTS generation/cancellation code path
   (specifically: when a new generation starts, does it call something that
   actually stops in-flight audio playback, or only marks old state as
   stale?), and how LiveKit's audio track publishing interacts with
   cancellation.
2. **Check for instrumentation/logging gaps.** Can we currently tell, from
   logs alone, when: STT finalizes a turn, TTS generation starts, TTS
   generation is cancelled, and audio actually starts/stops playing? If
   not, add lightweight timing logs FIRST — you can't fix what you can't
   see, and guessing at timing fixes without visibility risks masking the
   real cause.
3. **Check Groq-specific latency characteristics.** Is there existing
   logging/metrics on Groq call duration? Given the "no fallback provider"
   debt item, is latency variance possibly Groq-side (network/rate-limit
   backoff) rather than a bug in this codebase at all?
4. **Re-read the four existing tests in full** — do they test the
   mechanism's internal state correctly, or do they only assert on
   Python-level state flags without proving the actual audio stream
   behavior? A passing unit test for "generation marked stale" doesn't
   prove "old audio stopped playing."
5. **Report findings before proposing fixes.** Given three distinct
   symptoms, they may have three distinct root causes — don't force one
   unified fix if the evidence points to separate issues.

## Sub-phase RT-B — Fixes (scope depends entirely on RT-A's findings)
Not planned in detail here on purpose — this phase's fixes should be
targeted at whatever RT-A actually finds, not guessed at in advance.

## Verification standard for this work — different from the rest of the project
Automated tests can prove state-machine correctness (generation IDs
invalidate correctly, VAD segments coalesce as coded) but CANNOT prove the
experiential quality — "does this sound smooth." Required before any RT-B
fix is considered done:
1. Deterministic test coverage for the underlying state logic (same
   standard as always).
2. A real, live, spoken verification — the user (not the agent, since it
   cannot hear) actually talks to the agent through a full interview
   segment and confirms the specific symptom is resolved or improved,
   the same role played for the OTP flow's live confirmation.
Do not consider RT-B "done" on test-suite output alone.
