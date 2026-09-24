"""Backend configuration — the single place every tunable, credential and
policy value enters the process.

Rules (docs/production-hardening-plan.md §1, H1-A):
- Every value that is not a protocol constant is a field here, with a
  default equal to the behaviour the code had before it was lifted, and a
  one-line docstring saying what it controls.
- Environment variables (and the .env file) are the only source. The
  ``settings`` singleton is imported everywhere; it is deliberately left
  mutable because tests assign to it.
- Outside ``local``/``test`` the process refuses to boot with the shipped
  ``SECRET_KEY`` or without the secrets the deployment cannot work without
  (see ``_refuse_unsafe_production_config``).

New keys need a default here, a line in ``backend/.env.example`` and one in
the root ``.env.example``.
"""
from __future__ import annotations

import json
from typing import List, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The default that ships in this file. Anything outside local/test must
# override it — the validator below checks for exactly this string.
_DEFAULT_SECRET_KEY = "local_guest_jwt_secret_key_change_me_in_prod"
_MIN_SECRET_KEY_LENGTH = 32

# Model fallbacks. Before H1-A the call sites did `settings.GROQ_MODEL or
# "<literal>"`; an empty GROQ_MODEL= in .env therefore meant "use the
# default", and it still does (see _empty_model_means_default).
_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_GROQ_EXTRACTION_MODEL = "llama-3.1-8b-instant"


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────────────────────────
    ENVIRONMENT: Literal["local", "test", "staging", "production"] = "local"
    """Deployment environment. Anything but local/test enables the boot-time safety checks."""
    APP_VERSION: str = "0.1.0"
    """Reported by /health and /version."""
    LOG_FORMAT: Literal["json", "text", "auto"] = "auto"
    """auto = text when ENVIRONMENT is local/test, json otherwise. One line per event, request/session ids on every line (core/logging.py)."""
    LOG_LEVEL: str = "INFO"
    METRICS_ENABLED: bool = True
    """Expose GET /metrics (Prometheus text). Protect it at the network layer; it is unauthenticated."""
    BACKEND_CORS_ORIGINS: str = (
        '["http://localhost:5173", "http://127.0.0.1:5173", '
        '"http://localhost:5174", "http://127.0.0.1:5174"]'
    )
    """JSON list of allowed browser origins."""

    # ── Secrets shared with other components ───────────────────────────────
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    """HS256 key for guest (candidate) JWTs. Must be overridden outside local/test."""
    AGENT_API_SECRET: str = ""
    """Shared secret the agent worker sends as X-Agent-Secret on /internal/*."""

    # ── Supabase (Auth + Storage) ──────────────────────────────────────────
    SUPABASE_URL: str
    """Project URL; also the base for the Storage REST API used for CVs."""
    SUPABASE_SECRET_KEY: str
    """Service-role key used server-side for Storage. Never sent to the frontend."""
    SUPABASE_JWKS_URL: str
    """JWKS endpoint used to verify Supabase-issued user JWTs."""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    """Browser key. Not used by the backend (the frontend has its own VITE_ copy); kept optional so shared .env files validate."""
    SUPABASE_JWT_ALGORITHMS: List[str] = ["ES256", "RS256"]
    """Signature algorithms accepted for Supabase user JWTs."""
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    """`aud` claim Supabase puts on signed-in users' tokens."""
    SUPABASE_JWT_ISSUER: str = ""
    """Expected `iss`. Empty = derive it from SUPABASE_URL (`<url>/auth/v1`), which is
    what GoTrue puts on its tokens; set explicitly only for a non-standard deployment."""
    SUPABASE_STORAGE_TIMEOUT_SECONDS: float = 30.0
    """HTTP timeout for CV upload/download against Supabase Storage."""
    STORAGE_RETRY_ATTEMPTS: int = 2
    """Retries on transport errors (connection reset, timeout) for Supabase Storage calls."""

    # ── Guest (candidate) JWTs ─────────────────────────────────────────────
    GUEST_JWT_ALGORITHM: str = "HS256"
    """Algorithm for guest tokens minted by guest_jwt_service."""
    GUEST_JWT_TTL_HOURS: int = 24
    """Lifetime of a guest token issued at public registration / invitation redemption."""
    GUEST_JWT_ISSUER: str = "himma-guest"
    """`iss` stamped on guest tokens this backend mints. Verified when present; tokens
    minted before H5-A carry none, so they stay valid until they expire."""

    # ── Data retention (services/tasks/handlers.py: purge) ─────────────────
    # The mechanism is built and deliberately switched off: how long
    # recordings, transcripts and CVs are kept, and who may delete them, is
    # U1 in docs/production-hardening-plan.md and belongs in
    # CURRENT_DECISIONS.md before anything starts erasing candidate data on
    # a timer. Turning this on without setting the policy first is the
    # mistake it is guarding against.
    DATA_PURGE_ENABLED: bool = False
    DATA_PURGE_AFTER_DAYS: int = 0
    """Age threshold for the purge. 0 means unset; the task refuses to run without it."""

    # ── Rate limiting (core/ratelimit.py) ──────────────────────────────────
    # "<count>/<second|minute|hour|day>". Parsed on every request, so a bad
    # value fails that route loudly instead of silently disabling a limit.
    # Anonymous routes are keyed by IP and everyone behind one NAT -- a
    # booth, an office -- shares it, which is why those two are generous.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_APPLY_PREVIEW: str = "120/minute"
    """GET /apply/{token}: a cheap read, keyed by IP."""
    RATE_LIMIT_PUBLIC_REGISTER: str = "20/minute"
    """POST /apply/{token}/register: keyed by IP, and each call creates a profile,
    an application, an interview session and a guest token."""
    RATE_LIMIT_INVITATION_REDEEM: str = "20/minute"
    """POST /invitations/{token}/redeem: keyed by the signed-in subject."""
    RATE_LIMIT_ROOM_TOKEN: str = "30/minute"
    """POST /livekit/token: keyed by the subject. Generous -- a reconnecting
    candidate legitimately asks again -- but bounded, because each call can
    schedule a recording."""

    # ── Identity linking (api/deps.py) ─────────────────────────────────────
    IDENTITY_AUTOLINK: Literal["verified_only", "always", "never"] = "verified_only"
    """What happens when a Supabase identity has no profile of its own but an existing
    profile carries the same email -- typically a candidate who applied through a public
    link (guest) and later signed in.

    `verified_only` (default): link only when the token proves the address was verified.
    An unverified or unprovable email is refused, because linking hands over that
    profile's sessions and results.
    `always`: the pre-H5-A behaviour, now logged. Only for a deployment that has
    confirmed its identity provider verifies addresses before issuing tokens.
    `never`: no linking at all; the Supabase identity gets its own empty profile."""

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str
    """asyncpg DSN. Tests substitute TEST_DATABASE_URL via conftest.py before import."""
    DB_POOL_SIZE: int = 5
    """Persistent connections per process (SQLAlchemy default)."""
    DB_MAX_OVERFLOW: int = 10
    """Extra connections allowed under burst, closed when idle (SQLAlchemy default)."""
    DB_POOL_RECYCLE_SECONDS: int = 1800
    """Recycle a connection after this age; keeps poolers/NAT from killing idle ones."""
    DB_POOL_TIMEOUT_SECONDS: int = 30
    """How long a request waits for a free connection before failing."""
    RUN_MIGRATIONS_ON_START: bool = False
    """Container entrypoint runs `alembic upgrade head` before serving. Off by default: N replicas
    would race on the same migration; run the `migrate` one-shot instead. Turn on for a single-instance deploy."""

    # ── Provider selectors (backend/backend/providers/factory.py) ──────────
    # One Literal per port; adding a vendor adds a value here and a branch there.
    REALTIME_PROVIDER: Literal["livekit"] = "livekit"
    RECORDINGS_STORAGE_PROVIDER: Literal["s3"] = "s3"
    """S3-compatible store the recordings land in (Cloudflare R2 today)."""
    RESUMES_STORAGE_PROVIDER: Literal["supabase"] = "supabase"
    NOTIFICATIONS_PROVIDER: Literal["console", "email"] = "console"
    """console = log the invitation (today's behaviour); email = render it and hand it to EMAIL_PROVIDER."""
    EMAIL_PROVIDER: Literal["null"] = "null"
    """Email transport. 'null' logs and reports not-sent; a real vendor adapter is P1 in CURRENT_DECISIONS.md."""
    TASK_QUEUE_PROVIDER: Literal["postgres"] = "postgres"
    """Durable background work (H2-F). 'postgres' = the `tasks` table + the in-process worker."""

    # ── Background task worker (services/tasks/worker.py) ──────────────────
    TASK_WORKER_ENABLED: bool = True
    """Run the worker in this process. Off = the API still queues tasks but nothing drains them
    (a deployment that runs the worker as a separate process would set this per role)."""
    TASK_WORKER_CONCURRENCY: int = 1
    """Tasks this process runs at once. Each is one LLM call; raising it raises provider load, not throughput per task."""
    TASK_POLL_INTERVAL_SECONDS: float = 1.0
    """Sleep between claim attempts when the queue is empty."""
    TASK_STALE_MINUTES: int = 15
    """A RUNNING task older than this is assumed abandoned by a dead process and marked FAILED,
    so a poller is never left waiting forever. Must exceed the slowest handler (LLM timeout x retries)."""

    # ── LiveKit (room tokens + recording egress) ───────────────────────────
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_API_TIMEOUT_SECONDS: float = 10.0
    """Per-call timeout for LiveKit server API calls (egress start/stop, room delete)."""
    LIVEKIT_TOKEN_TTL_MINUTES: int = 360
    """Lifetime of the candidate's room token. 360 = the SDK default the code relied on before this was explicit."""
    EGRESS_LAYOUT: str = "speaker"
    """RoomComposite egress layout for the recording."""
    EGRESS_START_RETRY_ATTEMPTS: int = 10
    """How many times to retry StartRoomCompositeEgress while the room is not yet created."""
    EGRESS_START_RETRY_DELAY_SECONDS: float = 1.0
    """Delay between those retries."""
    RECORDING_PATH_TEMPLATE: str = "interviews/{session_id}/{timestamp}.mp4"
    """Object key for the recording inside the R2 bucket; {session_id} and {timestamp} are substituted."""

    # ── Cloudflare R2 (S3-compatible) — recordings ─────────────────────────
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_ENDPOINT: str = ""
    RECORDING_URL_TTL_SECONDS: int = 3600
    """Lifetime of the presigned GET URL handed to HR for a recording."""
    S3_CONNECT_TIMEOUT_SECONDS: float = 5.0
    S3_READ_TIMEOUT_SECONDS: float = 30.0
    S3_MAX_ATTEMPTS: int = 3
    """boto3 standard-mode retry budget for R2 calls."""

    # ── CVs (Supabase Storage) ─────────────────────────────────────────────
    RESUMES_BUCKET: str = "resumes"
    """Supabase Storage bucket for candidate CVs."""
    MAX_RESUME_BYTES: int = 5 * 1024 * 1024
    """Upload size cap for a CV (5 MB, matching the entry page)."""

    # ── Groq (LLM) ─────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["groq"] = "groq"
    """Which LLM adapter the provider factory builds (H1-B). Only Groq exists today."""
    GROQ_API_KEY: str = ""
    GROQ_API_BASE_URL: str = "https://api.groq.com"
    """Groq API origin. The SDK appends /openai/v1 itself; a value ending in /openai/v1 is accepted and normalised."""
    GROQ_MODEL: str = _DEFAULT_GROQ_MODEL
    """Model for question generation, evaluation and invitation drafts."""
    GROQ_EXTRACTION_MODEL: str = _DEFAULT_GROQ_EXTRACTION_MODEL
    """Smaller/faster model used for CV → profile extraction."""
    GROQ_TIMEOUT_SECONDS: float = 30.0
    """Per-request timeout for every Groq call."""
    GROQ_MAX_RETRIES: int = 2
    """Retries the Groq SDK performs on transient failures (its own default)."""

    # ── Interview lifecycle ────────────────────────────────────────────────
    AGENT_LEASE_MINUTES: int = 10
    """How long an agent's claim on a session lasts before another worker may take it; the agent renews it periodically."""
    DISCONNECT_SWEEP_INTERVAL_SECONDS: int = 120
    """How often the idle-disconnect sweep runs."""
    DISCONNECT_AUTO_FINALIZE_MINUTES: int = 10
    """A session idle in DISCONNECTED for this long is auto-finalized (docs/CURRENT_DECISIONS.md)."""
    ADMIN_TEST_CANDIDATE_EMAIL: str = "admin_tester@path2hire.local"
    """Synthetic candidate used by HR's 'test interview' button; kept out of candidate results."""
    ADMIN_TEST_CANDIDATE_NAME: str = "Admin Tester"

    # ── HR dashboard ───────────────────────────────────────────────────────
    SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR: float = 0.5
    """Minimum evidence sufficiency for a candidate to be 'suggested' (Phase 8D)."""

    @property
    def cors_origins(self) -> List[str]:
        return json.loads(self.BACKEND_CORS_ORIGINS)

    @property
    def supabase_jwt_issuer(self) -> str:
        """Configured issuer, else GoTrue's default for this project URL."""
        if self.SUPABASE_JWT_ISSUER:
            return self.SUPABASE_JWT_ISSUER
        return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1" if self.SUPABASE_URL else ""

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT in ("local", "test")

    @property
    def log_format(self) -> str:
        if self.LOG_FORMAT != "auto":
            return self.LOG_FORMAT
        return "text" if self.is_local else "json"

    @model_validator(mode="after")
    def _empty_model_means_default(self) -> "Settings":
        if not self.GROQ_MODEL:
            self.GROQ_MODEL = _DEFAULT_GROQ_MODEL
        if not self.GROQ_EXTRACTION_MODEL:
            self.GROQ_EXTRACTION_MODEL = _DEFAULT_GROQ_EXTRACTION_MODEL
        return self

    @model_validator(mode="after")
    def _refuse_unsafe_production_config(self) -> "Settings":
        """Fail closed: outside local/test, refuse to start with placeholder
        or missing secrets instead of serving with them."""
        if self.is_local:
            return self
        problems: list[str] = []
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY is the shipped default")
        elif len(self.SECRET_KEY) < _MIN_SECRET_KEY_LENGTH:
            problems.append(f"SECRET_KEY is shorter than {_MIN_SECRET_KEY_LENGTH} characters")
        if not self.AGENT_API_SECRET:
            problems.append("AGENT_API_SECRET is empty")
        for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
            if not getattr(self, name):
                problems.append(f"{name} is empty")
        # H5-C: CORS is explicit per environment. The shipped default is a
        # list of localhost origins for development; booting production
        # with it means either the browser app cannot reach the API, or --
        # worse, if someone "fixes" it with "*" -- any site can, carrying
        # the user's credentials.
        try:
            origins = self.cors_origins
        except (ValueError, TypeError):
            origins = None
            problems.append("BACKEND_CORS_ORIGINS is not a JSON list")
        if origins is not None:
            if not origins:
                problems.append("BACKEND_CORS_ORIGINS is empty")
            for origin in origins:
                if origin == "*":
                    problems.append("BACKEND_CORS_ORIGINS contains '*'")
                elif "localhost" in origin or "127.0.0.1" in origin:
                    problems.append(f"BACKEND_CORS_ORIGINS still contains a development origin ({origin})")
        if problems:
            raise ValueError(
                f"Refusing to start in ENVIRONMENT={self.ENVIRONMENT}: " + "; ".join(problems)
            )
        return self

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
