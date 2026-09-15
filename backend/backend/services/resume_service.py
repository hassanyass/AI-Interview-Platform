import pymupdf  # PyMuPDF (formerly 'fitz')
import json
import httpx
from fastapi import UploadFile, HTTPException
from backend.core.config import settings
from backend.schemas.profile import ExtractedCandidateProfile
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# Background-subsection plan, step 0 (docs/verbal-background-subsection-plan.md,
# 2026-09-15): CV upload was broken end-to-end. This module used to build a
# supabase-py client at import time, and that SDK (2.31.0) rejects this
# project's new-format "sb_secret_..." key with "Invalid API key" (its regex
# only accepts the old three-segment JWT key shape) -- so the client was
# always None and every upload returned 500 "Supabase client is not
# initialized" (also the source of the "Failed to initialize Supabase client"
# warning on every backend start, noted in docs/LOCAL_DEMO_SETUP.md).
# Storage is now called over its REST API directly with httpx, the same way
# scripts/create_demo_admin.py bypasses the SDK for Auth. Same bucket, same
# object paths as before -- nothing about where CVs live changed.
RESUMES_BUCKET = "resumes"
MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB, matching the entry-page limit in the plan

class ResumeService:
    @staticmethod
    def validate_pdf(file: UploadFile):
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        # We could also check file size here if we read it

    @staticmethod
    def _storage_headers() -> dict:
        return {
            "Authorization": f"Bearer {settings.SUPABASE_SECRET_KEY}",
            "apikey": settings.SUPABASE_SECRET_KEY,
        }

    @staticmethod
    async def upload(file: UploadFile, user_id: str, resume_id: UUID) -> str:
        """
        Uploads a PDF file to Supabase Storage in the 'resumes' bucket via the
        Storage REST API (POST /storage/v1/object/{bucket}/{path}).
        Path format: users/{user_id}/resumes/{resume_id}.pdf
        """
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if len(file_bytes) > MAX_RESUME_BYTES:
            raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller.")

        storage_path = f"users/{user_id}/resumes/{resume_id}.pdf"
        url = f"{settings.SUPABASE_URL}/storage/v1/object/{RESUMES_BUCKET}/{storage_path}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        **ResumeService._storage_headers(),
                        "Content-Type": "application/pdf",
                        # resume_id is a fresh uuid4 per upload, so this only
                        # matters for a retried request -- lets it succeed
                        # instead of 409ing on its own half-written object.
                        "x-upsert": "true",
                    },
                    content=file_bytes,
                )
        except httpx.HTTPError as e:
            logger.error("Supabase Storage unreachable while uploading resume: %s", e)
            raise HTTPException(status_code=502, detail="Failed to upload resume.")
        if resp.status_code not in (200, 201):
            logger.error(
                "Supabase Storage upload failed (%s) for %s: %s",
                resp.status_code, storage_path, resp.text[:300],
            )
            raise HTTPException(status_code=500, detail="Failed to upload resume.")
        return storage_path

    @staticmethod
    async def delete_object(storage_path: str) -> bool:
        """Best-effort delete of a stored resume object; True on success."""
        url = f"{settings.SUPABASE_URL}/storage/v1/object/{RESUMES_BUCKET}/{storage_path}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.delete(url, headers=ResumeService._storage_headers())
            return resp.status_code in (200, 204)
        except httpx.HTTPError as e:
            logger.error("Supabase Storage unreachable while deleting %s: %s", storage_path, e)
            return False

    @staticmethod
    def extract_text(file_bytes: bytes) -> str:
        """
        Extracts text from PDF bytes using PyMuPDF.
        """
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            return text
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise HTTPException(status_code=500, detail="Failed to extract text from PDF.")

    @staticmethod
    def _schema_description() -> str:
        """The exact keys the model must emit, from the Pydantic schema itself
        (so this can never drift from ExtractedCandidateProfile)."""
        props = ExtractedCandidateProfile.model_json_schema().get("properties", {})
        lines = []
        for name, meta in props.items():
            typ = meta.get("type") or ("array" if "items" in meta else "string")
            if "anyOf" in meta:
                typ = " | ".join(t.get("type", "null") for t in meta["anyOf"])
            lines.append(f'  "{name}": {typ} -- {meta.get("description", "")}')
        return "\n".join(lines)

    @staticmethod
    def _normalize_profile_payload(parsed: dict) -> dict:
        """Tolerate the model's most likely key/value drift before strict
        validation: a differently-named level key, casing/whitespace on the
        level, and a numeric string for years."""
        data = dict(parsed)
        for alias in ("experience_level", "level", "seniority", "seniority_level"):
            if "recommended_level" not in data and alias in data:
                data["recommended_level"] = data.pop(alias)
        level = str(data.get("recommended_level") or "").strip().lower()
        data["recommended_level"] = level if level in ("junior", "mid", "senior") else "mid"
        years = data.get("years_of_experience")
        if isinstance(years, str):
            digits = "".join(ch for ch in years if ch.isdigit())
            data["years_of_experience"] = int(digits) if digits else 0
        return data

    @staticmethod
    async def build_candidate_profile(text: str) -> ExtractedCandidateProfile:
        """
        Calls Groq API to extract structured profile from resume text.

        Step 0 fix (docs/verbal-background-subsection-plan.md, 2026-09-15): the
        JSON schema was computed here but never sent to the model, while the
        prompt told it to "match the exact schema provided" -- so the model
        invented key names (a real run returned `experience_level` instead of
        `recommended_level`), strict validation failed on the missing
        required key, and the entire -- otherwise good -- profile was thrown
        away for the empty fallback below. Every uploaded CV therefore
        produced no profile data at all. The schema is now spelled out in
        the prompt from the model's own definition, and the most likely drift
        is normalised before validation.
        """
        if not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY is not set. Skipping LLM extraction.")
            return ExtractedCandidateProfile(recommended_level="mid")

        system_prompt = (
            "You are an expert technical recruiter. Extract structured information from a "
            "software/AI professional's resume.\n"
            "Output ONLY a single JSON object with EXACTLY these keys (no others, no markdown):\n"
            f"{ResumeService._schema_description()}\n"
            "Rules:\n"
            "- professional_title: the current or most recent title verbatim; null if unclear.\n"
            "- years_of_experience: an integer (total professional years); 0 if unknown.\n"
            "- education, skills, programming_languages, frameworks, projects: arrays of short strings ([] if none).\n"
            "- recommended_level: exactly one of \"junior\", \"mid\", \"senior\" -- your assessment of their level.\n"
        )
        user_prompt = f"Resume text:\n\n{text[:10000]}"  # cap to stay within context limits

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.GROQ_MODEL or "llama-3.1-8b-instant",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed_json = json.loads(content)
                return ExtractedCandidateProfile(**ResumeService._normalize_profile_payload(parsed_json))
        except Exception as e:
            # Deliberately not fatal: the CV is stored and its text kept, so a
            # transient LLM failure must not lose the upload. But it IS loud --
            # an empty profile downstream means "extraction failed", never
            # "the CV was empty".
            logger.error("LLM profile extraction failed; returning an empty profile: %s", e)
            return ExtractedCandidateProfile(recommended_level="mid")
