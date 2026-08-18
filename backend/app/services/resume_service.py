import pymupdf  # PyMuPDF (formerly 'fitz')
import json
import httpx
from fastapi import UploadFile, HTTPException
from supabase import create_client, Client
from app.core.config import settings
from app.schemas.profile import ExtractedCandidateProfile
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# Initialize Supabase client for backend operations (using secret key for admin privileges)
try:
    supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    supabase = None

class ResumeService:
    @staticmethod
    def validate_pdf(file: UploadFile):
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        # We could also check file size here if we read it

    @staticmethod
    async def upload(file: UploadFile, user_id: str, resume_id: UUID) -> str:
        """
        Uploads a PDF file to Supabase Storage in the 'resumes' bucket.
        Path format: users/{user_id}/resumes/{resume_id}.pdf
        """
        try:
            file_bytes = await file.read()
            storage_path = f"users/{user_id}/resumes/{resume_id}.pdf"
            
            if supabase is None:
                raise HTTPException(status_code=500, detail="Supabase client is not initialized.")
                
            # Using Supabase storage api
            res = supabase.storage.from_("resumes").upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": "application/pdf"}
            )
            return storage_path
        except Exception as e:
            logger.error(f"Failed to upload resume to Supabase Storage: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload resume.")

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
    async def build_candidate_profile(text: str) -> ExtractedCandidateProfile:
        """
        Calls Groq API to extract structured profile from resume text.
        """
        if not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY is not set. Skipping LLM extraction.")
            return ExtractedCandidateProfile(recommended_level="mid")
            
        system_prompt = """
        You are an expert technical recruiter. Your task is to extract structured information from a software engineer's resume.
        You must output ONLY valid JSON matching the exact schema provided. Do not include markdown formatting or explanations.
        Extract the candidate's current or most recent professional title as professional_title. If it is not clear, return null rather than inventing one.
        Evaluate their experience and recommend a level strictly from one of these values: "junior", "mid", "senior".
        """
        
        user_prompt = f"Extract the profile from the following resume text:\n\n{text[:10000]}" # Limit to 10k chars to avoid token limits

        try:
            # We can use the JSON schema feature of OpenAI API format that Groq supports
            schema = ExtractedCandidateProfile.model_json_schema()
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": settings.GROQ_MODEL or "llama-3.1-8b-instant", # fallback if not set
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                
                content = data["choices"][0]["message"]["content"]
                parsed_json = json.loads(content)
                
                # Validate the raw JSON against our Pydantic schema
                return ExtractedCandidateProfile(**parsed_json)
                
        except Exception as e:
            logger.error(f"LLM Profile extraction failed: {e}")
            # Return a default empty profile instead of failing completely, so the user can still proceed manually
            return ExtractedCandidateProfile(recommended_level="junior")
