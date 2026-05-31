"""
audit.filters

Single source of truth for the Audit Log filter logic.

Both the AuditLogListView (UI) and the CSV export view feed off
``apply_audit_filters`` so the table and the downloaded CSV always
agree on what the current filter set means.
"""
from __future__ import annotations

from django.db.models import Q

from .models import AuditLog


def apply_audit_filters(qs, params):
    """Apply the standard audit filters from a request.GET-like mapping."""
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(action__icontains=q)
            | Q(module__icontains=q)
            | Q(description__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
        )

    module = (params.get("module") or "").strip()
    if module:
        qs = qs.filter(module=module)

    action = (params.get("action") or "").strip()
    if action:
        qs = qs.filter(action=action)

    user_id = (params.get("user") or "").strip()
    if user_id.isdigit():
        qs = qs.filter(user_id=int(user_id))

    date_from = (params.get("date_from") or "").strip()
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)

    date_to = (params.get("date_to") or "").strip()
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    return qs


def get_filter_choices():
    """Distinct values used to populate the filter <select>s."""
    return {
        "modules": list(
            AuditLog.objects.values_list("module", flat=True)
            .distinct()
            .order_by("module")
        ),
        "actions": list(
            AuditLog.objects.values_list("action", flat=True)
            .distinct()
            .order_by("action")
        ),
    }
