"""
system_tools.control_center
===========================

Read-only diagnostic services that power the Admin Control Center.

Every function here is a *pure read* on existing data — no writes, no
destructive operations, no pricing logic. Each returns plain Python
dicts/lists so templates stay clean.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from paints.models import Paint
from quotation.models import (
    Quotation,
    QuotationLineItem,
    QuotationPdfExport,
    QuotationSection,
)
from system_tools.models import AppSetting
from users.models import SalesRepProfile, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OK = "ready"
WARN = "warning"
INFO = "info"


def _ok(title: str, hint: str = "", url: str = "") -> dict:
    return {"status": OK, "title": title, "hint": hint, "url": url}


def _warn(title: str, hint: str = "", url: str = "") -> dict:
    return {"status": WARN, "title": title, "hint": hint, "url": url}


def _info(title: str, hint: str = "", url: str = "") -> dict:
    return {"status": INFO, "title": title, "hint": hint, "url": url}


def _logo_exists() -> bool:
    """Best-effort check for a configured branding logo in /static/images/."""
    candidates = [
        "images/prostar-logo.png",
        "images/prostar-logo.jpg",
        "images/prostar-logo.svg",
    ]
    for finder_dir in (settings.STATICFILES_DIRS or []):
        for name in candidates:
            if (Path(finder_dir) / name).exists():
                return True
    # Fallback: app static directory inside project
    base = Path(settings.BASE_DIR) / "static"
    for name in candidates:
        if (base / name).exists():
            return True
    return False


# ---------------------------------------------------------------------------
# 1. Setup health
# ---------------------------------------------------------------------------

def get_setup_health() -> list[dict]:
    checks: list[dict] = []

    # VAT
    if AppSetting.objects.filter(key=AppSetting.VAT_RATE_KEY).exists():
        checks.append(_ok(
            "VAT rate configured",
            "Global tax rate stored in system settings.",
            reverse("system_tools:vat_settings"),
        ))
    else:
        checks.append(_warn(
            "VAT rate not configured",
            "Quotations will compute without a tax rate until this is set.",
            reverse("system_tools:vat_settings"),
        ))

    # At least one active admin
    admin_qs = User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(role="ADMIN")
    )
    if admin_qs.exists():
        checks.append(_ok(
            f"{admin_qs.count()} active admin{'s' if admin_qs.count() != 1 else ''}",
            "System has at least one active admin user.",
            reverse("users:user_list"),
        ))
    else:
        checks.append(_warn(
            "No active admin user",
            "Create or activate an admin so the platform stays manageable.",
            reverse("users:user_list"),
        ))

    # At least one active rep
    rep_count = User.objects.filter(is_active=True, role="REP", is_superuser=False).count()
    if rep_count:
        checks.append(_ok(
            f"{rep_count} active sales rep{'s' if rep_count != 1 else ''}",
            "Reps are ready to capture quotations.",
            reverse("users:user_list"),
        ))
    else:
        checks.append(_warn(
            "No active sales reps",
            "Invite reps so quotations can be created.",
            reverse("users:user_list"),
        ))

    # Paint catalogue
    paint_count = Paint.objects.filter(is_active=True).count()
    if paint_count:
        checks.append(_ok(
            f"{paint_count} active paint{'s' if paint_count != 1 else ''} in catalogue",
            "Catalogue is populated for quotation line items.",
            reverse("paints:paint_list"),
        ))
    else:
        checks.append(_warn(
            "Paint catalogue is empty",
            "Add paints so reps can build quotations.",
            reverse("paints:paint_list"),
        ))

    # At least one quotation
    quote_count = Quotation.objects.count()
    if quote_count:
        checks.append(_ok(
            f"{quote_count} quotation{'s' if quote_count != 1 else ''} on record",
            "Quotation workflow is in use.",
            reverse("quotation:quotation_list"),
        ))
    else:
        checks.append(_info(
            "No quotations yet",
            "Start the first quotation to validate the end-to-end flow.",
            reverse("quotation:quotation_list"),
        ))

    # At least one PDF
    pdf_count = QuotationPdfExport.objects.filter(
        status=QuotationPdfExport.Status.GENERATED
    ).count()
    if pdf_count:
        checks.append(_ok(
            f"{pdf_count} PDF{'s' if pdf_count != 1 else ''} generated",
            "PDF pipeline has produced at least one document.",
            reverse("audit:audit_log_list") + "?module=quotation",
        ))
    else:
        checks.append(_info(
            "No PDFs generated yet",
            "Generate a quotation PDF to validate the export pipeline.",
            reverse("quotation:quotation_list"),
        ))

    # Branding configuration
    try:
        from system_tools.models import BrandingSetting
        bobj = BrandingSetting.load()
    except Exception:
        bobj = None
    branding_url = reverse("system_tools:branding_settings")
    has_uploaded_logo = bool(bobj and bobj.company_logo)
    branding_fields_set = bool(
        bobj and (
            bobj.support_email or bobj.support_phone or bobj.website
            or bobj.pdf_footer_note or bobj.company_tagline
        )
    )
    if has_uploaded_logo and branding_fields_set:
        checks.append(_ok(
            "Branding configured",
            "Custom logo and business details are set.",
            branding_url,
        ))
    elif has_uploaded_logo or branding_fields_set or _logo_exists():
        checks.append(_info(
            "Branding partially configured",
            "Add company logo, contact details and a PDF footer note for a fully branded experience.",
            branding_url,
        ))
    else:
        checks.append(_warn(
            "Branding needs attention",
            "Upload a company logo and fill in contact details for the navbar and PDF templates.",
            branding_url,
        ))

    # User profile completion
    active = User.objects.filter(is_active=True, is_superuser=False)
    total = active.count()
    if total:
        complete = active.exclude(first_name="").exclude(last_name="").exclude(email="").count()
        pct = round(complete / total * 100) if total else 0
        if pct >= 80:
            checks.append(_ok(
                f"User profiles {pct}% complete",
                f"{complete} of {total} active staff have name + email filled.",
                reverse("users:user_list"),
            ))
        else:
            checks.append(_warn(
                f"User profiles {pct}% complete",
                f"Only {complete} of {total} active staff have name + email filled.",
                reverse("users:user_list"),
            ))
    else:
        checks.append(_info(
            "No active non-admin users",
            "No staff profiles to evaluate yet.",
            reverse("users:user_list"),
        ))

    return checks


# ---------------------------------------------------------------------------
# 2. Paint catalogue quality
# ---------------------------------------------------------------------------

def get_paint_catalogue_quality() -> dict:
    paints_url = reverse("paints:paint_list")
    qs = Paint.objects.all()

    active   = qs.filter(is_active=True).count()
    inactive = qs.filter(is_active=False).count()

    missing_price = qs.filter(is_active=True).filter(
        Q(price_excl_vat__isnull=True) | Q(price_excl_vat=0)
        | Q(price_incl_vat__isnull=True) | Q(price_incl_vat=0)
    ).count()

    missing_image = qs.filter(is_active=True).filter(
        Q(image__isnull=True) | Q(image__exact="")
    ).count()

    missing_meta = qs.filter(is_active=True).filter(
        Q(category="") | Q(paint_type="") | Q(base_type="")
    ).count()

    # Possible duplicates: same lower-cased name appearing more than once
    name_counts = (
        qs.values_list("name", flat=True)
    )
    counter = Counter((n or "").strip().lower() for n in name_counts if n)
    duplicate_names = sum(1 for v in counter.values() if v > 1)

    used_paint_ids = set(
        QuotationLineItem.objects.exclude(paint__isnull=True)
        .values_list("paint_id", flat=True)
        .distinct()
    )
    never_used = qs.filter(is_active=True).exclude(pk__in=used_paint_ids).count()

    items = [
        {"label": "Active paints",         "count": active,         "severity": INFO,
         "hint": "Currently visible to reps.",                          "url": paints_url},
        {"label": "Inactive paints",       "count": inactive,       "severity": INFO,
         "hint": "Hidden from quotations but retained for history.",    "url": paints_url + "?is_active=0"},
        {"label": "Missing / zero price",  "count": missing_price,  "severity": WARN if missing_price else OK,
         "hint": "Reps cannot quote these accurately.",                 "url": paints_url},
        {"label": "Missing image",         "count": missing_image,  "severity": WARN if missing_image else OK,
         "hint": "Visual catalogue items show a placeholder.",          "url": paints_url},
        {"label": "Missing category/type/base", "count": missing_meta,  "severity": WARN if missing_meta else OK,
         "hint": "Filters and PDF descriptions are weaker without these.", "url": paints_url},
        {"label": "Possible duplicate names",  "count": duplicate_names, "severity": WARN if duplicate_names else OK,
         "hint": "Same name appears more than once — review for duplicates.", "url": paints_url},
        {"label": "Never used in a quotation", "count": never_used,      "severity": INFO,
         "hint": "Useful to spot stale catalogue entries.",             "url": paints_url},
    ]

    return {"items": items, "total": qs.count(), "url": paints_url}


# ---------------------------------------------------------------------------
# 3. Quotation quality
# ---------------------------------------------------------------------------

def get_quotation_quality() -> dict:
    list_url = reverse("quotation:quotation_list")

    drafts = Quotation.objects.filter(status=Quotation.Status.DRAFT).count()

    # Quotations with no sections at all
    no_sections = Quotation.objects.annotate(
        sec_count=Count("sections")
    ).filter(sec_count=0).count()

    # Quotations that have sections but zero line items
    section_quotation_ids = set(
        QuotationSection.objects.values_list("quotation_id", flat=True).distinct()
    )
    line_quotation_ids = set(
        QuotationLineItem.objects.values_list("quotation_id", flat=True).distinct()
    )
    sections_no_lines = len(section_quotation_ids - line_quotation_ids)

    pdf_quotation_ids = set(
        QuotationPdfExport.objects.filter(
            status=QuotationPdfExport.Status.GENERATED
        ).values_list("quotation_id", flat=True).distinct()
    )
    total_quotations = Quotation.objects.count()
    no_pdf = total_quotations - len(pdf_quotation_ids)

    failed_pdf_quotation_ids = set(
        QuotationPdfExport.objects.filter(
            status=QuotationPdfExport.Status.FAILED
        ).values_list("quotation_id", flat=True).distinct()
    )

    missing_contact = Quotation.objects.filter(
        Q(customer_email="") & Q(customer_phone="")
    ).count()

    missing_location = Quotation.objects.filter(project_location="").count()

    items = [
        {"label": "Draft quotations",                   "count": drafts,
         "severity": INFO if drafts == 0 else WARN,
         "hint": "Drafts awaiting completion.",
         "url": list_url + "?status=DRAFT"},
        {"label": "Quotations with no sections",        "count": no_sections,
         "severity": WARN if no_sections else OK,
         "hint": "Builder was started but no surfaces configured.",
         "url": list_url + "?status=DRAFT"},
        {"label": "Sections but no line items",         "count": sections_no_lines,
         "severity": WARN if sections_no_lines else OK,
         "hint": "Surfaces exist but no paint/prep lines saved.",
         "url": list_url + "?status=DRAFT"},
        {"label": "No generated PDF",                   "count": no_pdf,
         "severity": INFO,
         "hint": "Includes drafts; useful as a backlog indicator.",
         "url": list_url},
        {"label": "Has at least one failed PDF",        "count": len(failed_pdf_quotation_ids),
         "severity": WARN if failed_pdf_quotation_ids else OK,
         "hint": "Investigate template/data issues then re-generate.",
         "url": list_url},
        {"label": "Missing customer contact",           "count": missing_contact,
         "severity": WARN if missing_contact else OK,
         "hint": "No email and no phone captured for the customer.",
         "url": list_url},
        {"label": "Missing project location",           "count": missing_location,
         "severity": WARN if missing_location else OK,
         "hint": "Location is recommended for site-specific quotations.",
         "url": list_url},
    ]

    return {"items": items, "total": total_quotations, "url": list_url}


# ---------------------------------------------------------------------------
# 4. Staff readiness
# ---------------------------------------------------------------------------

def get_staff_readiness() -> dict:
    user_list_url = reverse("users:user_list")
    since = timezone.now() - timedelta(days=30)

    active_reps = User.objects.filter(is_active=True, role="REP", is_superuser=False)
    total_reps = active_reps.count()

    incomplete = active_reps.filter(
        Q(first_name="") | Q(last_name="") | Q(email="")
    ).count()

    # Reps with no audit activity in the last 30 days
    recent_actor_ids = set(
        AuditLog.objects.filter(created_at__gte=since)
        .exclude(user__isnull=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    inactive_recent = active_reps.exclude(pk__in=recent_actor_ids).count()

    rep_ids_with_drafts = set(
        Quotation.objects.filter(status=Quotation.Status.DRAFT)
        .exclude(created_by__isnull=True)
        .values_list("created_by_id", flat=True)
        .distinct()
    )
    with_drafts = active_reps.filter(pk__in=rep_ids_with_drafts).count()

    rep_ids_with_pdfs = set(
        QuotationPdfExport.objects.filter(
            status=QuotationPdfExport.Status.GENERATED
        )
        .exclude(generated_by__isnull=True)
        .values_list("generated_by_id", flat=True)
        .distinct()
    )
    with_pdfs = active_reps.filter(pk__in=rep_ids_with_pdfs).count()

    # Profile completeness on SalesRepProfile (business email/phone)
    missing_business_contact = (
        SalesRepProfile.objects.filter(user__in=active_reps)
        .filter(Q(business_email="") | Q(company_phone=""))
        .count()
    )

    items = [
        {"label": "Active reps",                "count": total_reps,
         "severity": INFO, "hint": "All active rep accounts.", "url": user_list_url},
        {"label": "Incomplete profiles",        "count": incomplete,
         "severity": WARN if incomplete else OK,
         "hint": "Missing name or primary email.",  "url": user_list_url},
        {"label": "No activity in last 30 days", "count": inactive_recent,
         "severity": WARN if inactive_recent else OK,
         "hint": "No audit-tracked actions recorded recently.", "url": user_list_url},
        {"label": "With open drafts",           "count": with_drafts,
         "severity": INFO,
         "hint": "Reps actively building quotations.",
         "url": reverse("quotation:quotation_list") + "?status=DRAFT"},
        {"label": "Have generated PDFs",        "count": with_pdfs,
         "severity": INFO,
         "hint": "Reps who completed at least one PDF export.",
         "url": reverse("quotation:quotation_list")},
        {"label": "Missing business email/phone", "count": missing_business_contact,
         "severity": WARN if missing_business_contact else OK,
         "hint": "Helps customers reach the rep directly on PDFs.",
         "url": user_list_url},
    ]

    return {"items": items, "total": total_reps, "url": user_list_url}


# ---------------------------------------------------------------------------
# 5. PDF export health
# ---------------------------------------------------------------------------

def get_pdf_export_health(latest_limit: int = 8) -> dict:
    since = timezone.now() - timedelta(days=30)
    qs = QuotationPdfExport.objects.select_related("quotation", "generated_by")

    total_generated = qs.filter(status=QuotationPdfExport.Status.GENERATED).count()
    failed_30d = qs.filter(
        status=QuotationPdfExport.Status.FAILED,
        created_at__gte=since,
    ).count()

    latest = list(
        qs.filter(status=QuotationPdfExport.Status.GENERATED)
        .order_by("-created_at")[:latest_limit]
    )

    template_counts = (
        qs.filter(status=QuotationPdfExport.Status.GENERATED)
        .values("template_key")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return {
        "total_generated":  total_generated,
        "failed_30d":       failed_30d,
        "latest":           latest,
        "template_counts":  list(template_counts),
    }


# ---------------------------------------------------------------------------
# 6. Recent system activity
# ---------------------------------------------------------------------------

def get_recent_system_activity(limit: int = 10) -> list[dict]:
    logs = (
        AuditLog.objects.select_related("user")
        .order_by("-created_at")[:limit]
    )
    rows: list[dict[str, Any]] = []
    audit_url = reverse("audit:audit_log_list")
    for log in logs:
        actor = (
            (log.user.get_full_name() or log.user.username)
            if log.user else "System"
        )
        rows.append({
            "id":          log.pk,
            "user":        actor,
            "module":      log.module,
            "action":      log.action,
            "description": log.description,
            "created_at":  log.created_at,
            "url":         f"{audit_url}?q={log.action}",
        })
    return rows
