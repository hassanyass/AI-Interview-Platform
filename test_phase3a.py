import asyncio
import os
import sys
import uuid
import logging
from datetime import datetime, timezone
import httpx
import pytest

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# Mock environment variables for missing API keys
os.environ["SUPABASE_URL"] = "http://localhost:8000"
os.environ["SUPABASE_SECRET_KEY"] = "mock_secret_key"

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.core.config import settings

# Override settings before importing app.main
settings.SUPABASE_URL = "http://localhost:8000"
settings.SUPABASE_SECRET_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSJ9.mock"
settings.LIVEKIT_API_KEY = "devkey"
settings.LIVEKIT_API_SECRET = "secret"
settings.AGENT_API_SECRET = "dummy_secret"

from app.main import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOCK_USER_ID = "00000000-0000-0000-0000-000000000000"
AGENT_SECRET = settings.AGENT_API_SECRET or "dummy_secret"

from app.core.security import get_current_user
async def override_current_user():
    return MOCK_USER_ID

app.dependency_overrides[get_current_user] = override_current_user

async def create_profile_if_missing(client: AsyncClient):
    resp = await client.get("/api/v1/profiles/me")
    if resp.status_code == 404:
        await client.post("/api/v1/profiles/", json={
            "full_name": "Test Candidate",
            "email": "test@example.com",
            "years_of_experience": 2
        })

@pytest.mark.asyncio
async def test_phase3a_persistence_integration():
    """
    Test that question_records and current_question are persisted atomically
    and restored correctly via the FastAPI checkpoints endpoint.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await create_profile_if_missing(client)
        
        # 1. Create a session
        resp = await client.post("/api/v1/interviews/", json={
            "configuration": {
                "role": "Software Engineer",
                "level": "mid",
                "language": "en"
            }
        })
        assert resp.status_code == 200
        session_id = resp.json()["id"]

        # 2. Agent loads session (claims lease)
        agent_id = "agent-phase3a"
        agent_headers = {"x-agent-secret": AGENT_SECRET}
        load_resp = await client.get(f"/api/v1/internal/interviews/{session_id}/load?agent_id={agent_id}", headers=agent_headers)
        assert load_resp.status_code == 200
        
        # 3. Create a checkpoint
        # Simulate: Question A is SKIPPED, Question B is active.
        checkpoint_payload = {
            "schema_version": 1,
            "current_phase": "TECHNICAL",
            "current_question_id": "qB",
            "question_index": 1,
            "section": "TECHNICAL",
            "hints_used": 0,
            "followups_used": 0,
            "background_questions_asked": 1,
            "competencies_evaluated": [],
            "time_remaining_seconds": 1200,
            "last_message_sequence": 1,
            "last_event_sequence": 1,
            "current_question_snapshot": {
                "id": "qB",
                "title": "Question B",
                "problem_statement": "Solve B",
                "difficulty": "mid",
                "competency": "coding",
                "expected_concepts": [],
                "hints": [],
                "follow_up_topics": [],
                "time_budget_minutes": 20,
                "coding_required": True,
                "examples": [],
                "constraints": [],
                "starter_code": {},
                "test_cases": []
            },
            "section_progress": {
                "background": {"name": "background", "questions_asked": 1, "questions_completed": 1, "limits": {"target_questions": 2, "max_questions": 3}},
                "technical": {"name": "technical", "questions_asked": 2, "questions_completed": 0, "questions_skipped": 1, "limits": {"target_questions": 2, "max_questions": 3}}
            },
            "question_records": [
                {
                    "question_id": "qA",
                    "outcome": "SKIPPED",
                    "hints_used": 1,
                    "followups_used": 0,
                    "clarifications_used": 0,
                    "assistance_records": []
                }
            ]
        }
        
        cp_resp = await client.post(
            f"/api/v1/internal/interviews/{session_id}/checkpoints",
            json=checkpoint_payload,
            headers=agent_headers
        )
        assert cp_resp.status_code == 201, f"Failed to save checkpoint: {cp_resp.text}"
        
        cp_data = cp_resp.json()
        assert cp_data["question_records"] is not None
        assert len(cp_data["question_records"]) == 1
        assert cp_data["question_records"][0]["question_id"] == "qA"
        assert cp_data["question_records"][0]["outcome"] == "SKIPPED"
        
        # 4. Agent simulates a crash and reload
        reload_resp = await client.get(f"/api/v1/internal/interviews/{session_id}/load?agent_id={agent_id}", headers=agent_headers)
        assert reload_resp.status_code == 200
        reload_data = reload_resp.json()
        
        latest_checkpoint = reload_data["latest_checkpoint"]
        assert latest_checkpoint is not None
        
        # Verify current_question is EXACTLY B
        snapshot = latest_checkpoint["current_question_snapshot"]
        assert snapshot is not None
        assert snapshot["id"] == "qB"
        
        # Verify question_records contains EXACTLY A
        records = latest_checkpoint["question_records"]
        assert records is not None
        assert len(records) == 1
        assert records[0]["question_id"] == "qA"
        assert records[0]["outcome"] == "SKIPPED"
        
        # Verify question A is not active (since current_question_id is qB)
        assert latest_checkpoint["current_question_id"] == "qB"

        # ==========================================================
        # 5. Test Backward Compatibility
        # ==========================================================
        resp2 = await client.post("/api/v1/interviews/", json={
            "configuration": {
                "role": "Software Engineer",
                "level": "mid",
                "language": "en"
            }
        })
        assert resp2.status_code == 200
        session_id2 = resp2.json()["id"]

        agent_id_old = "agent-phase3a-old"
        await client.get(f"/api/v1/internal/interviews/{session_id2}/load?agent_id={agent_id_old}", headers=agent_headers)
        
        # Create a checkpoint without question_records
        checkpoint_payload_old = {
            "schema_version": 1,
            "current_phase": "TECHNICAL",
            "current_question_id": "q1",
            "question_index": 0,
            "section": "TECHNICAL",
            "hints_used": 0,
            "followups_used": 0,
            "background_questions_asked": 1,
            "competencies_evaluated": [],
            "time_remaining_seconds": 1200,
            "last_message_sequence": 1,
            "last_event_sequence": 1,
            "current_question_snapshot": None,
            "section_progress": {
                "background": {"name": "background", "questions_asked": 1, "questions_completed": 1, "limits": {"target_questions": 2, "max_questions": 3}},
                "technical": {"name": "technical", "questions_asked": 1, "questions_completed": 0, "questions_skipped": 0, "limits": {"target_questions": 2, "max_questions": 3}}
            },
            "question_records": None
        }
        
        cp_resp_old = await client.post(
            f"/api/v1/internal/interviews/{session_id2}/checkpoints",
            json=checkpoint_payload_old,
            headers=agent_headers
        )
        assert cp_resp_old.status_code == 201
        
        reload_resp_old = await client.get(f"/api/v1/internal/interviews/{session_id2}/load?agent_id={agent_id_old}", headers=agent_headers)
        assert reload_resp_old.status_code == 200
        reload_data_old = reload_resp_old.json()
        
        latest_checkpoint_old = reload_data_old["latest_checkpoint"]
        assert latest_checkpoint_old is not None
        assert latest_checkpoint_old["question_records"] is None
        
        # Verify it gracefully handles missing question_records
        records_snapshot = latest_checkpoint_old.get("question_records")
        if records_snapshot is None:
            records_snapshot = []
            
        assert len(records_snapshot) == 0
        
if __name__ == "__main__":
    asyncio.run(test_phase3a_persistence_integration())
