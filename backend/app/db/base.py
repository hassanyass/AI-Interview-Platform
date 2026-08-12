# Import all the models, so that Base has them before being
# imported by Alembic
from app.db.session import Base
from app.models.profile import CandidateProfile, Resume
from app.models.interview import InterviewSession, InterviewConfiguration
