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
        if command in ("SKIP_QUESTION", "SKIP_SECTION", "MOVE_TO_TECHNICAL", "CHANGE_QUESTION", "PROCEED_TO_NEXT_SECTION"):
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
                if getattr(action, "should_transition", False):
                    self.controller.context.conversation_history.clear()
                if command in ("SKIP_QUESTION", "SKIP_SECTION", "MOVE_TO_TECHNICAL", "CHANGE_QUESTION", "SUBMIT_CODE", "END_INTERVIEW", "PROCEED_TO_NEXT_SECTION"):
                    # WR-C: chains straight into the next section's opening
                    # ASK turn — no separate "welcome back" message is
                    # needed, the new section's own first turn carries it
                    # (same reasoning as WR-B's plan: this phase carries no
                    # LLM generation of its own).
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
                
            # Chain to the next turn to generate the new question
            if command in ("SKIP_QUESTION", "SKIP_SECTION", "MOVE_TO_TECHNICAL", "CHANGE_QUESTION", "SUBMIT_CODE", "END_INTERVIEW"):
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
            await self.persistence.save_completion(ctx)
        self._completion_persisted = True
            
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

        try:
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
                    await self._audio_source.capture_frame(audio_chunk.frame)

                logger.info(f"[TTS-DIAG] Synthesis playback complete (Gen {gen_id})")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                err_str = str(e)
                status_code = getattr(e, "status_code", None)
                response = getattr(e, "response", None)
                headers = getattr(response, "headers", {}) if response else {}

                is_429 = (status_code == 429) or ("429" in err_str) or ("Too Many Requests" in err_str)

                if is_429:
                    retry_after_str = headers.get("retry-after") or headers.get("x-ratelimit-reset-requests") or headers.get("x-ratelimit-reset-tokens")
                    try:
                        retry_after = float(retry_after_str) if retry_after_str else 0.0
                    except (ValueError, TypeError):
                        retry_after = 0.0

                    logger.warning(
                        f"[TTS-DIAG] Groq TTS rate limit (429) hit for Gen {gen_id}. "
                        f"Headers: {dict(headers)}. Skipping TTS for this turn to prevent quota starvation."
                    )

                    # If a reasonable reset time is provided, delay pulling the next item from the queue
                    if 0 < retry_after <= 15.0:
                        logger.info(f"[TTS-DIAG] Pausing TTS queue for {retry_after:.1f}s to respect provider reset window.")
                        await asyncio.sleep(retry_after)
                    return

                logger.error(f"[TTS-DIAG] TTS provider failed for Gen {gen_id} ({type(e).__name__}): {err_str}")
        finally:
            # RT-B2: single reset point covering normal completion,
            # CancelledError, and the generic-Exception path uniformly --
            # rather than duplicating the reset at three separate exit
            # points where one could get missed.
            self._is_speaking = False
