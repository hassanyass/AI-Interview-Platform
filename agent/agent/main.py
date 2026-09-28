"""
LiveKit Agent entrypoint — Phase 5.

Loads real session data from the backend, acquires agent lease,
initializes the InterviewController with real context, and manages
the full lifecycle including disconnect/reconnect and completion.
"""
import asyncio
import hashlib
import logging
import sys
import uuid as uuid_mod

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli

from agent.config import get_settings, load_env_files, reset_settings
from agent.logging_setup import bind_session, configure_worker_logging
from agent.interview.persistence import APIPersistence, LeaseState
from agent.runtime.bootstrap import build_context
from agent.runtime.teardown import finalize_session, mark_disconnected_after_failure
from agent.interview.models import (
    InterviewPhase, Question, OrderedSectionProgress,
    AssessmentCriterionData,
)
from agent.interview.controller import InterviewController
from agent.interview.voice_adapter import VoiceInterviewAdapter
from agent.providers.factory import build_llm, build_stt, build_tts, prewarm, vad_for
from agent.interview.question_generator import generate_custom_question, build_contextual_fallback_question
from agent.interview.background_generator import generate_background_questions

# H3: logging is configured by agent.logging_setup.configure_worker_logging,
# called from prewarm()/entrypoint() AFTER livekit-agents installed its own
# root handler -- one line per event, one format, session context on every
# line. (basicConfig here used to add a second handler: every line twice.)
logger = logging.getLogger("agent")

def _load_env():
    """Load the repository configuration explicitly (repo .env wins over
    inherited process variables so restarting the worker picks up a rotated
    key; agent/.env fills gaps). Lives in agent.config since H1-C; kept here
    by name because it is called at entrypoint start, not import time
    (Phase 7E: an import-time load leaked GROQ_API_KEY into pytest's shared
    process)."""
    load_env_files()


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
            # Background subsection: HR's per-section settings, forwarded by
            # /load's SectionPayload. Same defensive .get -- absent on every
            # pre-existing payload and fixture, which must keep meaning "off".
            include_background=bool(raw_section.get("include_background", False)),
            background_question_count=raw_section.get("background_question_count"),
            background_time_budget_minutes=raw_section.get("background_time_budget_minutes"),
        )
    return built_sections


def attach_background_questions(built_sections: dict, background_questions: list) -> int:
    """Background subsection (docs/verbal-background-subsection-plan.md §1):
    prepend the generated, source="BACKGROUND" questions to the VERBAL
    section's ordered list so they are walked first, by the same machinery
    as the HR-approved ones. Idempotent: a second call with the list already
    in place (or an empty list) changes nothing. Returns how many were
    attached. Pure, so it has direct unit-test coverage like
    build_core_sections above."""
    verbal = built_sections.get("VERBAL")
    if verbal is None or not background_questions:
        return 0
    if any(q.source == "BACKGROUND" for q in verbal.questions):
        return 0
    verbal.questions = list(background_questions) + list(verbal.questions)
    return len(background_questions)


def restore_background_questions(checkpoint: dict) -> list:
    """Resume path: the background questions a session already generated
    live in its checkpoint (section_progress.verbal.background_questions,
    written by APIPersistence.save_checkpoint). Rebuilding them from there --
    instead of generating again -- keeps the restored current_index and the
    question_records pointing at the very same questions. [] when the
    checkpoint predates the feature or the session had none."""
    verbal = ((checkpoint or {}).get("section_progress") or {}).get("verbal") or {}
    restored = []
    for raw in verbal.get("background_questions") or []:
        try:
            restored.append(Question(**raw))
        except Exception as error:  # noqa: BLE001 -- a bad snapshot must not kill the resume
            logger.warning("[BG-GEN] Ignoring unreadable background question snapshot: %s", error)
    return restored


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


def _setup_logging(settings) -> None:
    devmode = "dev" in sys.argv[1:2]
    configure_worker_logging(
        log_format=settings.log_format_for(devmode), level=settings.LOG_LEVEL, environment=settings.ENVIRONMENT,
    )


