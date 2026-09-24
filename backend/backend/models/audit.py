"""Who did what to whose data (H5-C).

`InterviewEvent` already records what happened *inside* an interview. This
records what an administrator did *to* it from outside: publishing a job,
deleting a session or a candidate, overriding a recommendation. Those are
the actions that change or destroy another person's data, and until now
the only trace of one was a log line in a container's stdout.

Append-only by convention -- nothing in the application updates or deletes
a row here, and the purge job deliberately leaves them alone: the record
that data was deleted must outlive the data.
"""
import uuid

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from backend.db.session import Base

# Actions. Kept as plain strings rather than a DB enum so adding one is a
# code change, not a migration.
JOB_PUBLISHED = "job.published"
JOB_STATUS_CHANGED = "job.status_changed"
JOB_DELETED = "job.deleted"
SESSION_DELETED = "session.deleted"
CANDIDATE_DELETED = "candidate.deleted"
EVALUATION_OVERRIDDEN = "evaluation.suggested_override"
DATA_PURGED = "data.purged"


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(String, nullable=False)
    """The admin's subject from their token. A string, not a FK: the row must
    survive the account being removed, which is the point of an audit trail."""
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    """`job` | `session` | `candidate` | `evaluation` | `data`."""
    target_id = Column(String, nullable=True)
    details = Column(JSONB, nullable=True)
    """Enough to understand the action without the row it refers to -- which
    may be gone. For a deletion: what was removed and how much."""
    request_id = Column(String, nullable=True)
    """Ties the entry to the request's log lines (core/logging.py)."""
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_admin_audit_log_created_at", "created_at"),
        Index("ix_admin_audit_log_target", "target_type", "target_id"),
    )
