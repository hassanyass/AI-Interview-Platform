"""
VoiceInterviewAdapter — bridges LiveKit audio streams to the InterviewController.

Orchestrates: STT → Controller → TTS
Persists finalized messages and meaningful events.
"""
import asyncio
import logging
import os
import re
from typing import Optional, List, Dict
from livekit.agents import APIConnectOptions, stt, tts, vad
from livekit import rtc

from agent.interview.controller import InterviewController
from agent.interview.models import ActionEnum, InterviewPhase
from agent.interview.persistence import InterviewPersistence
from agent.interview import tts_cache
from agent.llm.prompts import SYSTEM_MESSAGES

# Audit fix (2026-08-27): every fixed, non-personalized string any language's
# SYSTEM_MESSAGES dict can produce -- acks, skip/end-of-section/end-interview
# lines, etc. Used only to decide whether a given turn's response is safe to
# cache/replay (see _synthesize_and_play) -- built once at import time since
# SYSTEM_MESSAGES itself never changes at runtime.
_FIXED_SYSTEM_MESSAGE_TEXTS = frozenset(
    text for lang_messages in SYSTEM_MESSAGES.values() for text in lang_messages.values()
)

logger = logging.getLogger(__name__)


class VoiceInterviewAdapter:
    """
    Manually orchestrates STT -> InterviewController -> TTS.
    Persists finalized transcript messages and events at meaningful checkpoints.
    """

    def __init__(
        self,
        controller: InterviewController,
        stt_plugin: stt.STT,
        tts_plugin: tts.TTS,
        vad_plugin: vad.VAD,
        room: rtc.Room,
        persistence: Optional[InterviewPersistence] = None,
    ):
        self.controller = controller
        self.stt_plugin = stt_plugin
        self.tts_plugin = tts_plugin
        self.vad_plugin = vad_plugin
        self.room = room
        self.persistence = persistence

        self._stt_stream: Optional[stt.SpeechStream] = None
        self._audio_source: Optional[rtc.AudioSource] = None
        self._audio_track: Optional[rtc.LocalAudioTrack] = None

        # Audio playback queue (bounded to prevent endless buffering)
        self._tts_queue = asyncio.Queue(maxsize=20)
        self._playback_task: Optional[asyncio.Task] = None
        self._current_synthesis_task: Optional[asyncio.Task] = None
        self._candidate_endpoint_task: Optional[asyncio.Task] = None
        self._is_interrupted = False
        self._generation_id = 0
        # RT-B2: True only while frames are actively being captured for the
        # CURRENT generation -- set in _synthesize_and_play(), read (and
        # snapshotted) by _handle_interruption().
        self._is_speaking = False
        # RT-B2: snapshot of _is_speaking taken by _handle_interruption()
        # BEFORE it resets things -- synchronous, so it reflects the true
        # state at the moment of interruption, not whatever
        # _synthesize_and_play()'s own (asynchronous) finally-block reset
        # gets around to later. Consulted by _handle_candidate_turn() to
        # decide discard-outright vs. provisional-preserve.
        self._last_interruption_was_mid_playback = False
        self._candidate_turn_id = 0
        self._processed_candidate_turns = set()
        self._pending_candidate_parts: List[str] = []
        self._last_final_candidate_text = ""
        self._last_final_candidate_at = 0.0
        self._transcription_sequence = 0
        self._completion_persisted = False
        # Phase 8C: tracked independently of _completion_persisted above --
        # submitting the normalized Evaluation/Score rows is a second,
        # additive persistence target from save_completion()'s legacy
        # final_result JSONB write, not gated on it and not gating it. Read
        # by main.py's teardown retry to decide whether this specifically
        # still needs retrying.
        self._evaluation_submitted = False
        try:
            self._candidate_endpoint_delay = max(
                0.25, float(os.getenv("STT_ENDPOINT_DELAY_SECONDS", "0.8"))
            )
        except ValueError:
            self._candidate_endpoint_delay = 0.8

        # WR-C (docs/section-pacing-architecture.md): auto-proceed timeout
        # for the waiting room — handles an abandoned/AFK session. Same
        # defensive env-var loading pattern as _candidate_endpoint_delay
        # above.
        try:
            self._waiting_room_timeout_seconds = max(
                1.0, float(os.getenv("WAITING_ROOM_TIMEOUT_SECONDS", "300"))
            )
        except ValueError:
            self._waiting_room_timeout_seconds = 300.0
        self._waiting_room_timeout_task: Optional[asyncio.Task] = None
        # Edge-detection for the waiting-room timer: only (re)schedule on
        # the transition INTO WAITING_ROOM, only cancel on the transition
        # OUT of it — not on every _emit_ui_state() call while the phase
        # stays WAITING_ROOM (which happens often: stray/rejected UI
        # commands and incidental candidate speech both still reach the
        # finally-block emit). A naive "schedule whenever phase ==
        # WAITING_ROOM" would reset the countdown on any such incidental
        # event and could make the timeout effectively never fire.
        self._last_emitted_phase: Optional[InterviewPhase] = None

        # STT turns and UI controls share one interview timeline. Never let
        # two controller turns generate responses concurrently.
        self._turn_lock = asyncio.Lock()

    async def start(self, resume: bool = False):
        """Initializes audio tracks and starts listening for events."""
        self._audio_source = rtc.AudioSource(
            self.tts_plugin.sample_rate,
            self.tts_plugin.num_channels,
        )
        self._audio_track = rtc.LocalAudioTrack.create_audio_track(
            "agent-mic", self._audio_source
        )

        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self.room.local_participant.publish_track(self._audio_track, options)

        self.room.on("track_subscribed", self._on_track_subscribed)
        self.room.on("data_received", self._on_data_received)

        # RT-B0: wire up the SDK's existing metrics_collected event (both
        # stt.STT and tts.TTS already emit this on every call, with
        # ttfb/duration/audio_duration -- previously zero listeners anywhere
        # in this codebase) rather than hand-building STT/TTS timing.
        self.stt_plugin.on("metrics_collected", self._on_stt_metrics)
        self.tts_plugin.on("metrics_collected", self._on_tts_metrics)

        # Process any tracks that were already subscribed before we attached the listener
        for participant in self.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                    self._on_track_subscribed(publication.track, publication, participant)

        # Start playback consumer
        self._playback_task = asyncio.create_task(self._playback_loop())

        if resume:
            # Reconnect scenario — greet and continue
            logger.info("Resuming interview from checkpoint...")
            phase = self.controller.context.current_phase
            resume_msg = f"Welcome back! We're continuing from the {phase.value.lower().replace('_', ' ')} phase. Please go ahead."
            await self._speak_and_persist(resume_msg, is_agent=True)
            await self._emit_ui_state()
        else:
            # Fresh start
            self.controller.start_interview()
            logger.info("Voice adapter started. Kicking off interview...")
            await self._emit_ui_state()
            await self._kickoff_interview()
    async def _kickoff_interview(self):
        """Explicitly kicks off the interview by generating the first AI turn."""
        self._is_interrupted = False
        logger.info("[Agent Thinking... Initializing Interview]")
        
        # Pass None to generate the next action without an initial user message
        action = await self.controller.process_candidate_input(None)

        if not action or not action.response:
            return

        logger.info(f"AI ({action.action.value}): {action.response}")

        meta = {"action": action.action.value, "reason": action.reason, "is_greeting": True}
        
        await self._persist_message(
            speaker="agent",
            text=action.response,
            metadata=meta,
        )
        await self._emit_transcription(speaker="agent", text=action.response)
        await self._speak_text(action.response)
        await self._emit_ui_state()


    async def _broadcast_tts_status(self, status: str, attempt: int = None, max_retries: int = None, text: str = None):
        """Audit fix (2026-08-27): dedicated, minimal data-channel signal so
        the frontend can show real feedback while a TTS 429 retry is in
        flight, instead of silence that looks indistinguishable from the
        agent simply never responding. Deliberately its own topic/payload,
        not folded into generate_ui_state() — this reflects the AUDIO
        pipeline's own transient state, not interview state, and firing on
        every retry attempt would be noisy inside the interview-state
        broadcast's existing call sites/logging.
        status: "retrying" | "ok" | "gave_up".
        text/language (2026-08-27, follow-up): carried on "gave_up" so the
        frontend can speak the turn itself via the browser's own Web Speech
        API — the one case where server-side TTS has definitively failed for
        this turn (not just mid-retry) and the interview would otherwise go
        silent for that line regardless of provider/quota state."""
        import json
        payload = json.dumps({
            "status": status,
            "attempt": attempt,
            "max": max_retries,
            "text": text,
            "language": getattr(self.controller.context, "language", "en") if text else None,
        }).encode("utf-8")
        try:
            await self.room.local_participant.publish_data(
                payload,
                reliable=True,
                topic="tts_status",
            )
        except Exception:
            logger.exception("[TTS-DIAG] Failed to broadcast tts_status=%s", status)

    async def _emit_ui_state(self):
        """Broadcasts the current InterviewController state to the UI via LiveKit Data Channel."""
        import json
        state = self.controller.generate_ui_state()
        payload = json.dumps(state).encode("utf-8")
        logger.info(f"Emitting UI State: {state['phase']} / {state['sub_phase']}")
        await self.room.local_participant.publish_data(
            payload,
            reliable=True,
            topic="state_update"
        )

        # WR-C: reconcile the waiting-room auto-timeout with whatever phase
        # was just emitted. _emit_ui_state() is the one checkpoint called
        # after every UI command and every candidate turn (see its call
        # sites), so it's a more robust single place to do this than
        # hunting down each individual phase-transition call site — but
        # only acts on the EDGE (see __init__'s _last_emitted_phase
        # docstring for why a naive "schedule whenever phase ==
        # WAITING_ROOM" would be wrong). This also covers resume: a fresh
        # adapter's _last_emitted_phase starts as None, so restoring
        # straight into a persisted WAITING_ROOM phase schedules a fresh
        # timeout on the very first emit, with no separate resume-specific
        # code needed (item 5's approved answer, "fresh timeout window").
        current_phase = self.controller.context.current_phase
        if current_phase == InterviewPhase.WAITING_ROOM and self._last_emitted_phase != InterviewPhase.WAITING_ROOM:
            self._schedule_waiting_room_timeout()
        elif current_phase != InterviewPhase.WAITING_ROOM and self._last_emitted_phase == InterviewPhase.WAITING_ROOM:
            self._cancel_waiting_room_timeout()
        self._last_emitted_phase = current_phase

    async def _emit_transcription(self, speaker: str, text: str, is_final: bool = True):
        """Broadcasts a transcription update to the frontend via Data Channel."""
        import json
        self._transcription_sequence += 1
        payload = json.dumps({
            "id": f"{speaker}-{self._transcription_sequence}",
            "speaker": speaker,
            "text": text,
            "isFinal": is_final
        }).encode("utf-8")
        await self.room.local_participant.publish_data(
            payload,
            reliable=True,
            topic="transcription"
        )

    # ─── RT-B0: SDK Metrics ──────────────────────────────────────────────

    def _on_stt_metrics(self, metrics) -> None:
        """Handler for stt.STT's "metrics_collected" event (SDK-provided,
        emitted on every recognize call -- previously unlistened)."""
        logger.info(
            "[STT-METRICS] request_id=%s duration_ms=%.1f audio_duration_s=%.2f",
            metrics.request_id, metrics.duration * 1000, metrics.audio_duration,
        )

    def _on_tts_metrics(self, metrics) -> None:
        """Handler for tts.TTS's "metrics_collected" event (SDK-provided,
        emitted on every synthesize call -- previously unlistened)."""
        logger.info(
            "[TTS-METRICS] request_id=%s ttfb_ms=%.1f duration_ms=%.1f audio_duration_s=%.2f cancelled=%s",
            metrics.request_id, metrics.ttfb * 1000, metrics.duration * 1000,
            metrics.audio_duration, metrics.cancelled,
        )

    def _on_data_received(self, packet: rtc.DataPacket):
        """Handles incoming UI commands via LiveKit Data Channel."""
        import json
        data = packet.data
        topic = packet.topic
        
        if topic == "ui_command":
            try:
                payload = json.loads(data.decode("utf-8"))
                command = payload.get("command")
                if command:
                    logger.info(f"Received UI command: {command}")
                    asyncio.create_task(self._handle_ui_command(command, payload))
            except Exception as e:
                logger.error(f"Error parsing UI command: {e}")
                
    async def _handle_ui_command(self, command: str, payload: dict = None):
        """Processes a UI command through the controller and executes the resulting action."""
        async with self._turn_lock:
            await self._handle_ui_command_locked(command, payload)

    async def _handle_ui_command_locked(self, command: str, payload: dict = None):
        """Runs one serialized UI command and its optional follow-up turn."""
        
        # If the candidate skips or moves sections, immediately stop the current TTS
        # WR-C: PROCEED_TO_NEXT_SECTION added — guards against the wrap-up
        # message from the just-finished section still being mid-playback
        # when the candidate immediately clicks Proceed.
        # Audit fix (2026-08-27): END_SECTION_EARLY/END_INTERVIEW were
        # missing here — the only other control that ends the interview
        # entirely or ends a section outright, yet the one place that
        # didn't cut off in-flight agent audio first. Reported symptom:
        # clicking End Section (or End Interview) while the agent was still
        # mid-sentence let that queued speech keep playing out over the
        # transition. Same fix as every other entry in this tuple already
        # gets — no new mechanism, just closing this gap.
        if command in ("SKIP_QUESTION", "SKIP_SECTION", "MOVE_TO_TECHNICAL", "CHANGE_QUESTION", "PROCEED_TO_NEXT_SECTION", "END_SECTION_EARLY", "END_INTERVIEW"):
            self._handle_interruption()
            # Wait a tiny bit to ensure the audio frame buffer clears
            await asyncio.sleep(0.05)
            
        self._is_interrupted = False
        try:
            action = await self.controller.process_ui_command(command, payload)

            if not action:
                return
            if self.controller.context.current_phase == InterviewPhase.COMPLETED and not action.response:
                await self._handle_completion()
                return
            if not action.response:
                # Audit fix (2026-08-27): PROCEED_TO_NEXT_SECTION's own
                # StructuredAction always sets should_transition=False (see
                # controller.py: "the handler already performed the
                # transition itself... same 'don't transition twice'
                # pattern as SKIP_QUESTION/MOVE_TO_TECHNICAL" — a bookkeeping
                # flag about NOT re-applying _transition_to(), unrelated to
                # whether a real section boundary was actually crossed). But
                # crossing into a new section (e.g. CODING -> MCQ) via
                # PROCEED_TO_NEXT_SECTION genuinely does load a brand new
                # question with entirely different content, and the chain
                # call below immediately asks the LLM to present it — with
                # should_transition alone gating the clear, conversation_
                # history still carried the ENTIRE previous section's
                # back-and-forth into that turn's context. Reported symptom:
                # opening a new section, the agent started speaking about
                # content that didn't match the question actually on screen.
                if getattr(action, "should_transition", False) or command == "PROCEED_TO_NEXT_SECTION":
                    self.controller.context.conversation_history.clear()

                # Audit fix (2026-08-27): SUBMIT_MCQ_ANSWER's own response is
                # now always empty (MCQ is 0-live-interaction by design — see
                # controller.py's SUBMIT_MCQ_ANSWER handler), which means it
                # always reaches this branch. Chaining unconditionally here
                # (as SUBMIT_CODE legitimately still does — CODING stays
                # conversational throughout) meant every MCQ submission
                # generated ANOTHER LLM turn even for the routine "move to
                # the next question in the same section" case — re-running
                # CORE_MCQ_QUESTION_PROMPT's "announce this is MCQ" instruction
                # on every question instead of only the section's first, and
                # producing agent speech mid-section that MCQ's design never
                # wanted in the first place. A chain is only genuinely needed
                # here when this submission actually ended the interview
                # (current_phase is now CLOSING, which needs the real
                # goodbye turn) — moving to the next question within the
                # section, or into the silent WAITING_ROOM phase (which
                # carries no LLM generation of its own per WR-B), needs none.
                mcq_no_chain_needed = (
                    command == "SUBMIT_MCQ_ANSWER"
                    and self.controller.context.current_phase != InterviewPhase.CLOSING
                )

                if mcq_no_chain_needed:
                    await self._emit_ui_state()
                elif command in ("SKIP_QUESTION", "SKIP_SECTION", "MOVE_TO_TECHNICAL", "CHANGE_QUESTION", "SUBMIT_CODE", "SUBMIT_MCQ_ANSWER", "END_INTERVIEW", "PROCEED_TO_NEXT_SECTION", "END_SECTION_EARLY"):
                    # WR-C: chains straight into the next section's opening
                    # ASK turn — no separate "welcome back" message is
                    # needed, the new section's own first turn carries it
                    # (same reasoning as WR-B's plan: this phase carries no
                    # LLM generation of its own).
                    # Audit fix (2026-08-27): SUBMIT_MCQ_ANSWER was missing
                    # here, same class of gap as SUBMIT_CODE already covers
                    # — without it, an MCQ submission that completes the
                    # last section transitions to CLOSING but never chains
                    # into the CLOSING-phase LLM turn, leaving the session
                    # permanently stuck (never reaches COMPLETED, no
                    # final_result ever generated).
                    # PR-C manual-test finding (2026-09-01): END_SECTION_EARLY
                    # had the exact same gap — ending your last/only section
                    # early transitions straight to CLOSING (controller.py's
                    # _handle_end_section_early), but with an empty response
                    # it fell through to the else-branch below and never got
                    # the CLOSING-phase goodbye turn (or _handle_completion())
                    # at all. Same fix, same reasoning, extended to cover it.
                    await self._handle_candidate_turn("", is_chain=True, _lock_held=True)
                else:
                    await self._emit_ui_state()
                return
                
            logger.info(f"AI ({action.action.value}): {action.response}")
            
            await self._persist_message(
                speaker="agent",
                text=action.response,
                metadata={"action": action.action.value, "reason": action.reason},
            )
            await self._emit_transcription(speaker="agent", text=action.response)
            await self._persist_action_event(action)
            
            if self.controller.context.current_phase == InterviewPhase.COMPLETED:
                await self._speak_text(action.response)
                await self._handle_completion()
                return
                
            await self._speak_text(action.response)
            
            # If we transitioned to a new phase, clear stale context
            if getattr(action, "should_transition", False):
                self.controller.context.conversation_history.clear()
                
            # Audit fix (2026-08-27): SKIP_QUESTION/SKIP_SECTION/
            # MOVE_TO_TECHNICAL can be REJECTED as a no-op (Issue 6's guard
            # — core content is HR-approved and can't be skipped live; see
            # _handle_candidate_control's SKIP_QUESTION/SKIP_SECTION and
            # MOVE_TO_TECHNICAL branches in controller.py) as well as
            # actually succeed (legacy flow). The chain below used to fire
            # unconditionally on command name alone, with no way to tell
            # those apart — so a rejected skip during BRIEFING (nothing
            # actually changed: current_phase is still BRIEFING) still
            # chained into ANOTHER LLM turn, which re-ran BRIEFING_PROMPT
            # and produced the exact same greeting a second time right
            # after the "let's stick with it" rejection. Reported symptom:
            # the greeting repeating verbatim in the transcript after
            # pressing Skip. Each command's own reject-vs-succeed shape is
            # verified against controller.py's actual return values, not
            # guessed: SKIP_QUESTION/SKIP_SECTION's rejection is the only
            # path that returns action=ACKNOWLEDGE (success there always
            # returns action=TRANSITION); MOVE_TO_TECHNICAL's rejection is
            # the only path that returns should_transition=False (success
            # there always returns should_transition=True). CHANGE_QUESTION
            # deliberately left out of this check — its own success path
            # also returns ACKNOWLEDGE + should_transition=False, identical
            # in shape to its rejection, so there's no safe way to tell
            # them apart here without risking breaking the working
            # successful-change chain.
            was_rejected_no_op = (
                command in ("SKIP_QUESTION", "SKIP_SECTION") and action.action == ActionEnum.ACKNOWLEDGE
            ) or (
                command == "MOVE_TO_TECHNICAL" and not getattr(action, "should_transition", False)
            )

            # Chain to the next turn to generate the new question
            # Audit fix (2026-08-27): SUBMIT_MCQ_ANSWER added alongside
            # SUBMIT_CODE — same reasoning as the tuple above.
            if was_rejected_no_op:
                await self._emit_ui_state()
            elif command in ("SKIP_QUESTION", "SKIP_SECTION", "MOVE_TO_TECHNICAL", "CHANGE_QUESTION", "SUBMIT_CODE", "SUBMIT_MCQ_ANSWER", "END_INTERVIEW"):
                await self._handle_candidate_turn("", is_chain=True, _lock_held=True)
            else:
                await self._emit_ui_state()
        except Exception as e:
            logger.error(f"Error processing UI command {command}: {e}", exc_info=True)
        finally:
            await self._emit_ui_state()

    def _on_track_subscribed(
        self, track: rtc.Track, publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"Subscribed to candidate audio track from {participant.identity}")

            # Use StreamAdapter with VAD to chunk audio into REST requests
            from livekit.agents import stt as stt_module
            self._stt_stream = stt_module.StreamAdapter(
                stt=self.stt_plugin,
                vad=self.vad_plugin,
            ).stream()

            asyncio.create_task(self._push_audio_to_stt(track))
            asyncio.create_task(self._read_stt_events())

    async def _push_audio_to_stt(self, track: rtc.RemoteAudioTrack):
        audio_stream = rtc.AudioStream(track)
        async for frame_event in audio_stream:
            if self._stt_stream:
                self._stt_stream.push_frame(frame_event.frame)

    async def _read_stt_events(self):
        async for event in self._stt_stream:
            if event.type == stt.SpeechEventType.START_OF_SPEECH:
                # Speech-start is the authoritative barge-in signal. It must
                # invalidate audio and any in-flight response immediately.
                logger.info("[TURN] candidate_speech_started")
                self._handle_interruption()
                continue

            if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                transcript = event.alternatives[0].text.strip()
                if transcript:
                    logger.info(f"Candidate (STT final segment): {transcript}")
                    self._pending_candidate_parts.append(transcript)
                    self._schedule_candidate_endpoint()

            elif event.type == stt.SpeechEventType.INTERIM_TRANSCRIPT:
                transcript = event.alternatives[0].text.strip()
                # Interim STT is for barge-in/UI feedback only. It never
                # enters the controller and cannot start an LLM generation.
                if transcript and len(transcript) > 2:
                    logger.debug("[TURN] interim_transcript_received")
                    self._handle_interruption()

    def _schedule_candidate_endpoint(self) -> None:
        """Coalesce VAD segments before declaring one candidate turn complete."""
        if self._candidate_endpoint_task and not self._candidate_endpoint_task.done():
            self._candidate_endpoint_task.cancel()
        self._candidate_endpoint_task = asyncio.create_task(
            self._finalize_pending_candidate_after_endpoint()
        )

    async def _finalize_pending_candidate_after_endpoint(self) -> None:
        try:
            await asyncio.sleep(self._candidate_endpoint_delay)
            if not self._pending_candidate_parts:
                return
            parts = self._pending_candidate_parts
            self._pending_candidate_parts = []
            transcript = " ".join(parts).strip()
            now = asyncio.get_running_loop().time()
            is_duplicate_event = (
                transcript == self._last_final_candidate_text
                and now - self._last_final_candidate_at < 2.0
            )
            if not transcript or is_duplicate_event:
                logger.info("[TURN] duplicate_candidate_turn_ignored")
                return
            self._last_final_candidate_text = transcript
            self._last_final_candidate_at = now
            self._candidate_turn_id += 1
            turn_id = self._candidate_turn_id
            logger.info("[TURN] candidate_turn_finalized id=%s", turn_id)
            await self._handle_candidate_turn(transcript, turn_id=turn_id)
        except asyncio.CancelledError:
            return

    # ─── WR-C: Waiting-room auto-timeout ────────────────────────────────
    # Mirrors _schedule_candidate_endpoint()/_finalize_pending_candidate_
    # after_endpoint() above exactly: cancel-and-reschedule shape, a
    # CancelledError catch for the clean-cancel path. See __init__ for the
    # env-var-driven duration and the edge-detection rationale, and
    # _emit_ui_state() for where scheduling/cancellation is actually
    # triggered.

    def _schedule_waiting_room_timeout(self) -> None:
        if self._waiting_room_timeout_task and not self._waiting_room_timeout_task.done():
            self._waiting_room_timeout_task.cancel()
        self._waiting_room_timeout_task = asyncio.create_task(
            self._fire_waiting_room_timeout()
        )

    def _cancel_waiting_room_timeout(self) -> None:
        if self._waiting_room_timeout_task and not self._waiting_room_timeout_task.done():
            self._waiting_room_timeout_task.cancel()

    async def _fire_waiting_room_timeout(self) -> None:
        try:
            await asyncio.sleep(self._waiting_room_timeout_seconds)
        except asyncio.CancelledError:
            return
        logger.info(
            "[WAITING_ROOM] auto-timeout fired after %.0fs", self._waiting_room_timeout_seconds
        )
        # Same shared timeline lock every candidate/UI-driven turn uses —
        # this fires independently of any candidate action and must not
        # interleave with one (e.g. a PROCEED click landing at the same
        # moment). The phase re-check happens INSIDE the lock, not before
        # it, so there's no window between checking and acting.
        async with self._turn_lock:
            if self.controller.context.current_phase != InterviewPhase.WAITING_ROOM:
                # Cancellation should have prevented reaching here at all —
                # defensive, not the only thing relied on (see
                # _cancel_waiting_room_timeout's own docstring reference).
                return
            await self.controller._transition_out_of_waiting_room(auto=True)
            await self._emit_ui_state()

    def _handle_interruption(self):
        old_generation = self._generation_id
        # RT-B2: capture BEFORE resetting -- must reflect the true state at
        # this exact synchronous instant, not wait for _synthesize_and_play()'s
        # own (asynchronous, later-tick) finally-block reset. getattr guards
        # tests (and any other caller) that construct the adapter via
        # object.__new__() without ever setting self._is_speaking.
        self._last_interruption_was_mid_playback = getattr(self, "_is_speaking", False)
        self._is_speaking = False
        self._is_interrupted = True
        self._generation_id += 1
        logger.info(
            "[BARGE_IN] interviewer_generation_invalidated old_id=%s new_id=%s mid_playback=%s",
            old_generation,
            self._generation_id,
            self._last_interruption_was_mid_playback,
        )

        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
                self._tts_queue.task_done()
            except asyncio.QueueEmpty:
                break

        if self._current_synthesis_task and not self._current_synthesis_task.done():
            self._current_synthesis_task.cancel()

        # RT-B1: cancelling the synthesis task above only stops FUTURE
        # capture_frame() calls for this generation. Frames already handed
        # to LiveKit's AudioSource are queued in ITS OWN internal buffer,
        # independent of our task, and would otherwise keep playing out
        # regardless of the cancellation above (RT-A's confirmed root cause
        # of the "clashing" symptom -- capture_frame()'s own docstring: it
        # "queues [the frame] for playback"). clear_queue() is the SDK
        # method that exists specifically to discard already-buffered,
        # not-yet-played audio; it was never called anywhere before this.
        # getattr guards tests that construct the adapter via
        # object.__new__() without ever setting self._audio_source.
        audio_source = getattr(self, "_audio_source", None)
        if audio_source:
            audio_source.clear_queue()



    # ─── Core Turn Handler ─────────────────────────────────────────────

    async def _handle_candidate_turn(
        self,
        transcript: str,
        is_chain: bool = False,
        _lock_held: bool = False,
        turn_id: Optional[int] = None,
    ):
        """Process a finalized candidate utterance through the controller."""
        if not _lock_held:
            async with self._turn_lock:
                await self._handle_candidate_turn(
                    transcript, is_chain=is_chain, _lock_held=True, turn_id=turn_id
                )
            return

        self._is_interrupted = False

        if turn_id is not None:
            if turn_id in self._processed_candidate_turns:
                logger.info("[TURN] duplicate_candidate_turn_ignored id=%s", turn_id)
                return
            self._processed_candidate_turns.add(turn_id)

        transcript = transcript.strip()
        if not transcript and not is_chain:
            logger.info("Dropping empty candidate transcript.")
            return

        # Deduplication: Prevent duplicate processing of the exact same turn
        history = self.controller.context.conversation_history
        if not is_chain and history and history[-1].role == "user" and history[-1].content == transcript:
            logger.info("Dropping duplicate transcript (already processing this turn).")
            return

        # Persist finalized candidate message
        if transcript:
            await self._persist_message(
                speaker="candidate",
                text=transcript,
            )
            await self._emit_transcription(speaker="candidate", text=transcript)

        logger.info("[Agent Thinking...]")
        response_generation = self._generation_id
        logger.info("[LLM] generation_started id=%s turn_id=%s", response_generation, turn_id)
        try:
            action = await self.controller.process_candidate_input(transcript)

            is_provisional = False
            recheck_generation = None
            if response_generation != self._generation_id or self._is_interrupted:
                if self._last_interruption_was_mid_playback:
                    # RT-B1 behavior, unchanged: a response invalidated
                    # while the agent was actively speaking is discarded
                    # outright.
                    logger.info(
                        "[LLM] generation_rejected_mid_playback stale_id=%s current_id=%s",
                        response_generation,
                        self._generation_id,
                    )
                    return
                # RT-B2: invalidated while nothing was audibly playing --
                # don't discard outright. Provisionally continue; a further
                # validity check right before _speak_text() below decides
                # its actual fate. Deliberately scoped to ONLY this path --
                # a turn that was never stale gets no extra re-check, by
                # design (not bundling a second, independent behavioral
                # widening into this fix).
                is_provisional = True
                recheck_generation = self._generation_id
                logger.info(
                    "[LLM] generation_provisionally_preserved stale_id=%s current_id=%s",
                    response_generation,
                    self._generation_id,
                )

            if not action.response:
                if self.controller.context.current_phase == InterviewPhase.COMPLETED:
                    await self._handle_completion()
                return

            logger.info(f"AI ({action.action.value}): {action.response}")

            # Persist finalized agent message
            meta = {"action": action.action.value, "reason": action.reason}
            if self.controller.context.message_sequence == 0:
                meta["is_greeting"] = True

            await self._persist_message(
                speaker="agent",
                text=action.response,
                metadata=meta,
            )
            await self._emit_transcription(speaker="agent", text=action.response)
            await self._persist_action_event(action)

            if is_provisional:
                # RT-B2: re-check immediately before the point that would
                # actually queue this for synthesis -- catches a further
                # interruption that arrived during the persistence/emission
                # awaits just above. Generation comparison only, not
                # self._is_interrupted: that flag is still True from the
                # ORIGINAL interruption that put us on this path at all (it
                # only resets at the top of the NEXT _handle_candidate_turn
                # call) -- checking it here would reject every provisional
                # response unconditionally, not just genuinely re-invalidated
                # ones. self._generation_id is the reliable "did anything
                # NEW happen since" signal: every interruption bumps it.
                if self._generation_id != recheck_generation:
                    logger.info(
                        "[LLM] generation_discarded_at_recheck stale_id=%s current_id=%s",
                        recheck_generation,
                        self._generation_id,
                    )
                    return
                # Recheck passed: this provisional response is still valid.
                # Clear the stale interruption flag ourselves -- we've just
                # proven freshness explicitly, so _speak_text()'s own
                # (appropriately strict) "not self._is_interrupted" guard
                # must not reject what we've just decided is safe to speak.
                self._is_interrupted = False

            await self._speak_text(action.response)

            if getattr(action, "should_transition", False):
                self.controller.context.conversation_history.clear()

            if self.controller.context.current_phase == InterviewPhase.COMPLETED:
                await self._handle_completion()
                return
        except Exception as e:
            logger.error(f"Error processing candidate turn: {e}", exc_info=True)
        finally:
            await self._emit_ui_state()

    async def _speak_text(self, text: str):
        """Enqueue text for TTS playback without artificial chunking."""
        # Increment generation ID so any stale queued items are invalidated
        self._generation_id += 1
        current_gen = self._generation_id
        logger.info("[TTS] generation_started id=%s", current_gen)
        
        if not self._is_interrupted and self._generation_id == current_gen:
            try:
                await asyncio.wait_for(self._tts_queue.put((text, 1, 1, current_gen)), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("TTS queue full, dropping text.")

    async def _speak_and_persist(self, text: str, is_agent: bool = True):
        """Convenience: persist a message and speak it."""
        if is_agent:
            self.controller.append_message("assistant", text)
            await self._persist_message(speaker="agent", text=text)
            await self._emit_transcription(speaker="agent", text=text)
        await self._speak_text(text)

    # ─── Persistence Helpers ───────────────────────────────────────────

    async def _persist_message(
        self, speaker: str, text: str, metadata: Optional[dict] = None,
    ):
        """Persist a finalized transcript message."""
        if not self.persistence:
            return
        ctx = self.controller.context
        seq = ctx.message_sequence + 1
        ctx.message_sequence = seq
        try:
            await self.persistence.save_message(
                session_id=ctx.session_id,
                sequence=seq,
                speaker=speaker,
                text=text,
                phase=ctx.current_phase.value,
                metadata=metadata,
            )
        except Exception as e:
            logger.error(f"Failed to persist message: {e}")

    async def _persist_action_event(self, action):
        """Persist meaningful events based on the controller action."""
        if not self.persistence:
            return

        ctx = self.controller.context
        event_type = None
        metadata = {}

        if action.action == ActionEnum.TRANSITION:
            event_type = "PHASE_STARTED"
            metadata["phase"] = ctx.current_phase.value
        elif action.action == ActionEnum.HINT:
            event_type = "HINT_REQUESTED"
            metadata["hints_used"] = ctx.hints_used
        elif action.action == ActionEnum.FOLLOW_UP:
            event_type = "FOLLOW_UP"
            metadata["followups_used"] = ctx.followups_used
        elif action.action == ActionEnum.EVALUATE:
            event_type = "QUESTION_COMPLETED"
        elif action.action == ActionEnum.END:
            event_type = "SESSION_COMPLETED"

        if action.detected_candidate_control:
            ctrl = action.detected_candidate_control.value
            if ctrl == "SKIP_QUESTION":
                event_type = "QUESTION_SKIPPED"
            elif ctrl == "SKIP_SECTION":
                event_type = "SECTION_SKIPPED"
            elif ctrl == "MOVE_TO_TECHNICAL":
                event_type = "MOVE_TO_TECHNICAL"
            elif ctrl == "END_INTERVIEW":
                event_type = "SESSION_TERMINATED"

        if event_type:
            seq = ctx.event_sequence + 1
            ctx.event_sequence = seq
            try:
                await self.persistence.save_event(
                    session_id=ctx.session_id,
                    sequence=seq,
                    event_type=event_type,
                    phase=ctx.current_phase.value,
                    metadata=metadata,
                )
            except Exception as e:
                logger.error(f"Failed to persist event: {e}")

    async def _handle_completion(self):
        """Handle interview completion — persist final state."""
        if self._completion_persisted:
            logger.info("[COMPLETION] duplicate_completion_ignored")
            return
        
        # Drain the TTS queue so audio doesn't get cut off before disconnecting
        if not self._tts_queue.empty():
            await self._tts_queue.join()
        if self._current_synthesis_task and not self._current_synthesis_task.done():
            try:
                import asyncio
                await asyncio.wait_for(asyncio.shield(self._current_synthesis_task), timeout=30.0)
            except Exception as e:
                logger.warning(f"Error waiting for final TTS playback: {e}")
        
        # Give audio engine a little time to empty buffers
        await asyncio.sleep(2.0)
        
        ctx = self.controller.context
        logger.info("Interview completed. Persisting final state.")

        await self.controller.generate_final_evaluation()
        if self.persistence:
            seq = ctx.event_sequence + 1
            ctx.event_sequence = seq
            try:
                await self.persistence.save_event(
                    session_id=ctx.session_id,
                    sequence=seq,
                    event_type="SESSION_COMPLETED",
                    phase=InterviewPhase.COMPLETED.value,
                )
            except Exception:
                logger.exception("[COMPLETION] failed_to_persist_completion_event")
            persisted = await self.persistence.save_completion(ctx)
            if persisted:
                self._completion_persisted = True
            else:
                logger.error(
                    "[COMPLETION] persistence_failed session_id=%s — will retry on teardown",
                    ctx.session_id,
                )

            # Phase 8C: submit the normalized Evaluation/Score rows. Same
            # distinctly-tagged, greppable pattern as the completion-
            # persistence fix above -- independent target, independent
            # tracking, independent teardown retry (main.py).
            evaluation_submitted = await self.persistence.submit_evaluation(ctx)
            if evaluation_submitted:
                self._evaluation_submitted = True
            else:
                logger.error(
                    "[EVALUATION_SUBMIT] persistence_failed session_id=%s — will retry on teardown",
                    ctx.session_id,
                )
        else:
            self._completion_persisted = True
            self._evaluation_submitted = True

        await self._emit_ui_state()

    # ─── TTS Playback Loop ────────────────────────────────────────────

    async def _playback_loop(self):
        """Sequentially consumes text chunks from the queue and plays audio."""
        while True:
            chunk_data = await self._tts_queue.get()
            if isinstance(chunk_data, tuple) and len(chunk_data) == 4:
                chunk, chunk_idx, total_chunks, gen_id = chunk_data
            elif isinstance(chunk_data, tuple) and len(chunk_data) == 3:
                chunk, chunk_idx, total_chunks = chunk_data
                gen_id = 0
            else:
                chunk, chunk_idx, total_chunks, gen_id = chunk_data, 1, 1, 0

            # Discard if stale or interrupted
            if self._is_interrupted or gen_id != self._generation_id:
                logger.info("[TTS] generation_rejected stale_id=%s", gen_id)
                self._tts_queue.task_done()
                continue

            self._current_synthesis_task = asyncio.create_task(
                self._synthesize_and_play(chunk, chunk_idx, total_chunks, gen_id)
            )
            try:
                await self._current_synthesis_task
            except asyncio.CancelledError:
                logger.info("[TTS] playback_cancelled generation_id=%s", gen_id)
            except Exception as e:
                # TTS failure must NOT crash the loop or affect the persisted message
                logger.error(f"TTS Playback error (safe to continue): {e}")
            finally:
                self._tts_queue.task_done()

    async def _synthesize_and_play(self, text: str, chunk_idx: int = 1, total_chunks: int = 1, gen_id: int = 0):
        if self._is_interrupted or (gen_id != 0 and gen_id != self._generation_id):
            raise asyncio.CancelledError()
            
        logger.info(f"[TTS-DIAG] Synthesizing response (Gen {gen_id}): {text[:40]}...")

        # Audit fix (2026-08-27): cache fixed, non-personalized system
        # messages (acks, skip/end-of-section lines, etc.) on disk, keyed by
        # exactly the inputs that change the resulting audio -- provider,
        # voice/model, language, and the text itself. Deliberately restricted
        # to _FIXED_SYSTEM_MESSAGE_TEXTS: LLM-generated conversational text
        # (greetings, question presentations, the CLOSING goodbye) is
        # different content nearly every turn and must never be cached --
        # replaying stale audio for genuinely new text would be a real bug,
        # not an optimization. See tts_cache.py's own docstring for why this
        # is disk-backed rather than an in-memory dict (each session is its
        # own worker subprocess, so only a disk cache is actually shared
        # across candidates/sessions, which is most of the real saving).
        synth_cache_key = None
        if text in _FIXED_SYSTEM_MESSAGE_TEXTS:
            provider = getattr(self.tts_plugin, "provider_name", "unknown")
            voice = getattr(self.tts_plugin, "model_name", "unknown")
            language = getattr(self.controller.context, "language", "en")
            synth_cache_key = tts_cache.cache_key(provider, voice, language, text)
            cached_pcm = tts_cache.load(synth_cache_key)
            if cached_pcm:
                if self._is_interrupted or (gen_id != 0 and gen_id != self._generation_id):
                    raise asyncio.CancelledError()
                logger.info(
                    f"[TTS-CACHE] Cache hit for Gen {gen_id} ({len(cached_pcm)} bytes) "
                    "-- skipping the synthesis API call entirely."
                )
                self._is_speaking = True
                try:
                    num_channels = self.tts_plugin.num_channels
                    samples_per_channel = len(cached_pcm) // (2 * num_channels)
                    frame = rtc.AudioFrame(
                        cached_pcm, self.tts_plugin.sample_rate, num_channels, samples_per_channel
                    )
                    await self._audio_source.capture_frame(frame)
                    logger.info(f"[TTS-DIAG] Synthesis playback complete (Gen {gen_id}) [cached]")
                finally:
                    self._is_speaking = False
                return

        # Audit fix (2026-08-27): Groq's TTS 429 response never carries a
        # usable retry-after/rate-limit-reset header through this SDK
        # (Headers: {} every time this has been observed live) -- so
        # retry_after always computed to 0.0 and the "pause the queue"
        # branch below it never actually ran. The turn was just dropped
        # outright, silently, every single time -- which is why entering a
        # fresh section (a burst of back-to-back generations right after
        # PROCEED_TO_NEXT_SECTION) reliably produced total silence: the one
        # turn that mattered most (the section's opening line) was also the
        # one most likely to land inside that burst. Groq's TTS rate limit
        # in practice is a short per-minute burst, not a hard daily quota --
        # a bounded retry with a fixed backoff clears most of these instead
        # of abandoning the turn on the first hit.
        # Audit fix (2026-08-27, follow-up): a live 429 burst was confirmed
        # to still be in effect 3+ seconds later (both the first attempt AND
        # both 1.5s-spaced retries all failed) -- direct probing right after
        # showed the account was NOT actually near its quota (packets
        # succeeded cleanly moments later with 70+/100 requests still
        # available), so this is a short burst window, not exhaustion, but
        # 1.5s wasn't long enough to reliably outlast it. Escalating backoff
        # (2s/4s/8s, ~14s worst case across all 3 retries) trades a longer
        # possible silence for a much better chance of actually catching the
        # window's reset, instead of giving up while comfortably still
        # inside it.
        MAX_TTS_429_RETRIES = 3
        TTS_429_RETRY_DELAYS_S = [2.0, 4.0, 8.0]

        try:
            attempt = 0
            # Only populated when synth_cache_key is set (a real fixed-
            # message cache miss) -- collects the raw PCM bytes actually
            # captured so a successful synthesis can be saved for next time.
            collected_pcm = [] if synth_cache_key else None
            while True:
                try:
                    # We rely on Groq directly and disable internal LiveKit retries so we can control rate-limit handling.
                    async for audio_chunk in self.tts_plugin.synthesize(text, conn_options=APIConnectOptions(max_retry=0)):
                        if self._is_interrupted or (gen_id != 0 and gen_id != self._generation_id):
                            logger.info("[TTS] Interrupted during playback")
                            raise asyncio.CancelledError()
                        # RT-B2: set on/before the first captured frame of this
                        # generation -- the precise "audibly speaking" signal
                        # _handle_interruption() snapshots.
                        self._is_speaking = True
                        if collected_pcm is not None:
                            collected_pcm.append(bytes(audio_chunk.frame.data))
                        await self._audio_source.capture_frame(audio_chunk.frame)

                    logger.info(f"[TTS-DIAG] Synthesis playback complete (Gen {gen_id})")
                    if synth_cache_key and collected_pcm:
                        tts_cache.save(synth_cache_key, b"".join(collected_pcm))
                    if attempt > 0:
                        # Only clear the retry overlay if we actually showed
                        # one — a normal, never-retried turn shouldn't fire
                        # an "ok" broadcast for every single utterance.
                        await self._broadcast_tts_status("ok")
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    err_str = str(e)
                    status_code = getattr(e, "status_code", None)
                    response = getattr(e, "response", None)
                    headers = getattr(response, "headers", {}) if response else {}

                    is_429 = (status_code == 429) or ("429" in err_str) or ("Too Many Requests" in err_str)

                    # Audit fix (2026-08-27, follow-up): Groq's 429 is a
                    # per-KEY daily quota, confirmed live -- waiting seconds
                    # doesn't help the SAME key's quota reappear, but a
                    # genuinely different key has its own independent quota.
                    # When multi-key rotation is configured (key_rotator
                    # attribute -- see groq_key_rotator.py), a 429 rotates to
                    # the next key IMMEDIATELY, no backoff delay, and retries
                    # the same text right away -- "once, not a counter and
                    # trial" per the product ask. Only once every configured
                    # key has been tried does this fall through to the give-
                    # up path below. The escalating-backoff path underneath
                    # stays exactly as before for anything WITHOUT a
                    # key_rotator (Azure, or Groq with only the single legacy
                    # GROQ_API_KEY configured) -- there, a genuinely transient
                    # burst is still the more likely explanation.
                    key_rotator = getattr(self.tts_plugin, "key_rotator", None)
                    if is_429 and key_rotator is not None:
                        new_key = key_rotator.rotate()
                        if new_key is not None:
                            attempt += 1
                            logger.warning(
                                f"[TTS-DIAG] Groq TTS rate limit (429) hit for Gen {gen_id} "
                                f"-- switching to key {key_rotator.current_position}/{key_rotator.total_keys} immediately."
                            )
                            await self._broadcast_tts_status(
                                "switching_key", key_rotator.current_position, key_rotator.total_keys
                            )
                            if self._is_interrupted or (gen_id != 0 and gen_id != self._generation_id):
                                raise asyncio.CancelledError()
                            self.tts_plugin = key_rotator.rebuild_plugin()
                            continue
                        else:
                            logger.warning(
                                f"[TTS-DIAG] Groq TTS rate limit (429) hit for Gen {gen_id} -- "
                                f"all {key_rotator.total_keys} configured key(s) exhausted for today."
                            )
                            await self._broadcast_tts_status("gave_up", attempt, key_rotator.total_keys, text=text)
                            return

                    if is_429 and attempt < MAX_TTS_429_RETRIES:
                        delay = TTS_429_RETRY_DELAYS_S[attempt]
                        attempt += 1
                        logger.warning(
                            f"[TTS-DIAG] Groq TTS rate limit (429) hit for Gen {gen_id} "
                            f"(retry {attempt}/{MAX_TTS_429_RETRIES} in {delay}s)."
                        )
                        await self._broadcast_tts_status("retrying", attempt, MAX_TTS_429_RETRIES)
                        await asyncio.sleep(delay)
                        # A real interruption/barge-in during the backoff wait
                        # must still win -- don't retry into a stale turn.
                        if self._is_interrupted or (gen_id != 0 and gen_id != self._generation_id):
                            raise asyncio.CancelledError()
                        continue

                    if is_429:
                        logger.warning(
                            f"[TTS-DIAG] Groq TTS rate limit (429) hit for Gen {gen_id} "
                            f"after {attempt} retries. Headers: {dict(headers)}. "
                            "Skipping TTS for this turn to prevent quota starvation."
                        )
                        await self._broadcast_tts_status("gave_up", attempt, MAX_TTS_429_RETRIES, text=text)
                        return

                    logger.error(f"[TTS-DIAG] TTS provider failed for Gen {gen_id} ({type(e).__name__}): {err_str}")
                    # Audit fix (2026-08-27): any non-429 TTS failure (Azure
                    # outage, network error, etc.) also leaves this turn
                    # unspoken -- same client-side fallback trigger as the
                    # 429 give-up path, not just the rate-limit case.
                    await self._broadcast_tts_status("gave_up", attempt, MAX_TTS_429_RETRIES, text=text)
                    return
        finally:
            # RT-B2: single reset point covering normal completion,
            # CancelledError, and the generic-Exception path uniformly --
            # rather than duplicating the reset at three separate exit
            # points where one could get missed.
            self._is_speaking = False
