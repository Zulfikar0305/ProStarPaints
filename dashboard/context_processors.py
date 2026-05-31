"""
dashboard.context_processors
============================

Exposes role-scoped notification summary to every template so the navbar
bell can render its badge and dropdown without each view needing to
inject the data manually.

Key: `notifications` -> dict from dashboard.notifications.get_notifications.
"""

from __future__ import annotations

from .notifications import get_notifications


def notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"notifications": {"items": [], "count": 0, "by_severity": {}, "scope": "anon"}}
    return {"notifications": get_notifications(user)}
