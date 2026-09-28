import pymupdf  # PyMuPDF (formerly 'fitz')
import asyncio
import json
from backend.providers.factory import get_llm, get_resumes_storage
from backend.providers.llm.base import LLMProvider
from backend.providers.storage.base import ObjectStorage, StorageError, StorageUnavailable
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
# Storage is called over its REST API (providers/storage/supabase.py, behind
# the ObjectStorage port since H1-B), the same way scripts/create_demo_admin.py
# bypasses the SDK for Auth. Same bucket, same object paths as before --
# nothing about where CVs live changed. Bucket name and size cap live in
# Settings (RESUMES_BUCKET, MAX_RESUME_BYTES).

class ResumeService:
    @staticmethod
    def validate_pdf(file: UploadFile):
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        # We could also check file size here if we read it

    @staticmethod
    def storage_path_for(user_id: str, resume_id: UUID) -> str:
        """Object key for a candidate's CV: users/{user_id}/resumes/{resume_id}.pdf"""
        return f"users/{user_id}/resumes/{resume_id}.pdf"

    @staticmethod
    async def upload(file: UploadFile, user_id: str, resume_id: UUID, storage: ObjectStorage | None = None) -> str:
        """
        Uploads a PDF to the resumes object store (Supabase Storage today,
        via the ObjectStorage port). Path format: users/{user_id}/resumes/{resume_id}.pdf
        """
        storage = storage or get_resumes_storage()
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if len(file_bytes) > settings.MAX_RESUME_BYTES:
            raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller.")

        storage_path = ResumeService.storage_path_for(user_id, resume_id)
        try:
            await storage.put(storage_path, file_bytes, content_type="application/pdf")
        except StorageUnavailable as e:
            logger.error("Resume store unreachable while uploading resume: %s", e)
            raise HTTPException(status_code=502, detail="Failed to upload resume.")
        except StorageError as e:
            logger.error("Resume store upload failed for %s: %s", storage_path, e)
            raise HTTPException(status_code=500, detail="Failed to upload resume.")
        return storage_path

    @staticmethod
    async def delete_object(storage_path: str, storage: ObjectStorage | None = None) -> bool:
        """Best-effort delete of a stored resume object; True on success."""
        storage = storage or get_resumes_storage()
        try:
            await storage.delete(storage_path)
            return True
        except StorageError as e:
            logger.error("Resume store delete failed for %s: %s", storage_path, e)
            return False

    @staticmethod
    def extract_text(file_bytes: bytes) -> str:
        """
        Extracts text from PDF bytes using PyMuPDF. CPU-bound and synchronous:
        call via extract_text_async from request handlers (H2-B).
        """
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            return text
        except Exception as e:  # noqa: BLE001 -- PyMuPDF raises assorted classes for a corrupt/odd PDF
            logger.error(f"Failed to extract text from PDF: {e}")
            raise HTTPException(status_code=500, detail="Failed to extract text from PDF.")

    @staticmethod
    async def extract_text_async(file_bytes: bytes) -> str:
        """extract_text off the event loop; a multi-page CV parse must not
        freeze every other request for its duration."""
        return await asyncio.to_thread(ResumeService.extract_text, file_bytes)

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
    async def build_candidate_profile(text: str, llm: LLMProvider | None = None) -> ExtractedCandidateProfile:
        """
        Calls the LLM provider to extract a structured profile from resume text.

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
        if llm is None:
            if not settings.GROQ_API_KEY:
                logger.warning("GROQ_API_KEY is not set. Skipping LLM extraction.")
                return ExtractedCandidateProfile(recommended_level="mid")
            llm = get_llm()

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
            content = await llm.complete_json(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=settings.GROQ_EXTRACTION_MODEL,
                temperature=0.1,
            )
            parsed_json = json.loads(content)
            return ExtractedCandidateProfile(**ResumeService._normalize_profile_payload(parsed_json))
        except Exception as e:  # noqa: BLE001 -- deliberately non-fatal, see below
            # Deliberately not fatal: the CV is stored and its text kept, so a
            # transient LLM failure must not lose the upload. But it IS loud --
            # an empty profile downstream means "extraction failed", never
            # "the CV was empty".
            logger.error("LLM profile extraction failed; returning an empty profile: %s", e)
            return ExtractedCandidateProfile(recommended_level="mid")
