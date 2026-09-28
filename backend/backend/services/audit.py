"""Writing the admin audit trail (H5-C).

One helper, used at the handful of admin actions that change or destroy
somebody else's data. It adds the row to the caller's session without
committing: an audit entry and the action it records belong to the same
transaction, so a rolled-back deletion cannot leave a record saying it
happened, and a recorded deletion cannot happen without its record.

The one exception is a deletion whose side effects reach outside the
database (a recording in object storage). There the row is written with
the outcome of those side effects included, after they are attempted --
see `admin.py`'s deletion endpoints.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import request_id_var
from backend.models.audit import AdminAuditLog

logger = logging.getLogger(__name__)


def record_admin_action(
    db: AsyncSession,
    *,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AdminAuditLog:
    """Stage an audit row on `db`. The caller commits."""
    entry = AdminAuditLog(
        actor_id=str(actor_id),
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details,
        request_id=request_id_var.get(),
    )
    db.add(entry)
    logger.info(
        "Admin %s: %s %s %s", actor_id, action, target_type, target_id or "",
        extra={"event": "admin_action", "action": action, "target_type": target_type},
    )
    return entry
