"""H1-B: provider ports, adapters and the settings-driven factory.

No network. Adapters that would need a live vendor are exercised only for
the parts that are pure (token signing, presigned-URL construction,
destination mapping, selection/caching).
"""
from datetime import timedelta

import jwt
import pytest
from pydantic import ValidationError

from backend.core.config import Settings, settings
from backend.providers import factory
from backend.providers.email.null import NullEmailProvider
from backend.providers.llm.groq import GroqLLMProvider
from backend.providers.notifications.console import ConsoleNotificationService
from backend.providers.notifications.email import EmailNotificationService
from backend.providers.realtime.livekit import LiveKitProvider
from backend.providers.storage.base import S3Destination
from backend.providers.storage.s3 import S3CompatibleStorage
from backend.providers.storage.supabase import SupabaseStorage
from backend.services.evaluation_generator import generate_evaluation
from backend.services.invitation_message_generator import generate_invitation_message
from backend.services.question_generator import generate_questions
from tests.fakes import FakeEmailProvider, FakeLLMProvider, MemoryStorage


@pytest.fixture(autouse=True)
def _fresh_factory():
    factory.reset_providers()
    yield
    factory.reset_providers()


# ── factory ────────────────────────────────────────────────────────────────

def test_factory_builds_the_configured_adapters_and_caches_them():
    assert isinstance(factory.get_recordings_storage(), S3CompatibleStorage)
    assert isinstance(factory.get_resumes_storage(), SupabaseStorage)
    assert isinstance(factory.get_realtime(), LiveKitProvider)
    assert isinstance(factory.get_email(), NullEmailProvider)
    assert isinstance(factory.get_notification_service(), ConsoleNotificationService)
    assert factory.get_realtime() is factory.get_realtime()


def test_factory_llm_requires_an_api_key(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        factory.get_llm()
    monkeypatch.setattr(settings, "GROQ_API_KEY", "k")
    factory.reset_providers()
    llm = factory.get_llm()
    assert isinstance(llm, GroqLLMProvider) and llm.default_model == settings.GROQ_MODEL


def test_notifications_email_routes_through_the_email_port(monkeypatch):
    monkeypatch.setattr(settings, "NOTIFICATIONS_PROVIDER", "email")
    svc = factory.get_notification_service()
    assert isinstance(svc, EmailNotificationService)


def test_unknown_selector_values_are_rejected_at_settings_level():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SUPABASE_URL="u", SUPABASE_SECRET_KEY="k", SUPABASE_JWKS_URL="j",
                 DATABASE_URL="d", EMAIL_PROVIDER="sendgrid")


# ── email / notifications ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_null_email_provider_reports_not_sent():
    from backend.providers.email.base import EmailMessage
    result = await NullEmailProvider().send(EmailMessage(to="a@b.c", subject="s", text="t"))
    assert result.sent is False and result.provider == "null" and "no email provider" in result.reason


@pytest.mark.asyncio
async def test_email_notification_service_renders_the_invitation():
    email = FakeEmailProvider(sent=False)
    svc = EmailNotificationService(email)
    await svc.send_invitation_email("cand@example.com", "https://app/invite/tok", {"job_title": "Backend Engineer"})
    (msg,) = email.messages
    assert msg.to == "cand@example.com"
    assert "Backend Engineer" in msg.subject
    assert "https://app/invite/tok" in msg.text


# ── storage ────────────────────────────────────────────────────────────────

def test_s3_storage_presigns_and_exposes_egress_destination():
    s = S3CompatibleStorage(endpoint="https://acc.r2.cloudflarestorage.com", access_key_id="AK", secret_access_key="SK",
                            bucket="recordings", account_id="acc")
    assert s.configured
    url = s.presign_get("interviews/x/1.mp4", ttl_seconds=600)
    assert url.startswith("https://acc.r2.cloudflarestorage.com/recordings/interviews/x/1.mp4?")
    assert "X-Amz-Expires=600" in url
    assert s.egress_destination() == S3Destination(access_key="AK", secret="SK", bucket="recordings",
                                                   endpoint="https://acc.r2.cloudflarestorage.com")


