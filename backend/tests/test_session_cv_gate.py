"""Verbal Background subsection, step 2: the candidate CV gate.

docs/verbal-background-subsection-plan.md §2 "Candidate (entry)", rulings
Q1/Q2: register/redeem -> mandatory CV -> Start. Runs the REAL endpoints
(admin authoring, public register, GET/POST /interviews/{id}/cv,
/livekit/token) against the real DB, with only the outbound side effects
stubbed: Supabase Storage, Groq extraction, and the LiveKit recording
egress. Everything it creates is deleted at the end.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole, CandidateProfile
from backend.api.deps import get_current_user_token_data
from backend.schemas.profile import ExtractedCandidateProfile

ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "cv-gate@path2hire.test", "type": "supabase"}
PDF = b"%PDF-1.4 minimal"


@pytest_asyncio.fixture
async def published_public_job():
    async with AsyncSessionLocal() as db:
        db.add(UserRole(user_id=ADMIN_UUID, role="admin"))
        await db.commit()
    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        job = (await c.post("/api/v1/admin/jobs", json={"title": "CV Gate Test Job", "seniority": "mid"})).json()
        job_id, definition_id = job["id"], job["definition"]["id"]
        sec = (await c.post("/api/v1/admin/sections", json={"definition_id": definition_id, "section_type": "VERBAL", "order_index": 0})).json()
        await c.patch(f"/api/v1/admin/sections/{sec['id']}", json={"config": {**sec["config"], "time_budget_minutes": 10}})
        await c.post(f"/api/v1/admin/sections/{sec['id']}/questions", json={"title": "Q", "text": "Tell me."})
        tok = (await c.patch(f"/api/v1/admin/definitions/{definition_id}", json={"is_public": True})).json()["definition"]["public_access_token"]
        assert (await c.post(f"/api/v1/admin/jobs/{job_id}/publish")).status_code == 200
    app.dependency_overrides.pop(get_current_user_token_data, None)
    created = {"job_id": job_id, "public_token": tok, "sessions": [], "emails": []}
    yield created
    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for sid in created["sessions"]:
            await c.delete(f"/api/v1/admin/interviews/{sid}")
        await c.delete(f"/api/v1/admin/jobs/{job_id}")
    app.dependency_overrides.pop(get_current_user_token_data, None)
    async with AsyncSessionLocal() as db:
        for email in created["emails"]:
            await db.execute(delete(CandidateProfile).where(CandidateProfile.email == email))
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.commit()


def _stubs():
    fake_profile = ExtractedCandidateProfile(
        professional_title="Backend Engineer", years_of_experience=6,
        skills=["Python", "FastAPI"], recommended_level="mid",
    )
    return (
        patch("backend.services.resume_service.ResumeService.upload", new=AsyncMock(return_value="users/x/resumes/y.pdf")),
        patch("backend.services.resume_service.ResumeService.extract_text", return_value="Backend Engineer, Python, FastAPI"),
        patch("backend.services.resume_service.ResumeService.build_candidate_profile", new=AsyncMock(return_value=fake_profile)),
        patch("backend.services.sessions.room_token.start_recording_egress", new=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_room_token_is_gated_on_the_cv(published_public_job):
    job = published_public_job
    email = f"cv-gate-{uuid.uuid4().hex[:8]}@example.dev"
    job["emails"].append(email)
    p1, p2, p3, p4 = _stubs()
    with p1, p2, p3, p4:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            reg = (await c.post(f"/api/v1/apply/{job['public_token']}/register", json={"name": "Gate", "email": email})).json()
            sid = reg["session"]["id"]; job["sessions"].append(sid)
            auth = {"Authorization": f"Bearer {reg['access_token']}"}

            # 1) register no longer hands out a room token
            assert reg["livekit_token"] is None and reg["livekit_url"] is None

            # 2) status: required, none yet
            st = (await c.get(f"/api/v1/interviews/{sid}/cv", headers=auth)).json()
            assert st == {**st, "required": True, "has_resume": False, "summary": None}

            # 3) Start is refused with a recognisable reason
            tok = await c.post("/api/v1/livekit/token", json={"session_id": sid}, headers=auth)
            assert tok.status_code == 409 and tok.json()["detail"].startswith("CV_REQUIRED")

            # 4) not a PDF -> 400, still gated
            bad = await c.post(f"/api/v1/interviews/{sid}/cv", headers=auth, files={"file": ("cv.txt", b"x", "text/plain")})
            assert bad.status_code == 400
            assert (await c.post("/api/v1/livekit/token", json={"session_id": sid}, headers=auth)).status_code == 409

            # 5) a PDF -> stored, parsed, linked; summary is what the candidate sees
            up = await c.post(f"/api/v1/interviews/{sid}/cv", headers=auth, files={"file": ("cv.pdf", PDF, "application/pdf")})
            assert up.status_code == 200, up.text
            st = up.json()
            assert st["has_resume"] is True and st["extraction_status"] == "COMPLETED"
            assert st["original_filename"] == "cv.pdf"
            assert st["summary"] == {"professional_title": "Backend Engineer", "years_of_experience": 6,
                                     "skills": ["Python", "FastAPI"], "projects_count": 0}

            # 6) now the room token is issued
            tok = await c.post("/api/v1/livekit/token", json={"session_id": sid}, headers=auth)
            assert tok.status_code == 200 and tok.json()["token"]

            # 7) a returning candidate (same email) starts fresh: no accounts for
            #    public applicants (2026-09-16), nothing carries over -- the CV
            #    must be uploaded again for the new session, and Start is gated.
            reg2 = (await c.post(f"/api/v1/apply/{job['public_token']}/register", json={"name": "Gate", "email": email})).json()
            job["sessions"].append(reg2["session"]["id"])
            auth2 = {"Authorization": f"Bearer {reg2['access_token']}"}
            st2 = (await c.get(f"/api/v1/interviews/{reg2['session']['id']}/cv", headers=auth2)).json()
            assert st2["has_resume"] is False
            assert (await c.post("/api/v1/livekit/token", json={"session_id": reg2["session"]["id"]}, headers=auth2)).status_code == 409


@pytest.mark.asyncio
async def test_cv_endpoints_enforce_ownership_and_session_state(published_public_job):
    job = published_public_job
    email_a = f"cv-own-a-{uuid.uuid4().hex[:6]}@example.dev"
    email_b = f"cv-own-b-{uuid.uuid4().hex[:6]}@example.dev"
    job["emails"] += [email_a, email_b]
    p1, p2, p3, p4 = _stubs()
    with p1, p2, p3, p4:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            a = (await c.post(f"/api/v1/apply/{job['public_token']}/register", json={"name": "A", "email": email_a})).json()
            b = (await c.post(f"/api/v1/apply/{job['public_token']}/register", json={"name": "B", "email": email_b})).json()
            job["sessions"] += [a["session"]["id"], b["session"]["id"]]
            auth_b = {"Authorization": f"Bearer {b['access_token']}"}

            # B cannot read or upload against A's session
            assert (await c.get(f"/api/v1/interviews/{a['session']['id']}/cv", headers=auth_b)).status_code == 403
            r = await c.post(f"/api/v1/interviews/{a['session']['id']}/cv", headers=auth_b,
                             files={"file": ("cv.pdf", PDF, "application/pdf")})
            assert r.status_code == 403

            # Once a session is no longer CREATED the CV is locked
            async with AsyncSessionLocal() as db:
                from backend.models.interview import InterviewSession
                s = (await db.execute(select(InterviewSession).where(InterviewSession.id == uuid.UUID(b["session"]["id"])))).scalar_one()
                s.status = "IN_PROGRESS"; await db.commit()
            r = await c.post(f"/api/v1/interviews/{b['session']['id']}/cv", headers=auth_b,
                             files={"file": ("cv.pdf", PDF, "application/pdf")})
            assert r.status_code == 409
            # ...and a session already past START is never gated on resume
            assert (await c.post("/api/v1/livekit/token", json={"session_id": b["session"]["id"]}, headers=auth_b)).status_code == 200


@pytest.mark.asyncio
async def test_public_register_uses_the_name_typed_this_time(published_public_job):
    """Live finding 2026-09-16: a returning email kept its old stored name
    ("Hi khaled" for a candidate who registered as Ali). Public
    registration now refreshes full_name from the form."""
    job = published_public_job
    email = f"cv-name-{uuid.uuid4().hex[:8]}@example.dev"
    job["emails"].append(email)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        first = (await c.post(f"/api/v1/apply/{job['public_token']}/register", json={"name": "Khaled", "email": email})).json()
        second = (await c.post(f"/api/v1/apply/{job['public_token']}/register", json={"name": "Ali", "email": email})).json()
        job["sessions"] += [first["session"]["id"], second["session"]["id"]]
        sess = (await c.get(f"/api/v1/interviews/{second['session']['id']}",
                            headers={"Authorization": f"Bearer {second['access_token']}"})).json()
    assert sess["candidate_name"] == "Ali"
    async with AsyncSessionLocal() as db:
        name = (await db.execute(select(CandidateProfile.full_name).where(CandidateProfile.email == email))).scalar_one()
    assert name == "Ali"
