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
from livekit.plugins import groq, silero, azure

from agent.llm.groq_provider import GroqProvider
from agent.interview.persistence import APIPersistence
from agent.interview.models import (
    InterviewRuntimeContext, InterviewPhase, InterviewPlan,
    SectionProgress, SectionLimits, Message,
    Question, QuestionRecord, OrderedSectionProgress,
    AssessmentCriterionData,
)
from agent.interview.controller import InterviewController
from agent.interview.voice_adapter import VoiceInterviewAdapter
from agent.interview.groq_key_rotator import GroqKeyRotator
from agent.interview.question_generator import generate_custom_question, build_contextual_fallback_question

# RT-B0: default logging.basicConfig() has no timestamp at all (its default
# format is just "%(levelname)s:%(name)s:%(message)s"), making it impossible
# to compute any latency delta from logs alone -- the exact gap RT-A found.
# Python's default asctime already includes milliseconds when no datefmt is
# given, so adding %(asctime)s here is sufficient for latency work.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("agent")

# Agent lease renewal interval (seconds)
LEASE_RENEWAL_INTERVAL = 300  # 5 minutes


def _load_env():
    """Load the repository configuration explicitly. Override inherited
    process variables so restarting the worker actually picks up a rotated
    API key.

    Phase 7E: moved out of module level and into entrypoint() (called as its
    first line, below) so importing agent.main for its pure helpers (e.g.
    build_core_sections) no longer side-effects the whole process's
    environment. That import-time override(...) call was silently leaking
    GROQ_API_KEY into pytest's single shared process whenever anything
    imported this module, changing what unrelated tests observed in
    os.environ. Same override semantics as before (repo .env wins over
    inherited vars, agent .env fills gaps only) — just deferred until
    something that actually needs it runs, instead of at import time."""
    repo_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    agent_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv(repo_env, override=True)
    load_dotenv(agent_env, override=False)


def build_core_sections(session_data: dict) -> dict:
    """Phase 7D/7E: maps /load's `sections` payload into
    {section_type: OrderedSectionProgress}. Always sourced fresh from /load —
    core questions are immutable per session (HR-approved, never skipped/
    replaced/reordered live), so re-reading them on every connect or
    reconnect is safe. Returns {} for legacy (InterviewConfiguration-sourced)
    sessions, where session_data has no "sections" key or an empty list.

    Extracted from entrypoint() in Phase 7E specifically so this mapping has
    direct unit-test coverage — entrypoint() itself needs a live LiveKit
    JobContext and can't be exercised in a normal test."""
    built_sections = {}
    for raw_section in session_data.get("sections") or []:
        questions = []
        for q in sorted(raw_section["questions"], key=lambda item: item["order_index"]):
            config = q.get("config") or {}
            questions.append(Question(
                id=q["id"],
                title=q["title"],
                problem_statement=q["text"],
                difficulty=session_data.get("level") or "mid",
                competency=q.get("competency"),
                expected_concepts=[], follow_up_topics=[],
                # Phase 9C: CODING's hints (schema-added in 9A, `config.hints`)
                # feed the ported _provide_hint()/REQUEST_HINT mechanism via
                # this same Question.hints field the legacy single-question
                # flow already reads. A no-op for VERBAL/MCQ, whose config
                # never carries a "hints" key.
                hints=config.get("hints") or [],
                time_budget_minutes=0,
                # Part 1 (rebrand work, 2026-08-26): CODING questions are
                # genuinely coding_required; was hardcoded False for every
                # type here, which (combined with generate_ui_state() only
                # reading ctx.current_question, now fixed) left the
                # frontend never seeing a real CODING editor for the
                # ordered flow. supported_languages copies directly (clean
                # List[str] match with CodingConfig). starter_code/
                # constraints are deliberately NOT coerced into the legacy
                # Dict[str,str]/List[str] typed fields below (shape
                # mismatch with CodingConfig.starter_code: str /
                # .constraints: str) — they stay at their empty defaults;
                # `config` (already carried through unmodified) is the real
                # source of truth Part 3's frontend reads from instead. A
                # no-op for VERBAL/MCQ, matching the `hints=` line above.
                coding_required=(raw_section["section_type"] == "CODING"),
                supported_languages=(
                    config.get("supported_languages") or []
                    if raw_section["section_type"] == "CODING" else []
                ),
                config=config,
                # Phase 9D: HR-authored grading rubric, shape varies by
                # section_type -- see Question.eval_criteria's docstring.
                eval_criteria=q.get("eval_criteria"),
                source="HR_APPROVED",
            ))
        built_sections[raw_section["section_type"]] = OrderedSectionProgress(
            section_type=raw_section["section_type"],
            questions=questions,
            # WR-A: defensive .get, not direct indexing — older /load
            # payloads (pre-WR-A) and existing test fixtures won't carry
            # this key at all, and it must not crash for them.
            time_budget_minutes=raw_section.get("time_budget_minutes"),
        )
    return built_sections


