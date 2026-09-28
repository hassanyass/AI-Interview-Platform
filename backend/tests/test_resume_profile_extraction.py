"""Step 0 of docs/verbal-background-subsection-plan.md: CV profile extraction.

Guards the two regressions found while proving POST /resumes end-to-end:
  * the JSON schema was never sent to the model, so it invented key names
    (a real Groq run returned `experience_level` instead of the required
    `recommended_level`) and strict validation threw the whole profile away;
  * the failure was swallowed into an empty profile, indistinguishable from
    "the CV had nothing in it".
No network: the LLM call is faked at the provider port (H1-B moved the
Groq client behind backend.providers; before that it was stubbed at the
httpx boundary).
"""
from unittest.mock import patch

import pytest

from backend.schemas.profile import ExtractedCandidateProfile
from backend.services.resume_service import ResumeService
from tests.fakes import FakeLLMProvider


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


@pytest.mark.asyncio
async def test_build_profile_survives_model_key_drift():
    """The exact payload shape a real Groq run returned before the fix."""
    payload = {"professional_title": "Senior ML Engineer", "education": ["BSc CS"],
               "years_of_experience": 8, "skills": ["Python"], "programming_languages": ["Python"],
               "frameworks": ["PyTorch"], "projects": ["RAG assistant"], "experience_level": "senior"}
    llm = FakeLLMProvider(payload)
    profile = await ResumeService.build_candidate_profile("resume text", llm=llm)
    assert profile.professional_title == "Senior ML Engineer"
    assert profile.recommended_level == "senior"
    assert profile.skills == ["Python"]
    # and the prompt actually carries the schema now
    sent = llm.calls[-1]
    assert '"recommended_level"' in sent["messages"][0]["content"]
    # JSON mode is the port's contract (complete_json); the extraction model is chosen per call
    assert sent["model"] is not None


@pytest.mark.asyncio
async def test_build_profile_logs_error_on_failure_and_returns_empty():
    llm = FakeLLMProvider(RuntimeError("groq down"))
    with patch("backend.services.resume_service.logger") as log:
        profile = await ResumeService.build_candidate_profile("resume text", llm=llm)
    assert profile.skills == [] and profile.professional_title is None
    assert log.error.called