def test_s3_storage_unconfigured_when_any_credential_is_missing():
    s = S3CompatibleStorage(endpoint="e", access_key_id="", secret_access_key="s", bucket="b", account_id="a")
    assert not s.configured


def test_supabase_storage_has_no_presign():
    s = SupabaseStorage(project_url="https://p.supabase.co", service_key="k", bucket="resumes")
    assert s.configured
    with pytest.raises(NotImplementedError):
        s.presign_get("x", ttl_seconds=1)
    with pytest.raises(NotImplementedError):
        s.egress_destination()


# ── realtime ───────────────────────────────────────────────────────────────

def test_livekit_token_carries_identity_room_and_ttl():
    p = LiveKitProvider(url="wss://x", api_key="devkey", api_secret="secret" * 6)
    tok = p.mint_participant_token(room="interview-1", identity="candidate-u", name="Candidate u", ttl=timedelta(minutes=5))
    claims = jwt.decode(tok, "secret" * 6, algorithms=["HS256"], options={"verify_aud": False})
    assert claims["sub"] == "candidate-u"
    assert claims["name"] == "Candidate u"
    assert claims["video"]["room"] == "interview-1" and claims["video"]["roomJoin"] is True
    assert 290 <= claims["exp"] - claims["nbf"] <= 310 or 290 <= claims["exp"] - claims["iat"] <= 310


# ── services take an injected LLM ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_generators_use_the_injected_llm_and_pass_json_mode_parameters():
    llm = FakeLLMProvider({"questions": [{"title": "T", "competency": "c", "text": "Q?", "eval_criteria": {}, "config": {}}]})
    out = await generate_questions(job_title="J", job_description=None, seniority=None, required_skills=None,
                                   preferred_skills=None, responsibilities=None, location=None,
                                   candidate_instructions=None, section_type="VERBAL", section_config=None,
                                   num_questions=1, llm=llm)
    assert out and out[0]["text"] == "Q?"
    assert llm.calls[-1]["temperature"] == 0.7 and llm.calls[-1]["max_tokens"] == 4096

    llm = FakeLLMProvider({"subject": "S", "body": "B"})
    out = await generate_invitation_message(job_title="J", job_description=None, seniority=None, duration_minutes=30, llm=llm)
    assert out == {"subject": "S", "body": "B"}
    assert llm.calls[-1]["max_tokens"] == 1024

    llm = FakeLLMProvider({"overall_score": 3, "recommendation": "Hold", "evidence_sufficiency": 0.5,
                           "summary": "s", "detailed_overview": "d", "criterion_scores": []})
    out = await generate_evaluation(role="r", level="l", transcript=[], question_records=[], technical_submission={},
                                    question_eval_criteria={}, criteria=[], llm=llm)
    assert out["overall_score"] == 3
    assert llm.calls[-1]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_resume_upload_and_delete_go_through_the_storage_port():
    from io import BytesIO
    from uuid import uuid4
    from starlette.datastructures import UploadFile

    from backend.services.resume_service import ResumeService

    store = MemoryStorage()
    f = UploadFile(filename="cv.pdf", file=BytesIO(b"%PDF-1.4 x"), headers={"content-type": "application/pdf"})
    rid = uuid4()
    path = await ResumeService.upload(f, "user-1", rid, storage=store)
    assert path == f"users/user-1/resumes/{rid}.pdf"
    assert store.objects[path] == b"%PDF-1.4 x"
    assert await ResumeService.delete_object(path, storage=store) is True
    assert store.deleted == [path]


@pytest.mark.parametrize("given", ["https://api.groq.com", "https://api.groq.com/", "https://api.groq.com/openai/v1", "https://api.groq.com/openai/v1/"])
def test_groq_provider_normalises_the_base_url_so_the_sdk_does_not_double_the_path(given):
    llm = GroqLLMProvider(api_key="k", default_model="m", base_url=given)
    assert str(llm._client.base_url).rstrip("/") == "https://api.groq.com"
