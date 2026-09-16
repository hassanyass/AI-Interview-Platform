"""Verbal Background subsection, step 4: evaluation + results.

docs/verbal-background-subsection-plan.md §2 "Evaluation"/"Results", §9.
- the backend evaluator receives the parsed CV as `candidate_profile` and
  its prompt carries the cv_alignment instruction block (Groq stubbed);
- the admin result enriches a BACKGROUND record from the record's own
  text (its id resolves to no InterviewQuestion row) and tags it, while an
  HR record still resolves through the InterviewQuestion join (real DB,
  throwaway rows, cleaned up).
"""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole, CandidateProfile
from backend.models.interview import InterviewSession, InterviewCheckpoint, Evaluation
from backend.api.deps import get_current_user_token_data
from backend.services.evaluation_generator import generate_evaluation, EVALUATOR_SYSTEM_PROMPT

ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "bg-eval@path2hire.test", "type": "supabase"}


def test_backend_evaluator_prompt_has_cv_alignment_block():
    assert "cv_alignment" in EVALUATOR_SYSTEM_PROMPT
    assert "candidate_profile" in EVALUATOR_SYSTEM_PROMPT
    assert '"subsection": "BACKGROUND"' in EVALUATOR_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_backend_evaluator_sends_candidate_profile_in_evidence():
    fake = MagicMock()
    fake.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "overall_score": 4, "recommendation": "Hire", "evidence_sufficiency": 0.8,
            "summary": "s", "detailed_overview": "d",
            "criterion_scores": [{"criterion_key": "cv_alignment", "score": 4, "overview": "o",
                                  "strengths": [], "improvements": [], "evidence_reference": None}],
        })))]
    )
    with patch("backend.services.evaluation_generator.Groq", return_value=fake), \
         patch("backend.services.evaluation_generator.settings") as s:
        s.GROQ_API_KEY, s.GROQ_MODEL = "k", "m"
        out = await generate_evaluation(
            role="AI Engineer", level="senior", transcript=[], question_records=[],
            technical_submission={}, question_eval_criteria={},
            criteria=[{"key": "cv_alignment", "label": "CV & Experience Alignment", "kind": "content", "guidance_text": "g", "section_id": None}],
            candidate_profile={"professional_title": "Senior ML Engineer", "skills": ["Python"]},
        )
    sent = fake.chat.completions.create.call_args.kwargs["messages"]
    evidence = json.loads(sent[1]["content"])
    assert evidence["candidate_profile"] == {"professional_title": "Senior ML Engineer", "skills": ["Python"]}
    assert "cv_alignment" in sent[0]["content"]
    assert out["criterion_scores"][0].criterion_key == "cv_alignment"

    # no CV -> {} (never a missing key the prompt would trip over)
    with patch("backend.services.evaluation_generator.Groq", return_value=fake), \
         patch("backend.services.evaluation_generator.settings") as s:
        s.GROQ_API_KEY, s.GROQ_MODEL = "k", "m"
        await generate_evaluation(role="r", level="l", transcript=[], question_records=[],
                                  technical_submission={}, question_eval_criteria={}, criteria=[])
    assert json.loads(fake.chat.completions.create.call_args.kwargs["messages"][1]["content"])["candidate_profile"] == {}


@pytest_asyncio.fixture
async def completed_session_with_records():
    async with AsyncSessionLocal() as db:
        db.add(UserRole(user_id=ADMIN_UUID, role="admin"))
        await db.commit()
    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        job = (await c.post("/api/v1/admin/jobs", json={"title": "BG Results Test Job", "seniority": "mid"})).json()
        job_id, definition_id = job["id"], job["definition"]["id"]
        sec = (await c.post("/api/v1/admin/sections", json={"definition_id": definition_id, "section_type": "VERBAL", "order_index": 0})).json()
        hr_q = (await c.post(f"/api/v1/admin/sections/{sec['id']}/questions",
                             json={"title": "Ownership", "text": "Tell me about ownership.", "competency": "ownership"})).json()
    candidate_id, session_id = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(CandidateProfile(id=candidate_id, full_name="BG Results Cand", email=f"bg-results-{candidate_id.hex[:8]}@example.dev"))
        db.add(InterviewSession(id=session_id, candidate_profile_id=candidate_id, job_id=uuid.UUID(job_id),
                                definition_id=uuid.UUID(definition_id), role="Backend Engineer", level="mid",
                                language="en", status="COMPLETED"))
        db.add(InterviewCheckpoint(
            session_id=session_id, current_phase="COMPLETED", question_index=0, time_remaining_seconds=0,
            question_records=[
                {"question_id": "bg-1-abc", "outcome": "COMPLETED", "hints_used": 0, "followups_used": 1,
                 "clarifications_used": 0, "assistance_records": [], "evaluation": None,
                 "question_title": "Recent role", "question_text": "What did you own as Senior ML Engineer?",
                 "competency": "background:recent_role", "subsection": "BACKGROUND"},
                {"question_id": hr_q["id"], "outcome": "COMPLETED", "hints_used": 0, "followups_used": 2,
                 "clarifications_used": 0, "assistance_records": [], "evaluation": None},
            ],
        ))
        db.add(Evaluation(session_id=session_id, overall_score=3, recommendation="Consider / Mixed",
                          evidence_sufficiency=0.5, summary="s", detailed_overview="d"))
        await db.commit()
    yield {"session_id": str(session_id), "hr_question_id": hr_q["id"]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.delete(f"/api/v1/admin/interviews/{session_id}")
        await c.delete(f"/api/v1/admin/jobs/{job_id}")
    app.dependency_overrides.pop(get_current_user_token_data, None)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CandidateProfile).where(CandidateProfile.id == candidate_id))
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.commit()


@pytest.mark.asyncio
async def test_result_enriches_background_record_from_itself_and_hr_record_from_db(completed_session_with_records):
    sid = completed_session_with_records["session_id"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/admin/interviews/{sid}/result")
    assert r.status_code == 200, r.text
    bg, hr = r.json()["question_records"]
    assert (bg["subsection"], bg["title"], bg["text"], bg["competency"]) == (
        "BACKGROUND", "Recent role", "What did you own as Senior ML Engineer?", "background:recent_role")
    assert bg["order_index"] is None
    assert (hr["subsection"], hr["title"], hr["text"], hr["competency"], hr["order_index"]) == (
        None, "Ownership", "Tell me about ownership.", "ownership", 0)
