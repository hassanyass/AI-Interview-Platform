"""Step 0 of docs/verbal-background-subsection-plan.md: CV profile extraction.

Guards the two regressions found while proving POST /resumes end-to-end:
  * the JSON schema was never sent to the model, so it invented key names
    (a real Groq run returned `experience_level` instead of the required
    `recommended_level`) and strict validation threw the whole profile away;
  * the failure was swallowed into an empty profile, indistinguishable from
    "the CV had nothing in it".
No network: the Groq call is stubbed at the httpx boundary.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas.profile import ExtractedCandidateProfile
from backend.services.resume_service import ResumeService


def test_prompt_lists_every_schema_key():
    described = ResumeService._schema_description()
    for key in ExtractedCandidateProfile.model_fields:
        assert f'"{key}"' in described, key


def test_normalize_maps_level_alias_and_numeric_strings():
    raw = {"professional_title": "ML Engineer", "experience_level": " Senior ",
           "years_of_experience": "7 years", "skills": ["Python"]}
    out = ResumeService._normalize_profile_payload(raw)
    assert out["recommended_level"] == "senior"
    assert "experience_level" not in out
    assert out["years_of_experience"] == 7
    ExtractedCandidateProfile(**out)  # validates


def test_normalize_defaults_unknown_level_to_mid():
    assert ResumeService._normalize_profile_payload({})["recommended_level"] == "mid"
    assert ResumeService._normalize_profile_payload({"recommended_level": "staff"})["recommended_level"] == "mid"


def _groq_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return resp


@pytest.mark.asyncio
async def test_build_profile_survives_model_key_drift():
    """The exact payload shape a real Groq run returned before the fix."""
    payload = {"professional_title": "Senior ML Engineer", "education": ["BSc CS"],
               "years_of_experience": 8, "skills": ["Python"], "programming_languages": ["Python"],
               "frameworks": ["PyTorch"], "projects": ["RAG assistant"], "experience_level": "senior"}
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=_groq_response(payload))
    with patch("backend.services.resume_service.settings") as s, \
         patch("backend.services.resume_service.httpx.AsyncClient", return_value=client):
        s.GROQ_API_KEY, s.GROQ_MODEL = "test-key", "test-model"
        profile = await ResumeService.build_candidate_profile("resume text")
    assert profile.professional_title == "Senior ML Engineer"
    assert profile.recommended_level == "senior"
    assert profile.skills == ["Python"]
    # and the prompt actually carries the schema now
    sent = client.post.call_args.kwargs["json"]
    assert '"recommended_level"' in sent["messages"][0]["content"]
    assert sent["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_build_profile_logs_error_on_failure_and_returns_empty():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(side_effect=RuntimeError("groq down"))
    with patch("backend.services.resume_service.settings") as s, \
         patch("backend.services.resume_service.httpx.AsyncClient", return_value=client), \
         patch("backend.services.resume_service.logger") as log:
        s.GROQ_API_KEY, s.GROQ_MODEL = "test-key", "test-model"
        profile = await ResumeService.build_candidate_profile("resume text")
    assert profile.skills == [] and profile.professional_title is None
    assert log.error.called
