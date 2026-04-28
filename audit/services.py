"""
audit.services
==============
Central audit logging helper for ProStar Paints.

Usage
-----
    from audit.services import log_action

    log_action(
        user=request.user,
        action="USER_CREATED",
        module="users",
        description="Admin created rep account for John Smith.",
        metadata={"target_user_id": user.pk},
        request=request,       # optional — captures IP + user-agent
    )

Design principles
-----------------
- Never raises an exception back to the caller.
  A failed audit write must never break the main request.
- All parameters except user/action/module are optional.
- IP detection handles proxied environments (X-Forwarded-For).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_client_ip(request) -> str | None:
    """Return the real client IP, respecting common proxy headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # Take the first (leftmost) address — the original client
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def log_action(
    user,
    action: str,
    module: str,
    description: str = "",
    metadata: dict[str, Any] | None = None,
    request=None,
) -> None:
    """
    Write an AuditLog entry.

    Parameters
    ----------
    user        : User instance (or None for anonymous/system actions)
    action      : Short uppercase constant, e.g. "USER_CREATED"
    module      : App / domain name, e.g. "users", "paints"
    description : Human-readable summary (stored as-is)
    metadata    : Arbitrary JSON-serialisable dict for extra context
    request     : Django HttpRequest (optional) — used to capture IP and UA
    """
    try:
        from audit.models import AuditLog  # local import avoids circular deps

        ip = None
        ua = ""
        if request is not None:
            ip = _get_client_ip(request)
            ua = request.META.get("HTTP_USER_AGENT", "")[:512]

        AuditLog.objects.create(
            user=user if (user and user.is_authenticated) else None,
            action=action,
            module=module,
            description=description,
            metadata=metadata,
            ip_address=ip,
            user_agent=ua,
        )
    except Exception:
        # Log to the Python logging system but never propagate to the caller.
        logger.exception(
            "audit.log_action failed silently: action=%s module=%s user=%s",
            action,
            module,
            getattr(user, "username", "unknown"),
        )
