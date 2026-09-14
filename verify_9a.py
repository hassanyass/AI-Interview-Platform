"""
Phase 9A Manual Verification — live generate-questions for CODING and MCQ.

Uses httpx + ASGITransport (same as tests) with JWT override to bypass auth,
then calls the real Groq API via question_generator.py.
"""
import asyncio
import json
import uuid
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole
from backend.api.deps import get_current_user_token_data

ADMIN_UUID = str(uuid.uuid4())

_admin_payload = {
    "sub": ADMIN_UUID,
    "email": "verify-9a@path2hire.test",
    "type": "supabase",
}


async def main():
    # Seed admin role
    async with AsyncSessionLocal() as session:
        from sqlalchemy.future import select
        stmt = select(UserRole).where(UserRole.user_id == uuid.UUID(ADMIN_UUID))
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            session.add(UserRole(user_id=uuid.UUID(ADMIN_UUID), role="admin"))
            await session.commit()

    app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create job
        job_resp = await client.post("/api/v1/admin/jobs", json={
            "title": "Phase 9A Verification Job",
            "description": "Backend engineer role for testing CODING/MCQ generation",
            "seniority": "mid",
            "required_skills": ["Python", "FastAPI", "SQL"],
        })
        assert job_resp.status_code == 201, job_resp.text
        job = job_resp.json()
        definition_id = job["definition"]["id"]
        print(f"Job created: {job['id']}")

        # Create CODING section
        coding_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "CODING", "order_index": 0,
        })
        assert coding_resp.status_code == 201, coding_resp.text
        coding_section_id = coding_resp.json()["id"]
        print(f"CODING section: {coding_section_id}")

        # Create MCQ section
        mcq_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "MCQ", "order_index": 1,
        })
        assert mcq_resp.status_code == 201, mcq_resp.text
        mcq_section_id = mcq_resp.json()["id"]
        print(f"MCQ section: {mcq_section_id}")

        # === CODING generate-questions ===
        print("\n" + "=" * 70)
        print("CODING — POST /admin/sections/{id}/generate-questions")
        print("=" * 70)
        coding_req_body = {"num_questions": 2}
        print(f"REQUEST: POST /api/v1/admin/sections/{coding_section_id}/generate-questions")
        print(f"BODY: {json.dumps(coding_req_body, indent=2)}")

        coding_gen = await client.post(
            f"/api/v1/admin/sections/{coding_section_id}/generate-questions",
            json=coding_req_body,
        )
        print(f"\nRESPONSE STATUS: {coding_gen.status_code}")
        print(f"RESPONSE BODY:\n{json.dumps(coding_gen.json(), indent=2)}")

        # === MCQ generate-questions ===
        print("\n" + "=" * 70)
        print("MCQ — POST /admin/sections/{id}/generate-questions")
        print("=" * 70)
        mcq_req_body = {"num_questions": 2}
        print(f"REQUEST: POST /api/v1/admin/sections/{mcq_section_id}/generate-questions")
        print(f"BODY: {json.dumps(mcq_req_body, indent=2)}")

        mcq_gen = await client.post(
            f"/api/v1/admin/sections/{mcq_section_id}/generate-questions",
            json=mcq_req_body,
        )
        print(f"\nRESPONSE STATUS: {mcq_gen.status_code}")
        print(f"RESPONSE BODY:\n{json.dumps(mcq_gen.json(), indent=2)}")

    app.dependency_overrides.pop(get_current_user_token_data, None)


asyncio.run(main())
