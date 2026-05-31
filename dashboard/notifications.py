"""
dashboard.notifications
=======================

Read-only notification synthesiser.

Builds a small role-scoped list of "things that need attention" from
existing data — no new models, no real-time, no DB writes.

Public API:
    get_notifications(user) -> dict
        {
          "items":  [Notification, ...]    (severity-sorted, capped)
          "count":  int                     (total items),
          "by_severity": {"warning": n, "info": n, "success": n},
          "scope":  "admin" | "rep",
        }

    get_data_quality(user) -> list of metric dicts
        Each metric: {label, value, total, percent, severity, hint, url, icon}
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta
from typing import Any

from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from paints.models import Paint
from quotation.models import Quotation, QuotationPdfExport, QuotationSection
from system_tools.models import AppSetting
from users.models import User


# Severity ordering for sorting
_SEVERITY_ORDER = {"warning": 0, "info": 1, "success": 2}

# Max notifications shown in the bell dropdown
_MAX_ITEMS = 8


@dataclass
class Notification:
    title: str
    description: str
    severity: str          # "warning" | "info" | "success"
    icon: str              # bootstrap-icons class
    url: str = ""
    timestamp: Any = None  # datetime or None
    tag: str = ""          # short label e.g. "audit", "draft"

    def to_dict(self) -> dict:
        return asdict(self)


def _is_admin(user) -> bool:
    return bool(user and (user.is_superuser or getattr(user, "role", None) == "ADMIN"))


def _profile_complete(user) -> bool:
    return bool(user and user.first_name and user.last_name and user.email)


def _pref(user, name: str, default: bool = True) -> bool:
    """Safely read a per-user notification preference."""
    try:
        return bool(getattr(getattr(user, "app_settings", None), name, default))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Notification builders
# ---------------------------------------------------------------------------

def _admin_notifications(user=None) -> list[Notification]:
    items: list[Notification] = []

    sys_on    = _pref(user, "notify_system_activity")
    drafts_on = _pref(user, "notify_draft_quotations")
    pdf_on    = _pref(user, "notify_failed_pdfs")

    # Users with incomplete profiles
    incomplete = User.objects.filter(is_active=True).filter(
        first_name=""
    ).count() + User.objects.filter(is_active=True).filter(
        last_name=""
    ).exclude(first_name="").count()
    if incomplete and sys_on:
        items.append(Notification(
            title=f"{incomplete} user{'s' if incomplete != 1 else ''} with incomplete profile",
            description="Reps with missing name or email may show blank attribution on PDFs.",
            severity="info",
            icon="bi-person-exclamation",
            url=reverse("users:user_list"),
            tag="users",
        ))

    # Paints missing prices
    missing_price = Paint.objects.filter(is_active=True).filter(
        price_excl_vat__isnull=True
    ).count() + Paint.objects.filter(is_active=True).filter(
        price_incl_vat__isnull=True
    ).exclude(price_excl_vat__isnull=True).count()
    if missing_price and sys_on:
        items.append(Notification(
            title=f"{missing_price} active paint{'s' if missing_price != 1 else ''} missing pricing",
            description="Reps cannot generate accurate quotes without VAT-inclusive and exclusive prices.",
            severity="warning",
            icon="bi-currency-exchange",
            url=reverse("paints:paint_list"),
            tag="paints",
        ))

    # Draft quotations pending across the system
    draft_count = Quotation.objects.filter(status=Quotation.Status.DRAFT).count()
    if draft_count and drafts_on:
        items.append(Notification(
            title=f"{draft_count} draft quotation{'s' if draft_count != 1 else ''} in progress",
            description="Drafts older than 7 days may need a nudge or to be cancelled.",
            severity="info",
            icon="bi-pencil-square",
            url=reverse("quotation:quotation_list") + "?status=DRAFT",
            tag="drafts",
        ))

    # Failed PDF exports in last 30 days
    since = timezone.now() - timedelta(days=30)
    failed = QuotationPdfExport.objects.filter(
        status=QuotationPdfExport.Status.FAILED,
        created_at__gte=since,
    ).count()
    if failed and pdf_on:
        items.append(Notification(
            title=f"{failed} failed PDF export{'s' if failed != 1 else ''} (30d)",
            description="Investigate template or data issues, then regenerate from the quotation.",
            severity="warning",
            icon="bi-file-earmark-x",
            url=reverse("quotation:quotation_list"),
            tag="pdf",
        ))

    # VAT configured status
    has_vat = AppSetting.objects.filter(key=AppSetting.VAT_RATE_KEY).exists()
    if sys_on and not has_vat:
        items.append(Notification(
            title="VAT rate not configured",
            description="Set the global VAT rate so quotations and invoices compute correctly.",
            severity="warning",
            icon="bi-percent",
            url=reverse("system_tools:vat_settings"),
            tag="system",
        ))
    elif sys_on:
        items.append(Notification(
            title="VAT rate configured",
            description="Global tax rate is set. Update it from System Settings if regulations change.",
            severity="success",
            icon="bi-check-circle",
            url=reverse("system_tools:vat_settings"),
            tag="system",
        ))

    # Recent audit actions (most recent 1)
    recent = AuditLog.objects.select_related("user").order_by("-created_at").first()
    if recent and sys_on:
        actor = (recent.user.get_full_name() or recent.user.username) if recent.user else "System"
        items.append(Notification(
            title=f"Latest activity: {recent.action}",
            description=f"{actor} • {recent.module.capitalize()}",
            severity="info",
            icon="bi-clock-history",
            url=reverse("audit:audit_log_list"),
            timestamp=recent.created_at,
            tag="audit",
        ))

    return items


def _rep_notifications(user) -> list[Notification]:
    items: list[Notification] = []

    profile_on     = _pref(user, "notify_profile_incomplete")
    drafts_on      = _pref(user, "notify_draft_quotations")
    placeholder_on = _pref(user, "notify_placeholder_sections")
    pdf_on         = _pref(user, "notify_failed_pdfs")

    if profile_on and not _profile_complete(user):
        items.append(Notification(
            title="Complete your profile",
            description="Add your full name and email so your work is attributed correctly.",
            severity="warning",
            icon="bi-person-exclamation",
            url=reverse("users:profile"),
            tag="profile",
        ))

    my_drafts = Quotation.objects.filter(
        created_by=user, status=Quotation.Status.DRAFT
    )
    draft_count = my_drafts.count()
    if draft_count and drafts_on:
        items.append(Notification(
            title=f"{draft_count} draft{'s' if draft_count != 1 else ''} waiting for you",
            description="Pick up where you left off — your latest progress is auto-saved.",
            severity="info",
            icon="bi-pencil-square",
            url=reverse("quotation:quotation_list") + "?status=DRAFT",
            tag="drafts",
        ))

    # Sections not configured on the rep's own drafts
    unconfigured = QuotationSection.objects.filter(
        quotation__created_by=user,
        quotation__status=Quotation.Status.DRAFT,
        is_placeholder=True,
    ).count()
    if unconfigured and placeholder_on:
        items.append(Notification(
            title=f"{unconfigured} surface{'s' if unconfigured != 1 else ''} still placeholder",
            description="Open the builder to configure them so the quotation can be reviewed.",
            severity="warning",
            icon="bi-grid-3x3-gap",
            url=reverse("quotation:quotation_list") + "?status=DRAFT",
            tag="sections",
        ))

    # Failed PDF exports authored by this user, last 30 days
    since = timezone.now() - timedelta(days=30)
    my_failed = QuotationPdfExport.objects.filter(
        generated_by=user,
        status=QuotationPdfExport.Status.FAILED,
        created_at__gte=since,
    ).count()
    if my_failed and pdf_on:
        items.append(Notification(
            title=f"{my_failed} of your PDF export{'s' if my_failed != 1 else ''} failed",
            description="Open the quotation and try regenerating with a different template.",
            severity="warning",
            icon="bi-file-earmark-x",
            url=reverse("quotation:quotation_list"),
            tag="pdf",
        ))

    return items


def get_notifications(user) -> dict:
    if not user or not user.is_authenticated:
        return {"items": [], "count": 0, "by_severity": {}, "scope": "anon"}

    scope = "admin" if _is_admin(user) else "rep"
    items = _admin_notifications(user) if scope == "admin" else _rep_notifications(user)

    items.sort(key=lambda n: (_SEVERITY_ORDER.get(n.severity, 99), 0))
    by_severity: dict[str, int] = {}
    for item in items:
        by_severity[item.severity] = by_severity.get(item.severity, 0) + 1

    return {
        "items": [n.to_dict() for n in items[:_MAX_ITEMS]],
        "count": len(items),
        "by_severity": by_severity,
        "scope": scope,
    }


# ---------------------------------------------------------------------------
# Data quality widget
# ---------------------------------------------------------------------------

def _pct(done: int, total: int) -> int:
    if not total:
        return 100
    return int(round((done / total) * 100))


def _severity_from_percent(pct: int) -> str:
    if pct >= 90:
        return "success"
    if pct >= 60:
        return "info"
    return "warning"


def get_data_quality(user) -> list[dict]:
    metrics: list[dict] = []
    is_admin = _is_admin(user)

    if is_admin:
        # Profile completeness (across active users)
        active_users = User.objects.filter(is_active=True)
        total_users = active_users.count()
        complete_users = active_users.exclude(first_name="").exclude(last_name="").exclude(email="").count()
        pct = _pct(complete_users, total_users)
        metrics.append({
            "label": "User profile completeness",
            "value": complete_users,
            "total": total_users,
            "percent": pct,
            "severity": _severity_from_percent(pct),
            "hint": "Active users with name + email filled.",
            "url": reverse("users:user_list"),
            "icon": "bi-person-check",
        })

        # Paints with pricing
        active_paints = Paint.objects.filter(is_active=True)
        total_paints = active_paints.count()
        priced = active_paints.exclude(price_excl_vat__isnull=True).exclude(price_incl_vat__isnull=True).count()
        pct = _pct(priced, total_paints)
        metrics.append({
            "label": "Paints with pricing",
            "value": priced,
            "total": total_paints,
            "percent": pct,
            "severity": _severity_from_percent(pct),
            "hint": "Active paints that have both VAT-inclusive and exclusive prices.",
            "url": reverse("paints:paint_list"),
            "icon": "bi-palette",
        })

        # Quotations needing review (drafts older than 7 days)
        cutoff = timezone.now() - timedelta(days=7)
        stale = Quotation.objects.filter(
            status=Quotation.Status.DRAFT, updated_at__lt=cutoff
        ).count()
        total_drafts = Quotation.objects.filter(status=Quotation.Status.DRAFT).count()
        # Lower is better for stale, so invert
        fresh = max(total_drafts - stale, 0)
        pct = _pct(fresh, total_drafts) if total_drafts else 100
        metrics.append({
            "label": "Fresh drafts (≤ 7 days)",
            "value": fresh,
            "total": total_drafts,
            "percent": pct,
            "severity": _severity_from_percent(pct),
            "hint": "Drafts updated in the last week. Older drafts may need a nudge or cancellation.",
            "url": reverse("quotation:quotation_list") + "?status=DRAFT",
            "icon": "bi-pencil-square",
        })

        # PDF export success (last 30 days)
        since = timezone.now() - timedelta(days=30)
        recent_exports = QuotationPdfExport.objects.filter(created_at__gte=since)
        total_exports = recent_exports.count()
        succeeded = recent_exports.filter(status=QuotationPdfExport.Status.GENERATED).count()
        pct = _pct(succeeded, total_exports) if total_exports else 100
        metrics.append({
            "label": "PDF export success (30d)",
            "value": succeeded,
            "total": total_exports,
            "percent": pct,
            "severity": _severity_from_percent(pct),
            "hint": "Generated successfully vs total exports attempted recently.",
            "url": reverse("quotation:quotation_list"),
            "icon": "bi-file-earmark-pdf",
        })

        # System setup
        setup_items = 3
        setup_done = 0
        if active_users.exclude(is_superuser=True).exists(): setup_done += 1
        if active_paints.exists(): setup_done += 1
        if AppSetting.objects.filter(key=AppSetting.VAT_RATE_KEY).exists(): setup_done += 1
        pct = _pct(setup_done, setup_items)
        metrics.append({
            "label": "System setup",
            "value": setup_done,
            "total": setup_items,
            "percent": pct,
            "severity": _severity_from_percent(pct),
            "hint": "Team members, paint catalogue, and VAT rate configured.",
            "url": reverse("system_tools:system_settings"),
            "icon": "bi-sliders",
        })
    else:
        # Rep-scoped quality
        profile_done = int(_profile_complete(user))
        metrics.append({
            "label": "Profile completeness",
            "value": profile_done,
            "total": 1,
            "percent": 100 if profile_done else 0,
            "severity": "success" if profile_done else "warning",
            "hint": "Your name + email filled.",
            "url": reverse("users:profile"),
            "icon": "bi-person-circle",
        })

        my_quotes = Quotation.objects.filter(created_by=user)
        total = my_quotes.count()
        completed = my_quotes.filter(status=Quotation.Status.COMPLETED).count()
        pct = _pct(completed, total) if total else 0
        metrics.append({
            "label": "Your completed quotations",
            "value": completed,
            "total": total,
            "percent": pct,
            "severity": _severity_from_percent(pct) if total else "info",
            "hint": "Quotations you've marked complete vs your total.",
            "url": reverse("quotation:quotation_list"),
            "icon": "bi-check2-circle",
        })

        since = timezone.now() - timedelta(days=30)
        my_recent = QuotationPdfExport.objects.filter(generated_by=user, created_at__gte=since)
        total_recent = my_recent.count()
        my_ok = my_recent.filter(status=QuotationPdfExport.Status.GENERATED).count()
        pct = _pct(my_ok, total_recent) if total_recent else 100
        metrics.append({
            "label": "Your PDF success (30d)",
            "value": my_ok,
            "total": total_recent,
            "percent": pct,
            "severity": _severity_from_percent(pct),
            "hint": "Your PDF exports that generated successfully recently.",
            "url": reverse("quotation:quotation_list"),
            "icon": "bi-file-earmark-pdf",
        })

    return metrics