def build_criteria(session_data: dict) -> list:
    """Phase 8C: maps /load's `criteria` payload into a list of
    AssessmentCriterionData. Always sourced fresh from /load, same rationale
    as build_core_sections above. Returns [] for a legacy session or a job
    with nothing resolved -- session_data has no "criteria" key or an empty
    list in either case."""
    return [
        AssessmentCriterionData(
            key=c["key"],
            label=c["label"],
            kind=c["kind"],
            guidance_text=c.get("guidance_text"),
            section_id=c.get("section_id"),
        )
        for c in (session_data.get("criteria") or [])
    ]


async def entrypoint(ctx: JobContext):
    _load_env()
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

    # Phase 7D/7E: B2B ordered core-question sections (see build_core_sections
    # docstring). Only the mutable pointer (current_index/completed) is
    # restored from the checkpoint below, on the resume path.
    built_sections = build_core_sections(session_data)
    built_criteria = build_criteria(session_data)

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
        
        checkpoint_technical = (checkpoint.get("section_progress") or {}).get("technical", {})
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
            technical_question_ids_seen=checkpoint.get("technical_question_ids_seen", checkpoint_technical.get("technical_question_ids_seen", [])),
            technical_question_ids_skipped=checkpoint.get("technical_question_ids_skipped", checkpoint_technical.get("technical_question_ids_skipped", [])),
            technical_question_id_submitted=checkpoint.get("technical_question_id_submitted", checkpoint_technical.get("technical_question_id_submitted")),
            technical_submission=checkpoint.get("technical_submission", checkpoint_technical.get("technical_submission", {})),
            sections=built_sections,
            criteria=built_criteria,
        )

        # Restore the ordered core-question pointer (Phase 7D) — the question
        # list itself is always the fresh one built from /load above.
        verbal_checkpoint = (checkpoint.get("section_progress") or {}).get("verbal")
        if verbal_checkpoint and "VERBAL" in context.sections:
            context.sections["VERBAL"].current_index = verbal_checkpoint.get("current_index", 0)
            context.sections["VERBAL"].completed = verbal_checkpoint.get("completed", False)

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
            logger.info(
                "[TECH-GEN] Resumed existing question id=%s title=%s source=%s",
                context.current_question.id,
                context.current_question.title,
                context.current_question.source,
            )
            
        # Restore question records
        records_snapshot = checkpoint.get("question_records", [])
        if records_snapshot:
            context.question_records = [QuestionRecord(**r) for r in records_snapshot]

        # Restore evaluation signals
        from agent.interview.models import EvaluationSignal
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
            sections=built_sections,
            criteria=built_criteria,
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
    async def generate_for_this_session():
        logger.info(
            "[TECH-GEN] Interview ID=%s Candidate ID=%s Role=%s Seniority=%s CV available=%s CV context length=%d Job description available=%s",
            context.session_id, context.candidate_id, context.role, context.confirmed_level,
            bool(context.candidate_profile), len(str(context.candidate_profile or {})),
            bool(context.job_description and context.job_description.strip()),
        )
        logger.info("[TECH-GEN] Generator invoked: source=LLM_GENERATED")
        return await generate_custom_question(
            llm=llm,
            role=context.role,
            level=context.confirmed_level,
            language=context.language,
            job_description=context.job_description,
            candidate_profile=context.candidate_profile,
            previous_questions=controller.previous_question_summaries(),
        )
    controller.set_question_generator(generate_for_this_session)
    controller.set_question_fallback(lambda: build_contextual_fallback_question(
        role=context.role,
        level=context.confirmed_level,
        language=context.language,
        job_description=context.job_description,
        candidate_profile=context.candidate_profile,
    ))
    if is_resuming:
        # A checkpoint stores remaining budget, not the process-local clock.
        controller.resume_timer()
    if not context.current_question and context.current_phase not in (InterviewPhase.CLOSING, InterviewPhase.COMPLETED):
        try:
            custom_question = await generate_for_this_session()
            controller.set_custom_question(custom_question)
            logger.info("[TECH-GEN] Generator result: GENERATED id=%s title=%s", custom_question.id, custom_question.title)
        except Exception as error:
            logger.exception("[TECH-GEN] Personalized generation FAILED: %s", error)
            emergency = build_contextual_fallback_question(
                role=context.role, level=context.confirmed_level, language=context.language,
                job_description=context.job_description, candidate_profile=context.candidate_profile,
            )
            controller.set_custom_question(emergency)
            logger.warning("[TECH-GEN] FALLBACK=CONTEXTUAL_FALLBACK id=%s title=%s reason=%s", emergency.id, emergency.title, error)

    # ─── Initialize Voice Plugins ──────────────────────────────────────
    language = session_data.get("language", "en")
    stt_plugin = groq.STT(model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"))

    # Audit fix (2026-08-27): Groq's TTS free tier is a hard 3.6K-tokens/day
    # (TPD) ceiling per model (confirmed live against the real account — see
    # docs/CURRENT_DECISIONS.md), not a short burst that retrying can outlast
    # -- one real test day exhausted it outright, and it would exhaust
    # again within a single real candidate interview once this deploys for
    # actual user testing. Azure Speech becomes the default TTS provider;
    # the Groq path below is deliberately kept fully intact, not deleted --
    # this is a config-level swap (TTS_PROVIDER=groq reverts it instantly),
    # not a rip-and-replace. Confirmed via direct plugin-source inspection
    # (both TTS classes share the exact same livekit.agents.tts.TTS /
    # ChunkedStream / AudioEmitter base machinery Groq's plugin uses) that
    # this doesn't disturb RT-B0's metrics_collected listeners or RT-B1's
    # AudioSource.clear_queue() interruption fix -- both operate on that
    # shared base layer, not any Groq-specific code.
    tts_provider = os.getenv("TTS_PROVIDER", "azure").lower()

    if language == "ar":
        if tts_provider == "azure":
            # ar-SA has exactly two neural voices in Azure's catalog:
            # ar-SA-ZariyahNeural (female) and ar-SA-HamedNeural (male).
            # Hamed chosen for consistency with InterviewerCharacter.tsx's
            # existing male-presenting avatar (thobe/ghutra) already shown
            # to every candidate throughout the interview.
            tts_voice = os.getenv("AZURE_TTS_ARABIC_VOICE", "ar-SA-HamedNeural")
            logger.info("Interview language: ar")
            logger.info("TTS provider: azure")
            logger.info(f"TTS voice: {tts_voice}")
            tts_plugin = azure.TTS(voice=tts_voice, language="ar-SA")
            tts_plugin.provider_name = "Azure"
            tts_plugin.model_name = tts_voice
        else:
            # Audit fix (2026-08-27, follow-up): Groq's TTS 429 is a
            # per-KEY daily quota (confirmed live) — a different key has
            # its own independent quota, so multi-key rotation (7 real
            # keys provisioned for prototype user testing) replaces
            # waiting-and-retrying the same exhausted key. One rotator per
            # language — independent models, independent quotas, no
            # reason a rotation on one should affect the other's starting
            # key. See docs/tts-provider-switching.md.
            tts_model = os.getenv("GROQ_TTS_ARABIC_MODEL", "canopylabs/orpheus-arabic-saudi")
            tts_voice = "abdullah"
            key_rotator = GroqKeyRotator("ar", model=tts_model, voice=tts_voice)
            logger.info("Interview language: ar")
            logger.info("TTS provider: groq")
            logger.info(f"TTS model: {tts_model}")
            logger.info(f"TTS voice: {tts_voice}")
            logger.info(f"Groq key rotator: key {key_rotator.current_position}/{key_rotator.total_keys}")
            tts_plugin = key_rotator.rebuild_plugin()
    else:
        if tts_provider == "azure":
            # en-US-AvaNeural: one of Azure's newer voices explicitly
            # designed/tuned for conversational, casual dialogue (not just
            # formal narration) -- a better fit for a spoken interview than
            # older general-purpose voices, and a stable, generally
            # available (non-preview) voice rather than the newer
            # Dragon-HD-preview tier, which isn't guaranteed available on
            # every region/subscription.
            tts_voice = os.getenv("AZURE_TTS_ENGLISH_VOICE", "en-US-AvaNeural")
            logger.info("Interview language: en")
            logger.info("TTS provider: azure")
            logger.info(f"TTS voice: {tts_voice}")
            tts_plugin = azure.TTS(voice=tts_voice, language="en-US")
            tts_plugin.provider_name = "Azure"
            tts_plugin.model_name = tts_voice
        else:
            # See the matching Arabic branch above for the full multi-key
            # rotation rationale.
            tts_model = os.getenv("GROQ_TTS_ENGLISH_MODEL", "canopylabs/orpheus-v1-english")
            tts_voice = os.getenv("GROQ_TTS_ENGLISH_VOICE", "troy")
            key_rotator = GroqKeyRotator("en", model=tts_model, voice=tts_voice)
            logger.info("Interview language: en")
            logger.info("TTS provider: groq")
            logger.info(f"TTS model: {tts_model}")
            logger.info(f"TTS voice: {tts_voice}")
            logger.info(f"Groq key rotator: key {key_rotator.current_position}/{key_rotator.total_keys}")
            tts_plugin = key_rotator.rebuild_plugin()

    try:
        vad_min_silence = max(
            0.55, float(os.getenv("VAD_MIN_SILENCE_DURATION_SECONDS", "0.85"))
        )
    except ValueError:
        vad_min_silence = 0.85
    logger.info(
        "Voice endpointing: Silero min_silence_duration=%.2fs, candidate endpoint coalescing enabled",
        vad_min_silence,
    )
    vad_plugin = silero.VAD.load(min_silence_duration=vad_min_silence)

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
        try:
            await controller.generate_final_evaluation()
            await persistence.save_completion(context)
        except Exception:
            # Completion must not be lost because room teardown raced a
            # final persistence request. The next recovery path can retry.
            logger.exception("Failed to persist completed interview during shutdown")

        # Phase 8C: same last-resort retry for the normalized Evaluation/
        # Score submission, independent of the block above -- the backend
        # endpoint upserts on session_id, so retrying here even when the
        # mid-session attempt already succeeded is safe, not just tolerated.
        try:
            await persistence.submit_evaluation(context)
        except Exception:
            logger.exception("[EVALUATION_SUBMIT] failed_to_persist_completed_interview_during_shutdown")

    await persistence.close()
    logger.info("Agent shutdown complete.")


if __name__ == "__main__":
    _load_env()
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

