"""
VoiceInterviewAdapter — bridges LiveKit audio streams to the InterviewController.

Orchestrates: STT → Controller → TTS
Persists finalized messages and meaningful events.
"""
import asyncio
import logging
import re
from typing import Optional, List
from livekit.agents import stt, tts, vad
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

        # Audio playback queue
        self._tts_queue: asyncio.Queue[str] = asyncio.Queue()
        self._playback_task: Optional[asyncio.Task] = None
        self._current_synthesis_task: Optional[asyncio.Task] = None
        self._is_interrupted = False

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
        else:
            # Fresh start
            self.controller.start_interview()
            logger.info("Voice adapter started. Kicking off interview...")
            await self._handle_candidate_turn("")

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

    async def _handle_candidate_turn(self, transcript: str):
        """Process a finalized candidate utterance through the controller."""
        self._is_interrupted = False

        # Persist finalized candidate message
        if transcript:
            await self._persist_message(
                speaker="candidate",
                text=transcript,
            )

        logger.info("[Agent Thinking...]")
        action = await self.controller.process_candidate_input(transcript)

        if not action.response:
            return

        logger.info(f"AI ({action.action.value}): {action.response}")

        # Persist finalized agent message
        await self._persist_message(
            speaker="agent",
            text=action.response,
            metadata={"action": action.action.value, "reason": action.reason},
        )

        # Persist meaningful events
        await self._persist_action_event(action)

        # Check if interview completed
        if self.controller.context.current_phase == InterviewPhase.COMPLETED:
            # Speak the final response first, then handle completion
            await self._speak_text(action.response)
            await self._handle_completion()
            return

        # Speak the response
        await self._speak_text(action.response)

    async def _speak_text(self, text: str):
        """Segment and enqueue text for TTS playback."""
        chunks = self._segment_text(text)
        logger.info(f"Segmented AI response into {len(chunks)} TTS chunks.")

        for chunk in chunks:
            if not self._is_interrupted:
                await self._tts_queue.put(chunk)

    async def _speak_and_persist(self, text: str, is_agent: bool = True):
        """Convenience: persist a message and speak it."""
        if is_agent:
            self.controller.append_message("assistant", text)
            await self._persist_message(speaker="agent", text=text)
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

    # ─── TTS Playback Loop ────────────────────────────────────────────

    async def _playback_loop(self):
        """Sequentially consumes text chunks from the queue and plays audio."""
        while True:
            chunk = await self._tts_queue.get()

            if self._is_interrupted:
                self._tts_queue.task_done()
                continue

            self._current_synthesis_task = asyncio.create_task(
                self._synthesize_and_play(chunk)
            )
            try:
                await self._current_synthesis_task
            except asyncio.CancelledError:
                logger.info(f"Cancelled playback for chunk: {chunk[:20]}...")
            except Exception as e:
                logger.error(f"Playback error: {e}")
            finally:
                self._tts_queue.task_done()

    async def _synthesize_and_play(self, text: str):
        try:
            logger.info(f"Synthesizing: {text[:40]}...")
            async for audio_chunk in self.tts_plugin.synthesize(text):
                if self._is_interrupted:
                    raise asyncio.CancelledError()
                await self._audio_source.capture_frame(audio_chunk.frame)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error during TTS synthesis: {e}")