async def entrypoint(ctx: JobContext):
    _load_env()
    # prewarm() may have cached settings from the inherited environment;
    # re-read after the .env reload so a rotated key is picked up per job.
    reset_settings()
    settings = get_settings()
    _setup_logging(settings)
    bind_session(None, job_id=getattr(getattr(ctx, "job", None), "id", None))
    logger.info("Initializing Agent (Phase 5)...")

    # A fingerprint makes key precedence diagnosable without logging secrets.
    groq_key = settings.GROQ_API_KEY
    logger.info(
        "Groq credential loaded: present=%s length=%d fingerprint=%s",
        bool(groq_key),
        len(groq_key),
        hashlib.sha256(groq_key.encode()).hexdigest()[:10] if groq_key else "missing",
    )

    # ─── Validate Environment ──────────────────────────────────────────
    # Everything the job needs, checked BEFORE the session is touched --
    # including LLM_MODEL and the Azure credentials, which used to fail only
    # after the status had already been moved to IN_PROGRESS (H1-C).
    missing = settings.missing_for_job()
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
    # H3: from here every log line of this job carries the session and agent ids.
    bind_session(session_id, agent_id=agent_id)
    backend_url = settings.BACKEND_INTERNAL_URL
    agent_secret = settings.AGENT_API_SECRET

    persistence = APIPersistence(
        backend_url=backend_url,
        agent_secret=agent_secret,
        agent_id=agent_id,
        timeout_seconds=settings.BACKEND_TIMEOUT_SECONDS,
        retry_attempts=settings.BACKEND_RETRY_ATTEMPTS,
    )

    # ─── Load session from backend ─────────────────────────────────────
    session_data = await persistence.load_session(session_id)
    if not session_data:
        logger.error(f"Could not load session {session_id}. Exiting.")
        await persistence.close()
        ctx.shutdown(reason="session_not_loaded")
        return

    logger.info(f"Loaded session: role={session_data.get('role')}, level={session_data.get('level')}, status={session_data.get('status')}")

    # H2-D: from build_context onward the session is IN_PROGRESS and this
    # worker owes the backend a terminal status. Everything below runs
    # under one try/except/finally so a failure anywhere leaves the session
    # DISCONNECTED (sweep-finalizable), never stranded IN_PROGRESS.
    slots = _SessionSlots()
    shutdown_reason = "room_disconnected"
    try:
        await _run_session(ctx, settings, persistence, session_data, session_id, slots)
    except Exception:
        logger.exception("Agent session %s failed", session_id)
        if slots.context is not None and not slots.lease_lost:
            await mark_disconnected_after_failure(persistence, slots.context, session_id)
        shutdown_reason = "agent_failure"
    finally:
        if slots.lease_task is not None:
            slots.lease_task.cancel()
        if slots.adapter is not None:
            try:
                await slots.adapter.aclose()
            except Exception:  # noqa: BLE001 -- teardown of the audio pipeline is best effort
                logger.exception("Voice adapter close failed")
        if slots.lease_lost:
            shutdown_reason = "lease_lost"
        elif slots.outcome:
            shutdown_reason = slots.outcome
        await persistence.close()
        logger.info("Agent shutdown complete (%s).", shutdown_reason)
        ctx.shutdown(reason=shutdown_reason)


class _SessionSlots:
    """What the failure/teardown paths need from a session that may have
    stopped at any point (filled in by _run_session as it goes)."""

    def __init__(self) -> None:
        self.context = None
        self.controller = None
        self.adapter = None
        self.lease_task = None
        self.lease_lost = False
        self.outcome = None


