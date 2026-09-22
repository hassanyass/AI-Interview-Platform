"""Builds one adapter per port from Settings and caches it for the process.

Application code calls ``get_<port>()``; tests either pass a fake straight
into the service function (every service takes its provider as an optional
argument) or call ``reset_providers()`` after changing ``settings``.
Adding a vendor = a new adapter module + one branch here + a new value in
the matching ``*_PROVIDER`` Literal in core/config.py.
"""
from __future__ import annotations

from functools import lru_cache

from backend.core.config import settings
from backend.providers.email.base import EmailProvider
from backend.providers.email.null import NullEmailProvider
from backend.providers.llm.base import LLMProvider
from backend.providers.llm.groq import GroqLLMProvider
from backend.providers.notifications.base import NotificationService
from backend.providers.notifications.console import ConsoleNotificationService
from backend.providers.notifications.email import EmailNotificationService
from backend.providers.realtime.base import RealtimeProvider
from backend.providers.realtime.livekit import LiveKitProvider
from backend.providers.storage.base import ObjectStorage
from backend.providers.storage.s3 import S3CompatibleStorage
from backend.providers.storage.supabase import SupabaseStorage


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    if settings.LLM_PROVIDER == "groq":
        return GroqLLMProvider(
            api_key=settings.GROQ_API_KEY,
            default_model=settings.GROQ_MODEL,
            base_url=settings.GROQ_API_BASE_URL,
            timeout_seconds=settings.GROQ_TIMEOUT_SECONDS,
            max_retries=settings.GROQ_MAX_RETRIES,
        )
    raise ValueError(f"Unknown LLM_PROVIDER {settings.LLM_PROVIDER!r}")


@lru_cache(maxsize=1)
def get_recordings_storage() -> ObjectStorage:
    if settings.RECORDINGS_STORAGE_PROVIDER == "s3":
        return S3CompatibleStorage(
            endpoint=settings.R2_ENDPOINT,
            access_key_id=settings.R2_ACCESS_KEY_ID,
            secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            bucket=settings.R2_BUCKET_NAME,
            account_id=settings.R2_ACCOUNT_ID,
            connect_timeout=settings.S3_CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.S3_READ_TIMEOUT_SECONDS,
            max_attempts=settings.S3_MAX_ATTEMPTS,
        )
    raise ValueError(f"Unknown RECORDINGS_STORAGE_PROVIDER {settings.RECORDINGS_STORAGE_PROVIDER!r}")


@lru_cache(maxsize=1)
def get_resumes_storage() -> ObjectStorage:
    if settings.RESUMES_STORAGE_PROVIDER == "supabase":
        return SupabaseStorage(
            project_url=settings.SUPABASE_URL,
            service_key=settings.SUPABASE_SECRET_KEY,
            bucket=settings.RESUMES_BUCKET,
            timeout_seconds=settings.SUPABASE_STORAGE_TIMEOUT_SECONDS,
            retry_attempts=settings.STORAGE_RETRY_ATTEMPTS,
        )
    raise ValueError(f"Unknown RESUMES_STORAGE_PROVIDER {settings.RESUMES_STORAGE_PROVIDER!r}")


@lru_cache(maxsize=1)
def get_realtime() -> RealtimeProvider:
    if settings.REALTIME_PROVIDER == "livekit":
        return LiveKitProvider(
            url=settings.LIVEKIT_URL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            egress_layout=settings.EGRESS_LAYOUT,
            egress_start_retry_attempts=settings.EGRESS_START_RETRY_ATTEMPTS,
            egress_start_retry_delay_seconds=settings.EGRESS_START_RETRY_DELAY_SECONDS,
            api_timeout_seconds=settings.LIVEKIT_API_TIMEOUT_SECONDS,
        )
    raise ValueError(f"Unknown REALTIME_PROVIDER {settings.REALTIME_PROVIDER!r}")


@lru_cache(maxsize=1)
def get_email() -> EmailProvider:
    if settings.EMAIL_PROVIDER == "null":
        return NullEmailProvider()
    raise ValueError(f"Unknown EMAIL_PROVIDER {settings.EMAIL_PROVIDER!r}")


@lru_cache(maxsize=1)
def get_notification_service() -> NotificationService:
    if settings.NOTIFICATIONS_PROVIDER == "console":
        return ConsoleNotificationService()
    if settings.NOTIFICATIONS_PROVIDER == "email":
        return EmailNotificationService(get_email())
    raise ValueError(f"Unknown NOTIFICATIONS_PROVIDER {settings.NOTIFICATIONS_PROVIDER!r}")


def reset_providers() -> None:
    """Drop every cached adapter so the next ``get_*`` rebuilds from the
    current ``settings``. For tests."""
    for fn in (get_llm, get_recordings_storage, get_resumes_storage, get_realtime, get_email, get_notification_service):
        fn.cache_clear()
