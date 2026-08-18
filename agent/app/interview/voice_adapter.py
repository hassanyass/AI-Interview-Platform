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

from app.interview.controller import InterviewController
from app.interview.models import ActionEnum, InterviewPhase
from app.interview.persistence import InterviewPersistence

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
        self._is_interrupted = False
        self._generation_id = 0
        # Groq can return 429 while its LiveKit plugin is already retrying the
        # same request internally.  Keep a local cooldown so queued chunks do
        # not immediately create another burst of requests.
        self._tts_rate_limited_until = 0.0
        try:
            self._tts_rate_limit_cooldown = max(
                5.0, float(os.getenv("TTS_429_COOLDOWN_SECONDS", "30"))
            )
        except ValueError:
            self._tts_rate_limit_cooldown = 30.0
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
        
    async def _emit_transcription(self, speaker: str, text: str, is_final: bool = True):
        """Broadcasts a transcription update to the frontend via Data Channel."""
        import json
        payload = json.dumps({
            "id": f"{speaker}-{hash(text)}",
            "speaker": speaker,
            "text": text,
            "isFinal": is_final
        }).encode("utf-8")
        await self.room.local_participant.publish_data(
            payload,
            reliable=True,
            topic="transcription"
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
        if command in ("SKIP_QUESTION", "SKIP_SECTION", "MOVE_TO_TECHNICAL", "CHANGE_QUESTION"):
            self._handle_interruption()
            # Wait a tiny bit to ensure the audio frame buffer clears
            await asyncio.sleep(0.05)
            
        self._is_interrupted = False
        try:
            action = await self.controller.process_ui_command(command, payload)
            
            if not action or not action.response:
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
            if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                transcript = event.alternatives[0].text.strip()
                if transcript:
                    logger.info(f"Candidate (STT): {transcript}")
                    await self._handle_candidate_turn(transcript)

            elif event.type == stt.SpeechEventType.INTERIM_TRANSCRIPT:
                transcript = event.alternatives[0].text.strip()
                if transcript and not self._is_interrupted:
                    if len(transcript) > 2:
                        self._handle_interruption()

    def _handle_interruption(self):
        logger.info("Candidate barged in! Interrupting playback...")
        self._is_interrupted = True
        self._generation_id += 1

        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
                self._tts_queue.task_done()
            except asyncio.QueueEmpty:
                break

        if self._current_synthesis_task and not self._current_synthesis_task.done():
            self._current_synthesis_task.cancel()

    def _segment_text(self, text: str, max_len: int = 190) -> List[str]:
        """Splits text into chunks <= max_len at natural sentence boundaries."""
        pattern = r'([^.!?؟:;؛\n]+[.!?؟:;؛\n]+)'
        parts = re.split(pattern, text)
        parts = [p.strip() for p in parts if p.strip()]

        chunks = []
        current_chunk = ""

        for part in parts:
            if len(current_chunk) + len(part) + 1 <= max_len:
                current_chunk += (" " if current_chunk else "") + part
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                if len(part) > max_len:
                    subparts = re.split(r'([^,،\s]+[,،\s]+)', part)
                    subparts = [sp.strip() for sp in subparts if sp.strip()]
                    current_sub = ""
                    for sp in subparts:
                        if len(current_sub) + len(sp) + 1 <= max_len:
                            current_sub += (" " if current_sub else "") + sp
                        else:
                            if current_sub:
                                chunks.append(current_sub)
                            current_sub = sp
                    if current_sub:
                        current_chunk = current_sub
                else:
                    current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # ─── Core Turn Handler ─────────────────────────────────────────────

    async def _handle_candidate_turn(self, transcript: str, is_chain: bool = False, _lock_held: bool = False):
        """Process a finalized candidate utterance through the controller."""
        if not _lock_held:
            async with self._turn_lock:
                await self._handle_candidate_turn(transcript, is_chain=is_chain, _lock_held=True)
            return

        self._is_interrupted = False

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
        try:
            action = await self.controller.process_candidate_input(transcript)

            if not action.response:
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
        """Segment and enqueue text for TTS playback."""
        # Increment generation ID so any stale queued items are invalidated
        self._generation_id += 1
        current_gen = self._generation_id
        
        # Always segment for Groq TTS to avoid rate limits / length limits
        chunks = self._segment_text(text)
        logger.info(f"Segmented AI response into {len(chunks)} TTS chunks (Gen {current_gen}).")

        for i, chunk in enumerate(chunks, 1):
            if not self._is_interrupted and self._generation_id == current_gen:
                try:
                    await asyncio.wait_for(self._tts_queue.put((chunk, i, len(chunks), current_gen)), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("TTS queue full, dropping chunk.")

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
        ctx = self.controller.context
        logger.info("Interview completed. Persisting final state.")

        if self.persistence:
            seq = ctx.event_sequence + 1
            ctx.event_sequence = seq
            await self.persistence.save_event(
                session_id=ctx.session_id,
                sequence=seq,
                event_type="SESSION_COMPLETED",
                phase=InterviewPhase.COMPLETED.value,
            )
            await self.persistence.save_completion(ctx)
            
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
                self._tts_queue.task_done()
                continue

            self._current_synthesis_task = asyncio.create_task(
                self._synthesize_and_play(chunk, chunk_idx, total_chunks, gen_id)
            )
            try:
                await self._current_synthesis_task
            except asyncio.CancelledError:
                logger.info(f"Cancelled playback for chunk: {chunk[:20]}...")
            except Exception as e:
                # TTS failure must NOT crash the loop or affect the persisted message
                logger.error(f"TTS Playback error (safe to continue): {e}")
            finally:
                self._tts_queue.task_done()

    async def _synthesize_and_play(self, text: str, chunk_idx: int = 1, total_chunks: int = 1, gen_id: int = 0):
        now = asyncio.get_running_loop().time()
        if now < self._tts_rate_limited_until:
            remaining = self._tts_rate_limited_until - now
            logger.info(
                "[TTS-DIAG] Skipping synthesis during Groq rate-limit cooldown "
                f"({remaining:.1f}s remaining). Transcript remains available."
            )
            return

        # Strict execution of the configured TTS plugin
        provider = getattr(self.tts_plugin, "provider_name", "Unknown")
        model = getattr(self.tts_plugin, "model_name", "Unknown")
        lang = getattr(self.controller.context, "language", "en")
        
        logger.info(f"[TTS-DIAG] Provider: {provider}")
        logger.info(f"[TTS-DIAG] Model: {model}")
        logger.info(f"[TTS-DIAG] Synthesizing {lang} speech")
        import random
        # The LiveKit provider also retries API failures. Keep adapter-level
        # retries for transient errors bounded so one turn cannot block the
        # playback queue for a long time.
        try:
            max_retries = max(1, int(os.getenv("TTS_MAX_RETRIES", "2")))
        except ValueError:
            max_retries = 2
        try:
            rate_limit_retry_delay = max(
                1.0, float(os.getenv("TTS_429_RETRY_DELAY_SECONDS", "3"))
            )
        except ValueError:
            rate_limit_retry_delay = 3.0
        rate_limit_retry_used = False
        base_delay = 1.0
        
        for attempt in range(1, max_retries + 1):
            if self._is_interrupted or (gen_id != 0 and gen_id != self._generation_id):
                raise asyncio.CancelledError()
            
            try:
                resp_id = id(text)
                logger.info(
                    f"[TTS-DIAG] Synthesizing chunk {chunk_idx}/{total_chunks} "
                    f"(ID: {resp_id}) - Attempt {attempt}/{max_retries}: {text[:40]}..."
                )
                
                # Disable LiveKit's default provider retries here. A 429 is a
                # quota/rate-limit response, not a transient connection error;
                # retrying it only delays the interview and duplicates traffic.
                async for audio_chunk in self.tts_plugin.synthesize(
                    text,
                    conn_options=APIConnectOptions(max_retry=0),
                ):
                    if self._is_interrupted or (gen_id != 0 and gen_id != self._generation_id):
                        raise asyncio.CancelledError()
                    await self._audio_source.capture_frame(audio_chunk.frame)
                
                logger.info(f"[TTS-DIAG] Success for chunk {chunk_idx}/{total_chunks} (ID: {resp_id})")
                return
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                err_str = str(e)
                err_type = type(e).__name__
                status_code = getattr(e, "status_code", None)
                # Some API errors expose a response or message attribute
                err_msg = getattr(e, "message", getattr(e, "body", None))
                
                is_429 = (status_code == 429) or ("429" in err_str) or ("Too Many Requests" in err_str)
                
                logger.warning(
                    f"[TTS-DIAG] Failed chunk {chunk_idx}/{total_chunks} (ID: {resp_id}) "
                    f"Attempt {attempt}/{max_retries}. Status: {status_code or (429 if is_429 else 'unknown')} "
                    f"| Type: {err_type} | Error: {err_str} | Body: {err_msg}"
                )
                
                if is_429:
                    # Groq's TTS token window commonly resets within a few
                    # seconds. Allow exactly one reset-aware retry; if the
                    # window is a hard quota, enter cooldown instead.
                    if not rate_limit_retry_used:
                        rate_limit_retry_used = True
                        logger.warning(
                            "[TTS-DIAG] Groq TTS rate limit window active. "
                            f"Waiting {rate_limit_retry_delay:.1f}s for one recovery retry."
                        )
                        await asyncio.sleep(rate_limit_retry_delay)
                        continue

                    self._tts_rate_limited_until = (
                        asyncio.get_running_loop().time() + self._tts_rate_limit_cooldown
                    )
                    logger.error(
                        "[TTS-DIAG] Groq rate limit detected. Entering "
                        f"{self._tts_rate_limit_cooldown:.0f}s cooldown; continuing "
                        "without voice so the interview transcript can proceed."
                    )
                    return

                if attempt == max_retries:
                    logger.error(f"[TTS-DIAG] Max retries reached for chunk {chunk_idx}/{total_chunks}. Failing gracefully.")
                    break
                    
                retry_after = getattr(e, "retry_after", None)
                if retry_after is not None:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                else:
                    delay = base_delay + random.uniform(0, 0.2)
                    
                logger.info(f"[TTS-DIAG] Retrying chunk {chunk_idx}/{total_chunks} after {delay:.2f}s...")
                await asyncio.sleep(delay)
