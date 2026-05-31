"""
quotation.preflight
===================

Read-only quality / completeness checks run before generating a customer PDF.

`get_quotation_preflight(quotation)` returns a structured result that powers:
- the Quotation Readiness panel on the review page
- the preflight banner on the PDF template select page
- the "needs attention" widget on the dashboard

Design rules
------------
- Pure read. Never writes, never raises (defensive try/except around any
  metadata.get() so a corrupt JSON value can't break the review page).
- Does NOT call pricing logic. The "pricing pending" check is just a
  reminder banner — pricing engine is intentionally not built yet.
- The only `fail` (blocking) condition is "no sections selected at all".
  Everything else is a warning that the rep can dismiss / proceed past.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from .config import MOISTURE_WARNING_THRESHOLD
from .models import Quotation, QuotationLineItem, QuotationPdfExport, QuotationSection


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

OK   = "ok"        # green — check passed
WARN = "warning"   # amber — non-blocking issue
FAIL = "fail"      # red   — blocking issue

OVERALL_READY      = "READY"       # all green (+ optional info)
OVERALL_WARNING    = "WARNING"     # has warnings, no blockers
OVERALL_INCOMPLETE = "INCOMPLETE"  # has at least one fail


def _check(label: str, status: str, message: str, action_url: str = "") -> dict:
    return {"label": label, "status": status, "message": message, "action_url": action_url}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_quotation_preflight(quotation: Quotation) -> dict[str, Any]:
    """
    Return preflight results for *quotation*.

    Shape:
        {
            "status": "READY" | "WARNING" | "INCOMPLETE",
            "score":   0..100,                  # % of checks that are OK
            "checks":  [ {label, status, message, action_url}, ... ],
            "counts":  {"ok": int, "warning": int, "fail": int},
            "can_generate_pdf": bool,           # False only when truly unsafe
            "has_pdf":          bool,
            "summary":          str,            # one-line headline
        }
    """
    builder_url = reverse("quotation:quotation_builder", args=[quotation.pk])
    sections_url = reverse("quotation:quotation_sections", args=[quotation.pk])
    profile_url = reverse("users:profile")

    sections = list(quotation.sections.all().order_by("sort_order"))
    section_ids = [s.pk for s in sections]
    all_items = list(
        QuotationLineItem.objects.filter(quotation=quotation).select_related("section")
    )
    items_by_section: dict = {}
    for li in all_items:
        items_by_section.setdefault(li.section_id, []).append(li)

    note_type = QuotationLineItem.ItemType.NOTE

    checks: list[dict] = []

    # ── 1. Customer name ───────────────────────────────────────────────────
    if (quotation.customer_name or "").strip():
        checks.append(_check(
            "Customer name", OK, "Customer name is set.",
        ))
    else:
        checks.append(_check(
            "Customer name", WARN, "Add the customer's name so the PDF is properly addressed.",
            builder_url,
        ))

    # ── 2. Customer email or phone ─────────────────────────────────────────
    if (quotation.customer_email or "").strip() or (quotation.customer_phone or "").strip():
        checks.append(_check(
            "Customer contact", OK, "Customer email or phone is on file.",
        ))
    else:
        checks.append(_check(
            "Customer contact", WARN,
            "No email or phone captured — you won't be able to follow up easily.",
            builder_url,
        ))

    # ── 3. Project name ────────────────────────────────────────────────────
    if (quotation.project_name or "").strip():
        checks.append(_check(
            "Project name", OK, "Project name is set.",
        ))
    else:
        checks.append(_check(
            "Project name", WARN, "Add a project name to help the customer identify this quote.",
            builder_url,
        ))

    # ── 4. Project location ────────────────────────────────────────────────
    if (quotation.project_location or "").strip():
        checks.append(_check(
            "Project location", OK, "Project location is set.",
        ))
    else:
        checks.append(_check(
            "Project location", WARN, "Add a site address or area for site-specific quotations.",
            builder_url,
        ))

    # ── 5. At least one section selected ───────────────────────────────────
    total_sections = len(sections)
    if total_sections == 0:
        checks.append(_check(
            "Sections", FAIL,
            "No surfaces selected. Pick at least one section before generating a PDF.",
            sections_url,
        ))
    else:
        checks.append(_check(
            "Sections", OK,
            f"{total_sections} section{'s' if total_sections != 1 else ''} selected.",
        ))

    # ── 6. All selected sections configured (have at least one item) ──────
    if total_sections:
        configured_ids = {
            sec_id for sec_id, items in items_by_section.items() if items
        }
        unconfigured = [s for s in sections if s.pk not in configured_ids]
        if unconfigured:
            names = ", ".join(s.display_name for s in unconfigured[:3])
            if len(unconfigured) > 3:
                names += f" +{len(unconfigured) - 3} more"
            checks.append(_check(
                "Section configuration", WARN,
                f"{len(unconfigured)} section{'s' if len(unconfigured) != 1 else ''} still need work: {names}.",
                builder_url,
            ))
        else:
            checks.append(_check(
                "Section configuration", OK, "All selected sections are configured.",
            ))

    # ── 7. At least one non-note line item exists ──────────────────────────
    non_note_count = sum(
        1 for li in all_items if li.item_type != note_type
    )
    if total_sections and non_note_count == 0:
        checks.append(_check(
            "Line items", WARN,
            "No paint / prep / primer line items yet — the PDF will look empty.",
            builder_url,
        ))
    elif total_sections:
        checks.append(_check(
            "Line items", OK,
            f"{non_note_count} work line{'s' if non_note_count != 1 else ''} captured.",
        ))

    # ── 8. High-moisture warnings (info-amber, not blocking) ───────────────
    moisture_hits: list[str] = []
    for sec in sections:
        sec_items = items_by_section.get(sec.pk, [])
        note = next((li for li in sec_items if li.item_type == note_type), None)
        if not note:
            continue
        try:
            lvl = int((note.metadata or {}).get("moisture_level") or 0)
        except (ValueError, TypeError):
            lvl = 0
        if lvl > MOISTURE_WARNING_THRESHOLD:
            moisture_hits.append(f"{sec.display_name} ({lvl}%)")

    if moisture_hits:
        names = ", ".join(moisture_hits[:3])
        if len(moisture_hits) > 3:
            names += f" +{len(moisture_hits) - 3} more"
        checks.append(_check(
            "Moisture levels", WARN,
            f"High moisture flagged on: {names}. Allow surfaces to dry before painting.",
            builder_url,
        ))
    elif total_sections:
        checks.append(_check(
            "Moisture levels", OK, "No high-moisture flags raised.",
        ))

    # ── 9. Sales rep profile complete enough for PDF signature ────────────
    profile_check = _check_rep_profile(quotation, profile_url)
    if profile_check:
        checks.append(profile_check)

    # ── 10. PDF already generated? (info only) ────────────────────────────
    has_pdf = QuotationPdfExport.objects.filter(
        quotation=quotation,
        status=QuotationPdfExport.Status.GENERATED,
    ).exists()
    if has_pdf:
        checks.append(_check(
            "PDF history", OK,
            "A PDF has already been generated for this quotation.",
        ))

    # ── 11. Pricing pending notice (informational, always shown) ──────────
    checks.append(_check(
        "Pricing", WARN,
        "Pricing engine is not active yet — totals will display as TBC on the PDF.",
    ))

    # ── Aggregate ─────────────────────────────────────────────────────────
    counts = {
        "ok":      sum(1 for c in checks if c["status"] == OK),
        "warning": sum(1 for c in checks if c["status"] == WARN),
        "fail":    sum(1 for c in checks if c["status"] == FAIL),
    }
    total = len(checks)
    score = round(counts["ok"] / total * 100) if total else 0

    if counts["fail"]:
        overall = OVERALL_INCOMPLETE
    elif counts["warning"]:
        overall = OVERALL_WARNING
    else:
        overall = OVERALL_READY

    can_generate_pdf = counts["fail"] == 0

    if overall == OVERALL_READY:
        summary = "All checks passed. This quotation is ready to send."
    elif overall == OVERALL_WARNING:
        summary = (
            f"{counts['warning']} item{'s' if counts['warning'] != 1 else ''} need review. "
            "You can still generate a PDF."
        )
    else:
        summary = (
            f"{counts['fail']} blocker{'s' if counts['fail'] != 1 else ''} — "
            "resolve before generating a PDF."
        )

    return {
        "status":            overall,
        "score":             score,
        "checks":            checks,
        "counts":            counts,
        "can_generate_pdf":  can_generate_pdf,
        "has_pdf":           has_pdf,
        "summary":           summary,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_rep_profile(quotation: Quotation, profile_url: str) -> dict | None:
    """
    Check the quotation owner has enough profile data to render a credible
    signature block. Returns None if there's no owner at all (defensive).
    """
    owner = getattr(quotation, "created_by", None)
    if owner is None:
        return None

    full_name = (owner.get_full_name() or "").strip()
    try:
        profile = owner.sales_profile
    except Exception:
        profile = None

    sig_name      = (getattr(profile, "signature_name", "") or "").strip() if profile else ""
    business_mail = (getattr(profile, "business_email", "") or "").strip() if profile else ""
    company_phone = (getattr(profile, "company_phone", "") or "").strip() if profile else ""

    has_name    = bool(sig_name or full_name)
    has_contact = bool(business_mail or company_phone or (owner.email or "").strip())

    if has_name and has_contact:
        return _check(
            "Rep profile", OK,
            "Your profile has enough detail for a professional signature block.",
        )

    missing = []
    if not has_name:
        missing.append("signature name")
    if not has_contact:
        missing.append("business email or phone")
    return _check(
        "Rep profile", WARN,
        "Profile is missing " + " and ".join(missing) + " — the PDF signature block will look bare.",
        profile_url,
    )


# ---------------------------------------------------------------------------
# Bulk helper for "needs attention" widgets
# ---------------------------------------------------------------------------

def get_quotations_needing_attention(queryset, limit: int = 5) -> list[dict]:
    """
    Return up to *limit* quotations from *queryset* whose preflight status is
    WARNING or INCOMPLETE. Skips COMPLETED quotations and quotations that
    already have a generated PDF.

    Callers must pre-scope the queryset for permissions. Order is preserved
    (caller decides ordering — usually -updated_at).
    """
    results: list[dict] = []
    candidates = (
        queryset.exclude(status=Quotation.Status.COMPLETED)
        .order_by("-updated_at")[: limit * 4]
    )
    for q in candidates:
        if q.pdf_exports.filter(status=QuotationPdfExport.Status.GENERATED).exists():
            continue
        pf = get_quotation_preflight(q)
        if pf["status"] in (OVERALL_WARNING, OVERALL_INCOMPLETE):
            results.append({"quotation": q, "preflight": pf})
        if len(results) >= limit:
            break
    return results
