"""
Dashboard analytics selectors.

All data fetching and computation lives here; views stay thin.
"""

import json
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from audit.models import AuditLog
from paints.models import Paint
from users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_filter(period: str) -> dict:
    """Return filter kwargs for a named period string."""
    now = timezone.now()
    if period == "this_month":
        return {"created_at__year": now.year, "created_at__month": now.month}
    if period == "last_30_days":
        return {"created_at__gte": now - timedelta(days=30)}
    return {}  # "all" — no filter


def _monthly_trend_to_json(trend_qs) -> tuple[str, str]:
    """Convert a TruncMonth queryset to two JSON strings (labels, data)."""
    labels = [row["month"].strftime("%b %Y") for row in trend_qs]
    data = [row["count"] for row in trend_qs]
    return json.dumps(labels), json.dumps(data)


# ---------------------------------------------------------------------------
# Admin selectors
# ---------------------------------------------------------------------------

def get_admin_metrics(period: str = "all") -> dict:
    f = _date_filter(period)
    qs = AuditLog.objects.filter(**f)

    # KPI cards
    total_active_reps = User.objects.filter(role=User.Role.REP, is_active=True).count()
    total_active_paints = Paint.objects.filter(is_active=True).count()
    total_audit_actions = qs.count()
    total_users = User.objects.filter(is_active=True).count()

    # Top reps by action count (in selected period)
    top_reps = list(
        qs.filter(user__role=User.Role.REP)
        .values("user__id", "user__first_name", "user__last_name", "user__username")
        .annotate(count=Count("id"))
        .order_by("-count")[:8]
    )

    # Module breakdown (in selected period)
    module_breakdown = list(
        qs.values("module")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Monthly trend — always last 12 months regardless of period filter
    twelve_months_ago = timezone.now() - timedelta(days=365)
    trend_qs = (
        AuditLog.objects.filter(created_at__gte=twelve_months_ago)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )
    trend_labels_json, trend_data_json = _monthly_trend_to_json(trend_qs)

    # Build chart JSON for top reps
    top_rep_labels = [
        (r["user__first_name"] + " " + r["user__last_name"]).strip()
        or r["user__username"]
        for r in top_reps
    ]
    top_rep_data = [r["count"] for r in top_reps]

    # Build chart JSON for module breakdown
    module_labels = [r["module"].capitalize() for r in module_breakdown]
    module_data = [r["count"] for r in module_breakdown]

    return {
        # KPI
        "total_active_reps": total_active_reps,
        "total_active_paints": total_active_paints,
        "total_audit_actions": total_audit_actions,
        "total_users": total_users,
        # Table data
        "top_reps": top_reps,
        "module_breakdown": module_breakdown,
        # Chart JSON (safe to emit into <script> via |safe filter)
        "trend_labels_json": trend_labels_json,
        "trend_data_json": trend_data_json,
        "top_rep_labels_json": json.dumps(top_rep_labels),
        "top_rep_data_json": json.dumps(top_rep_data),
        "module_labels_json": json.dumps(module_labels),
        "module_data_json": json.dumps(module_data),
    }


# ---------------------------------------------------------------------------
# Rep selectors
# ---------------------------------------------------------------------------

def get_rep_metrics(user, period: str = "all") -> dict:
    f = _date_filter(period)
    qs = AuditLog.objects.filter(user=user, **f)

    my_total_actions = qs.count()

    # Recent 10 entries — always unfiltered so they show the true latest
    recent_activity = list(
        AuditLog.objects.filter(user=user).select_related("user")[:10]
    )

    # Module breakdown (in selected period)
    my_modules = list(
        qs.values("module")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Monthly trend — always last 12 months
    twelve_months_ago = timezone.now() - timedelta(days=365)
    trend_qs = (
        AuditLog.objects.filter(user=user, created_at__gte=twelve_months_ago)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )
    trend_labels_json, trend_data_json = _monthly_trend_to_json(trend_qs)

    module_labels = [r["module"].capitalize() for r in my_modules]
    module_data = [r["count"] for r in my_modules]

    return {
        "my_total_actions": my_total_actions,
        "recent_activity": recent_activity,
        "my_modules": my_modules,
        "trend_labels_json": trend_labels_json,
        "trend_data_json": trend_data_json,
        "module_labels_json": json.dumps(module_labels),
        "module_data_json": json.dumps(module_data),
    }
