"""
LiveKit Agent entrypoint — Phase 5.

Loads real session data from the backend, acquires agent lease,
initializes the InterviewController with real context, and manages
the full lifecycle including disconnect/reconnect and completion.
"""
import asyncio
import hashlib
import logging
import os
import uuid as uuid_mod

from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.plugins import groq, silero

# Load the repository configuration explicitly.  Override inherited process
# variables so restarting the worker actually picks up a rotated API key.
_repo_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
_agent_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(_repo_env, override=True)
load_dotenv(_agent_env, override=False)

from app.llm.groq_provider import GroqProvider
from app.interview.persistence import APIPersistence
from app.interview.models import (
    InterviewRuntimeContext, InterviewPhase, InterviewPlan,
    SectionProgress, SectionLimits, Message,
    Question, QuestionRecord,
)
from app.interview.controller import InterviewController
from app.interview.voice_adapter import VoiceInterviewAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# Agent lease renewal interval (seconds)
LEASE_RENEWAL_INTERVAL = 300  # 5 minutes


async def entrypoint(ctx: JobContext):
    logger.info("Initializing Agent (Phase 5)...")

    # A fingerprint makes key precedence diagnosable without logging secrets.
    groq_key = os.getenv("GROQ_API_KEY", "")
    logger.info(
        "Groq credential loaded: present=%s length=%d fingerprint=%s",
        bool(groq_key),
        len(groq_key),
        hashlib.sha256(groq_key.encode()).hexdigest()[:10] if groq_key else "missing",
    )

    # ─── Validate Environment ──────────────────────────────────────────
    required_vars = [
        "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
        "GROQ_API_KEY", "AGENT_API_SECRET", "BACKEND_INTERNAL_URL",
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        return

    # ─── Extract session ID from room name ─────────────────────────────
    room_name = ctx.room.name
    logger.info(f"Connecting to room {room_name}...")

    # Room names follow the pattern: interview-{session_id}
    session_id = None
    if room_name.startswith("interview-"):
        session_id = room_name[len("interview-"):]
    else:
        logger.error(f"Unexpected room name format: {room_name}")
        return

    # ─── Connect to room ───────────────────────────────────────────────
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Agent connected to interview room.")

    # ─── Initialize persistence ────────────────────────────────────────
    agent_id = f"agent-{uuid_mod.uuid4().hex[:8]}"
    backend_url = os.getenv("BACKEND_INTERNAL_URL", "http://127.0.0.1:8000")
    agent_secret = os.getenv("AGENT_API_SECRET", "")

    persistence = APIPersistence(
        backend_url=backend_url,
        agent_secret=agent_secret,
        agent_id=agent_id,
    )

    # ─── Load session from backend ─────────────────────────────────────
    session_data = await persistence.load_session(session_id)
    if not session_data:
        logger.error(f"Could not load session {session_id}. Exiting.")
        await persistence.close()
        return

    logger.info(f"Loaded session: role={session_data.get('role')}, level={session_data.get('level')}, status={session_data.get('status')}")

    # ─── Build InterviewRuntimeContext ─────────────────────────────────
    duration_minutes = session_data.get("duration_minutes", 15)
    checkpoint = session_data.get("latest_checkpoint") or {}
    recent_messages = session_data.get("recent_messages", [])
    
    # Safely determine if the initial greeting was already generated and persisted.
    has_greeting = any(
        msg.get("metadata", {}) and msg.get("metadata", {}).get("is_greeting") is True
        for msg in recent_messages
    )

    # If resuming (has_greeting is True), restore state regardless of status
    is_resuming = has_greeting
    
    if is_resuming:
        logger.info("Restoring from checkpoint/messages (reconnect scenario)...")
        
        # Recover sequences from messages if checkpoint is missing
        max_msg_seq = max([m.get("sequence_number", 0) for m in recent_messages], default=0)
        
        context = InterviewRuntimeContext(
            session_id=session_id,
            candidate_id=str(session_data["candidate_profile_id"]),
            role=session_data["role"],
            confirmed_level=session_data["level"],
            language=session_data["language"],
            job_description=session_data.get("job_description"),
            candidate_profile=session_data.get("candidate_profile", {}),
            current_phase=InterviewPhase(checkpoint.get("current_phase", "CREATED")),
            question_index=checkpoint.get("question_index", 0),
            hints_used=checkpoint.get("hints_used", 0),
            followups_used=checkpoint.get("followups_used", 0),
            time_remaining_seconds=checkpoint.get("time_remaining_seconds", duration_minutes * 60),
            message_sequence=max(checkpoint.get("last_message_sequence", 0), max_msg_seq),
            event_sequence=checkpoint.get("last_event_sequence", 0),
        )

        # Restore conversation history from persisted messages
        for msg in recent_messages:
            context.conversation_history.append(
                Message(role="user" if msg["speaker"] == "candidate" else "assistant", content=msg["text"])
            )

        # Restore section progress from checkpoint
        sp = checkpoint.get("section_progress", {})
        if "background" in sp:
            bg = sp["background"]
            context.background_progress.questions_asked = bg.get("questions_asked", 0)
            context.background_progress.completed = bg.get("completed", False)
        if "technical" in sp:
            tech = sp["technical"]
            context.technical_progress.questions_completed = tech.get("questions_completed", 0)
            context.technical_progress.questions_skipped = tech.get("questions_skipped", 0)

        # Restore current question
        question_snapshot = checkpoint.get("current_question_snapshot")
        if question_snapshot:
            context.current_question = Question(**question_snapshot)
            
        # Restore question records
        records_snapshot = checkpoint.get("question_records", [])
        if records_snapshot:
            context.question_records = [QuestionRecord(**r) for r in records_snapshot]

        # Restore evaluation signals
        from app.interview.models import EvaluationSignal
        evals_snapshot = checkpoint.get("evaluation_signals", [])
        if evals_snapshot:
            context.evaluation_signals = [EvaluationSignal(**e) for e in evals_snapshot]

        # Log reconnect event
        await persistence.update_status(session_id, "IN_PROGRESS")
        await persistence.save_event(
            session_id=session_id,
            sequence=context.event_sequence + 1,
            event_type="SESSION_RECONNECTED",
            phase=context.current_phase.value,
        )
        context.event_sequence += 1

    else:
        # Fresh start
        context = InterviewRuntimeContext(
            session_id=session_id,
            candidate_id=str(session_data["candidate_profile_id"]),
            role=session_data["role"],
            confirmed_level=session_data["level"],
            language=session_data["language"],
            job_description=session_data.get("job_description"),
            candidate_profile=session_data.get("candidate_profile", {}),
            time_remaining_seconds=duration_minutes * 60,
        )

        # Transition to IN_PROGRESS
        await persistence.update_status(session_id, "IN_PROGRESS")
        await persistence.save_event(
            session_id=session_id,
            sequence=1,
            event_type="SESSION_STARTED",
            phase="CREATED",
        )
        context.event_sequence = 1

    # ─── Initialize Controller ─────────────────────────────────────────
    llm = GroqProvider()
    controller = InterviewController(llm, persistence, context)

    # ─── Initialize Voice Plugins ──────────────────────────────────────
    language = session_data.get("language", "en")
    stt_plugin = groq.STT(model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"))

    if language == "ar":
        tts_model = os.getenv("GROQ_TTS_ARABIC_MODEL", "canopylabs/orpheus-arabic-saudi")
        tts_voice = "fahad"
        logger.info("Interview language: ar")
        logger.info("TTS provider: groq")
        logger.info(f"TTS model: {tts_model}")
        logger.info(f"TTS voice: {tts_voice}")
        tts_plugin = groq.TTS(model=tts_model, voice=tts_voice)
        tts_plugin.provider_name = "Groq"
        tts_plugin.model_name = tts_model
    else:
        tts_model = os.getenv("GROQ_TTS_ENGLISH_MODEL", "canopylabs/orpheus-v1-english")
        logger.info("Interview language: en")
        logger.info("TTS provider: groq")
        logger.info(f"TTS model: {tts_model}")
        tts_plugin = groq.TTS(model=tts_model)
        tts_plugin.provider_name = "Groq"
        tts_plugin.model_name = tts_model

    vad_plugin = silero.VAD.load()

    # ─── Create Voice Adapter ──────────────────────────────────────────
    adapter = VoiceInterviewAdapter(
        controller, stt_plugin, tts_plugin, vad_plugin, ctx.room, persistence
    )

    # Start the adapter (which also kicks off the interview)
    await adapter.start(resume=is_resuming)

    logger.info("Agent running. Waiting for room lifecycle events...")

    # ─── Lifecycle Management ──────────────────────────────────────────
    shutdown_event = asyncio.Event()

    @ctx.room.on("disconnected")
    def on_room_disconnected(*args, **kwargs):
        logger.info("Room disconnected.")
        shutdown_event.set()

    # Lease renewal task
    async def renew_lease_loop():
        while not shutdown_event.is_set():
            await asyncio.sleep(LEASE_RENEWAL_INTERVAL)
            if not shutdown_event.is_set():
                await persistence.renew_lease(session_id)

    lease_task = asyncio.create_task(renew_lease_loop())

    # Wait for room to disconnect
    await shutdown_event.wait()

    # ─── Cleanup ───────────────────────────────────────────────────────
    lease_task.cancel()

    # If the interview isn't completed yet, mark as DISCONNECTED and save checkpoint
    if context.current_phase not in (InterviewPhase.COMPLETED,):
        logger.info("Interview not completed — saving disconnect checkpoint.")
        await persistence.save_event(
            session_id=session_id,
            sequence=context.event_sequence + 1,
            event_type="SESSION_DISCONNECTED",
            phase=context.current_phase.value,
        )
        context.event_sequence += 1
        await persistence.save_checkpoint(context)
        await persistence.update_status(session_id, "DISCONNECTED")
    else:
        logger.info("Interview completed.")
        await persistence.save_completion(context)

    await persistence.close()
    logger.info("Agent shutdown complete.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