async def _run_session(ctx: JobContext, settings, persistence, session_data: dict, session_id: str, slots: _SessionSlots) -> None:
    context, is_resuming = await build_context(session_data, persistence, session_id)
    slots.context = context

    # ─── Initialize Controller ─────────────────────────────────────────
    llm = build_llm(settings)

    # ─── Background subsection: generate once, on a fresh start ─────────
    # docs/verbal-background-subsection-plan.md §2 "Agent (bootstrap)". Only
    # when HR switched it on for this VERBAL section AND the CV profile has
    # something to ground on; generation failure or an empty result simply
    # means no background subsection -- the interview never waits on it
    # beyond this one bounded call, and never blocks on it.
    verbal_section = context.sections.get("VERBAL")
    if (
        not is_resuming
        and verbal_section is not None
        and verbal_section.include_background
        and not verbal_section.background_questions
    ):
        generated = await generate_background_questions(
            llm=llm,
            role=context.role,
            level=context.confirmed_level,
            language=context.language,
            job_description=context.job_description,
            candidate_profile=context.candidate_profile,
            count=verbal_section.background_question_count,
        )
        attached = attach_background_questions(context.sections, generated)
        logger.info(
            "[BG-GEN] Session %s: include_background=%s attached=%d verbal_total=%d",
            context.session_id, verbal_section.include_background, attached, verbal_section.total_questions,
        )

    controller = InterviewController(llm, persistence, context)
    slots.controller = controller
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
    # Provider construction (and the per-language/per-provider decisions
    # behind it) lives in agent.providers.factory since H1-C; VAD comes
    # prewarmed from the job process (WorkerOptions.prewarm_fnc).
    language = session_data.get("language", "en")
    stt_plugin = build_stt(language, settings)
    tts_plugin, _key_rotator = build_tts(language, settings)
    vad_plugin = vad_for(ctx.proc)

    # ─── Create Voice Adapter ──────────────────────────────────────────
    adapter = VoiceInterviewAdapter(
        controller, stt_plugin, tts_plugin, vad_plugin, ctx.room, persistence
    )
    slots.adapter = adapter

    # Start the adapter (which also kicks off the interview)
    await adapter.start(resume=is_resuming)

    logger.info("Agent running. Waiting for room lifecycle events...")

    # ─── Lifecycle Management ──────────────────────────────────────────
    shutdown_event = asyncio.Event()

    @ctx.room.on("disconnected")
    def on_room_disconnected(*args, **kwargs):
        logger.info("Room disconnected.")
        shutdown_event.set()

    # Lease renewal task. H2-D: a 409 means another worker now owns this
    # session -> stop driving it (leave the room; no DISCONNECTED write, the
    # other worker is responsible now). Repeated transport errors past the
    # lease window mean the same in practice.
    async def renew_lease_loop():
        errors = 0
        while not shutdown_event.is_set():
            await asyncio.sleep(settings.LEASE_RENEWAL_INTERVAL_SECONDS)
            if shutdown_event.is_set():
                return
            state = await persistence.renew_lease(session_id)
            if state == LeaseState.RENEWED:
                errors = 0
                continue
            if state == LeaseState.LOST:
                logger.error("Lease for session %s lost to another agent; leaving the room", session_id)
                slots.lease_lost = True
                shutdown_event.set()
                return
            errors += 1
            if errors >= settings.LEASE_ERROR_SHUTDOWN_AFTER:
                logger.error("Lease renewal failed %d times in a row for %s; assuming the lease expired", errors, session_id)
                slots.lease_lost = True
                shutdown_event.set()
                return

    lease_task = asyncio.create_task(renew_lease_loop())
    slots.lease_task = lease_task

    # Wait for room to disconnect (or the lease to be lost)
    await shutdown_event.wait()

    if slots.lease_lost:
        # Another worker owns the session now; persisting anything here
        # would fight it. Just stop.
        return
    slots.outcome = await finalize_session(persistence, controller, context, session_id)


def worker_options() -> WorkerOptions:
    """WorkerOptions from settings: the VAD model is loaded once per job
    process (prewarm) instead of per interview; agent_name / memory limits
    are opt-in knobs that default to the SDK's own behaviour."""
    s = get_settings()
    kwargs = dict(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=s.AGENT_NAME)
    if s.JOB_MEMORY_LIMIT_MB > 0:
        kwargs["job_memory_limit_mb"] = s.JOB_MEMORY_LIMIT_MB
    if s.JOB_MEMORY_WARN_MB > 0:
        kwargs["job_memory_warn_mb"] = s.JOB_MEMORY_WARN_MB
    return WorkerOptions(**kwargs)


if __name__ == "__main__":
    _load_env()
    cli.run_app(worker_options())
