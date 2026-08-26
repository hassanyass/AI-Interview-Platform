# Import all the models, so that Base has them before being
# imported by Alembic
from backend.db.session import Base
from backend.models.profile import CandidateProfile, Resume
from backend.models.interview import (
    InterviewSession, InterviewConfiguration,
    InterviewMessage, InterviewEvent, InterviewCheckpoint
)
