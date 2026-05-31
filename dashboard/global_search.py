"""
dashboard.global_search
=======================

Cross-app search service powering the Global Search Center and the
command-palette "Search everything" command.

Permission rules:
- Quotations & PDF exports → reps see only their own; admins see all.
- Paints, Users, Audit logs → admins/superusers only.

No mutations, no destructive ops. Every helper returns plain dicts so
templates stay logic-free.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from django.db.models import Q
from django.urls import reverse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_admin(user) -> bool:
    return bool(user and (user.is_superuser or getattr(user, "role", None) == "ADMIN"))


@dataclass
class SearchResult:
    type: str           # "quotation" | "paint" | "user" | "pdf" | "audit"
    label: str
    subtitle: str = ""
    icon: str = "bi-search"
    url: str = ""
    badge: str = ""
    timestamp: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchGroup:
    type: str
    label: str
    icon: str
    results: list = field(default_factory=list)
    total: int = 0

    def as_dict(self) -> dict:
        return {
            "type":    self.type,
            "label":   self.label,
            "icon":    self.icon,
            "results": [r.as_dict() for r in self.results],
            "total":   self.total,
            "more":    max(0, self.total - len(self.results)),
        }


# ---------------------------------------------------------------------------
# Source searchers
# ---------------------------------------------------------------------------

def _search_quotations(user, q: str, limit: int) -> SearchGroup:
    from quotation.models import Quotation
    from quotation.workspace import scoped_quotations

    qs = (
        scoped_quotations(user)
        .filter(
            Q(reference__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(customer_email__icontains=q)
            | Q(project_name__icontains=q)
            | Q(project_location__icontains=q)
        )
        .order_by("-updated_at")
    )
    total = qs.count()
    results = []
    for quotation in qs[:limit]:
        subtitle_bits = [
            quotation.customer_name,
            quotation.project_name,
            quotation.project_location,
        ]
        subtitle = " · ".join(b for b in subtitle_bits if b)
        results.append(SearchResult(
            type="quotation",
            label=quotation.reference,
            subtitle=subtitle or "—",
            icon="bi-file-earmark-text",
            url=reverse("quotation:quotation_detail", args=[quotation.pk]),
            badge=quotation.get_status_display(),
            timestamp=quotation.updated_at.isoformat() if quotation.updated_at else None,
        ))
    return SearchGroup(
        type="quotation",
        label="Quotations",
        icon="bi-file-earmark-text",
        results=results,
        total=total,
    )


def _search_pdfs(user, q: str, limit: int) -> SearchGroup:
    from quotation.models import QuotationPdfExport
    from quotation.workspace import scoped_quotations

    base = QuotationPdfExport.objects.select_related("quotation", "generated_by")
    if not _is_admin(user):
        base = base.filter(quotation__in=scoped_quotations(user))

    qs = base.filter(
        Q(quotation__reference__icontains=q)
        | Q(template_key__icontains=q)
        | Q(quotation__customer_name__icontains=q)
    ).order_by("-created_at")

    total = qs.count()
    results = []
    for exp in qs[:limit]:
        url = (
            reverse("quotation:pdf_download", args=[exp.pk])
            if exp.file
            else reverse("quotation:quotation_detail", args=[exp.quotation_id])
        )
        results.append(SearchResult(
            type="pdf",
            label=f"{exp.quotation.reference} — {exp.template_key}",
            subtitle=exp.quotation.customer_name or "—",
            icon="bi-file-earmark-pdf",
            url=url,
            badge=exp.get_status_display(),
            timestamp=exp.created_at.isoformat() if exp.created_at else None,
        ))
    return SearchGroup(
        type="pdf",
        label="PDF Exports",
        icon="bi-file-earmark-pdf",
        results=results,
        total=total,
    )


def _search_paints(user, q: str, limit: int) -> SearchGroup:
    from paints.models import Paint

    qs = Paint.objects.filter(
        Q(name__icontains=q)
        | Q(category__icontains=q)
        | Q(paint_type__icontains=q)
        | Q(base_type__icontains=q)
    ).order_by("-is_active", "name")

    total = qs.count()
    results = []
    for paint in qs[:limit]:
        subtitle = " · ".join(
            v for v in [paint.get_category_display() if hasattr(paint, "get_category_display") else paint.category,
                        paint.paint_type, paint.base_type] if v
        )
        results.append(SearchResult(
            type="paint",
            label=paint.name,
            subtitle=subtitle or "—",
            icon="bi-palette",
            url=reverse("paints:paint_update", args=[paint.pk]),
            badge="Active" if paint.is_active else "Inactive",
        ))
    return SearchGroup(
        type="paint",
        label="Paints",
        icon="bi-palette",
        results=results,
        total=total,
    )


def _search_users(user, q: str, limit: int) -> SearchGroup:
    from django.contrib.auth import get_user_model
    User = get_user_model()

    qs = User.objects.filter(
        Q(username__icontains=q)
        | Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(email__icontains=q)
    ).order_by("-is_active", "username")

    total = qs.count()
    results = []
    for u in qs[:limit]:
        full = u.get_full_name() or u.username
        results.append(SearchResult(
            type="user",
            label=full,
            subtitle=u.email or u.username,
            icon="bi-person-circle",
            url=reverse("users:user_update", args=[u.pk]),
            badge=getattr(u, "role", "") or ("Superuser" if u.is_superuser else ""),
        ))
    return SearchGroup(
        type="user",
        label="Users",
        icon="bi-people",
        results=results,
        total=total,
    )


def _search_audit(user, q: str, limit: int) -> SearchGroup:
    from audit.models import AuditLog

    qs = AuditLog.objects.select_related("user").filter(
        Q(action__icontains=q)
        | Q(module__icontains=q)
        | Q(description__icontains=q)
    ).order_by("-created_at")

    total = qs.count()
    results = []
    audit_url = reverse("audit:audit_log_list")
    for log in qs[:limit]:
        who = log.user.get_full_name() if log.user else "system"
        results.append(SearchResult(
            type="audit",
            label=log.action,
            subtitle=f"{log.module} · {who}",
            icon="bi-clock-history",
            url=f"{audit_url}?q={log.action}",
            badge=log.module,
            timestamp=log.created_at.isoformat() if log.created_at else None,
        ))
    return SearchGroup(
        type="audit",
        label="Audit Logs",
        icon="bi-clock-history",
        results=results,
        total=total,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def global_search(user, query: str, limit: int = 8) -> dict:
    """
    Run permission-aware search across every source available to ``user``.

    Returns:
        {
            "query":      str,
            "is_admin":   bool,
            "groups":     [SearchGroup.as_dict()],
            "total":      int,
        }
    """
    q = (query or "").strip()
    if not q:
        return {"query": "", "is_admin": _is_admin(user), "groups": [], "total": 0}

    # Hard caps so a runaway "%a%" can't tank the page
    limit = max(1, min(int(limit or 8), 25))

    groups: list[SearchGroup] = []

    # Available to everyone (rep-scoped where appropriate)
    groups.append(_search_quotations(user, q, limit))
    groups.append(_search_pdfs(user, q, limit))

    # Admin-only sources
    if _is_admin(user):
        groups.append(_search_paints(user, q, limit))
        groups.append(_search_users(user, q, limit))
        groups.append(_search_audit(user, q, limit))

    total = sum(g.total for g in groups)
    return {
        "query":    q,
        "is_admin": _is_admin(user),
        "groups":   [g.as_dict() for g in groups],
        "total":    total,
    }
