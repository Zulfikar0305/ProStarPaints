"""
quotation.workspace
===================

Read-only helpers that power the Quotation Workspace page:
stats, readiness, filtering, recently-viewed (session-backed) and pinned
quotations. Permission-aware: every helper expects a *scoped* queryset.

No pricing logic, no save logic, no PDF logic — diagnostics only.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import Count, F, Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from .models import Quotation, QuotationPdfExport


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------

def is_admin(user) -> bool:
    return bool(user and (user.is_superuser or getattr(user, "role", None) == "ADMIN"))


def scoped_quotations(user) -> QuerySet[Quotation]:
    """Return the base queryset the given user is allowed to see."""
    qs = Quotation.objects.select_related("created_by")
    if not is_admin(user):
        qs = qs.filter(created_by=user)
    return qs


def annotate_workspace(qs: QuerySet[Quotation]) -> QuerySet[Quotation]:
    """Attach total/configured section counts and successful PDF count."""
    return qs.annotate(
        ws_total_sections=Count("sections", distinct=True),
        ws_configured_sections=Count(
            "sections",
            filter=Q(sections__line_items__isnull=False),
            distinct=True,
        ),
        ws_pdf_count=Count(
            "pdf_exports",
            filter=Q(pdf_exports__status=QuotationPdfExport.Status.GENERATED),
            distinct=True,
        ),
    )


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------

READINESS_KEYS = ("not_started", "in_progress", "ready", "pdf_generated")

READINESS_LABELS = {
    "not_started":   "Not started",
    "in_progress":   "In progress",
    "ready":         "Ready for review",
    "pdf_generated": "PDF generated",
}

READINESS_VARIANTS = {
    "not_started":   "danger",
    "in_progress":   "warning",
    "ready":         "info",
    "pdf_generated": "success",
}

READINESS_ICONS = {
    "not_started":   "bi-slash-circle",
    "in_progress":   "bi-hourglass-split",
    "ready":         "bi-check2-circle",
    "pdf_generated": "bi-file-earmark-pdf-fill",
}


def get_quotation_readiness(quotation: Quotation) -> dict:
    """
    Decide readiness from annotated counts when available, falling back to
    live queries when called on a non-annotated object.
    """
    total = getattr(quotation, "ws_total_sections", None)
    configured = getattr(quotation, "ws_configured_sections", None)
    pdf_count = getattr(quotation, "ws_pdf_count", None)

    if total is None:
        total = quotation.sections.count()
    if configured is None:
        configured = (
            quotation.sections.annotate(_c=Count("line_items"))
            .filter(_c__gt=0).count()
        )
    if pdf_count is None:
        pdf_count = quotation.pdf_exports.filter(
            status=QuotationPdfExport.Status.GENERATED
        ).count()

    if pdf_count > 0:
        key = "pdf_generated"
    elif total == 0 or configured == 0:
        key = "not_started"
    elif configured < total:
        key = "in_progress"
    else:
        key = "ready"

    return {
        "key":          key,
        "label":        READINESS_LABELS[key],
        "variant":      READINESS_VARIANTS[key],
        "icon":         READINESS_ICONS[key],
        "configured":   configured,
        "total":        total,
        "pdf_count":    pdf_count,
        "has_pdf":      pdf_count > 0,
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_quotation_workspace_stats(user) -> dict:
    """Compact KPI block for the workspace header."""
    qs = scoped_quotations(user)
    total = qs.count()
    drafts = qs.filter(status=Quotation.Status.DRAFT).count()
    completed = qs.filter(status=Quotation.Status.COMPLETED).count()

    pdfs = QuotationPdfExport.objects.filter(
        status=QuotationPdfExport.Status.GENERATED,
        quotation__in=qs,
    ).count()

    # "Needs configuration" = at least one configured section but not all configured (and no PDF)
    needs_config = (
        annotate_workspace(qs)
        .filter(
            ws_total_sections__gt=0,
            ws_configured_sections__gt=0,
            ws_configured_sections__lt=F("ws_total_sections"),
            ws_pdf_count=0,
        )
        .count()
    )

    return {
        "total":         total,
        "drafts":        drafts,
        "completed":     completed,
        "pdfs":          pdfs,
        "needs_config":  needs_config,
    }


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

READINESS_FILTER_CHOICES = (
    ("not_started",   "Not started"),
    ("in_progress",   "Needs configuration"),
    ("ready",         "Ready for review"),
    ("pdf_generated", "PDF generated"),
)

HAS_PDF_CHOICES = (
    ("yes", "Has PDF"),
    ("no",  "No PDF"),
)


def apply_quotation_filters(qs: QuerySet[Quotation], request, user) -> QuerySet[Quotation]:
    """
    Apply workspace filters to an already-scoped queryset.
    Always returns an annotated queryset.
    """
    qs = annotate_workspace(qs)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(reference__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(customer_email__icontains=q)
            | Q(project_name__icontains=q)
            | Q(project_location__icontains=q)
        )

    status = request.GET.get("status", "")
    if status in Quotation.Status.values:
        qs = qs.filter(status=status)

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    if date_from:
        try:
            qs = qs.filter(created_at__date__gte=date_from)
        except (ValueError, ValidationError):
            pass
    if date_to:
        try:
            qs = qs.filter(created_at__date__lte=date_to)
        except (ValueError, ValidationError):
            pass

    has_pdf = request.GET.get("has_pdf", "")
    if has_pdf == "yes":
        qs = qs.filter(ws_pdf_count__gt=0)
    elif has_pdf == "no":
        qs = qs.filter(ws_pdf_count=0)

    readiness = request.GET.get("readiness", "")
    if readiness == "not_started":
        qs = qs.filter(Q(ws_total_sections=0) | Q(ws_configured_sections=0))
    elif readiness == "in_progress":
        qs = qs.filter(
            ws_total_sections__gt=0,
            ws_configured_sections__gt=0,
            ws_configured_sections__lt=F("ws_total_sections"),
            ws_pdf_count=0,
        )
    elif readiness == "ready":
        qs = qs.filter(
            ws_total_sections__gt=0,
            ws_configured_sections=F("ws_total_sections"),
            ws_pdf_count=0,
        )
    elif readiness == "pdf_generated":
        qs = qs.filter(ws_pdf_count__gt=0)

    # Admin-only: filter by rep
    rep_id = request.GET.get("rep", "")
    if rep_id and is_admin(user):
        try:
            qs = qs.filter(created_by_id=int(rep_id))
        except (TypeError, ValueError):
            pass

    return qs


# ---------------------------------------------------------------------------
# Recently viewed (session-backed)
# ---------------------------------------------------------------------------

RECENT_SESSION_KEY = "recent_quotation_ids"
RECENT_MAX = 5


def track_recent_quotation(session, quotation_pk: int) -> None:
    """Push a quotation id onto the session-backed recent list (max 5)."""
    try:
        pk = int(quotation_pk)
    except (TypeError, ValueError):
        return
    raw = session.get(RECENT_SESSION_KEY, [])
    if not isinstance(raw, list):
        raw = []
    ids: list[int] = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if pk in ids:
        ids.remove(pk)
    ids.insert(0, pk)
    session[RECENT_SESSION_KEY] = ids[:RECENT_MAX]
    session.modified = True


def get_recently_viewed_quotations(user, session) -> list[Quotation]:
    """Return Quotation objects the user is allowed to see, in session order."""
    raw = session.get(RECENT_SESSION_KEY, [])
    if not isinstance(raw, list) or not raw:
        return []
    ids_int: list[int] = []
    for x in raw:
        try:
            ids_int.append(int(x))
        except (TypeError, ValueError):
            continue
    if not ids_int:
        return []
    qs = annotate_workspace(scoped_quotations(user)).filter(pk__in=ids_int)
    by_pk = {q.pk: q for q in qs}
    return [by_pk[pk] for pk in ids_int if pk in by_pk]


# ---------------------------------------------------------------------------
# Pinned quotations
# ---------------------------------------------------------------------------

def get_pinned_quotations(user) -> list[Quotation]:
    """Return the user's pinned quotations they still have access to."""
    from .models import QuotationPin
    scoped = scoped_quotations(user)
    pins = (
        QuotationPin.objects
        .filter(user=user, quotation__in=scoped)
        .select_related("quotation", "quotation__created_by")
        .order_by("-created_at")
    )
    quotations = []
    pin_ids = []
    seen = set()
    for pin in pins:
        if pin.quotation_id in seen:
            continue
        seen.add(pin.quotation_id)
        pin_ids.append(pin.quotation_id)
    if not pin_ids:
        return []
    annotated = {
        q.pk: q for q in annotate_workspace(scoped).filter(pk__in=pin_ids)
    }
    return [annotated[pk] for pk in pin_ids if pk in annotated]


def get_pinned_pk_set(user) -> set[int]:
    from .models import QuotationPin
    return set(
        QuotationPin.objects.filter(user=user).values_list("quotation_id", flat=True)
    )
