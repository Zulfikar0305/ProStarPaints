"""
quotation.pdf_service
=====================
All PDF generation logic lives here — views are thin callers.

Public API
----------
  get_pdf_template(template_key)          → dict (raises KeyError on bad key)
  build_pdf_context(quotation, request)   → dict  (context for the HTML template)
  render_quotation_pdf(quotation, ...)    → QuotationPdfExport

Design rules
------------
- This module NEVER raises to callers.  Failures are captured in
  QuotationPdfExport.status = FAILED with error_message.
- Template keys are validated against the registry; arbitrary paths are
  never accepted.
- The logo is embedded as a base64 data-URI so WeasyPrint has no external
  dependencies at render time.
- Pricing is always shown as "pricing pending / TBC" — pricing engine is
  not called here.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template validation
# ---------------------------------------------------------------------------

def get_pdf_template(template_key: str) -> dict:
    """
    Return the validated template config for *template_key*.

    Raises KeyError if the key is not registered.  Callers must handle this
    and present a friendly error; they must NOT fall back to a raw path.
    """
    from .pdf_templates import get_template_config
    return get_template_config(template_key)


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_pdf_context(quotation, request=None) -> dict:
    """
    Assemble all data needed to render any of the PDF templates.

    DB cost: 2 queries (sections + line items).
    Never raises — missing related objects return None/empty values.
    """
    from django.utils import timezone

    from .description_engine import generate_line_item_description
    from .models import QuotationLineItem
    from .services import get_quotation_summary
    from decimal import Decimal

    # ── Line items grouped by section ──────────────────────────────────────
    sections = list(quotation.sections.order_by("sort_order"))
    all_items = list(
        QuotationLineItem.objects
        .filter(quotation=quotation)
        .select_related("section", "paint")
        .order_by("section__sort_order", "pk")
    )

    items_by_section: dict = {}
    for item in all_items:
        items_by_section.setdefault(item.section_id, []).append(item)

    section_data = []
    for section in sections:
        sec_items = items_by_section.get(section.pk, [])
        note_item = next((i for i in sec_items if i.item_type == QuotationLineItem.ItemType.NOTE), None)
        work_items = [i for i in sec_items if i.item_type != QuotationLineItem.ItemType.NOTE]

        # Compute persisted section totals from stored line item totals
        section_total_excl = Decimal("0.00")
        section_total_incl = Decimal("0.00")
        for wi in work_items:
            try:
                section_total_excl += Decimal(wi.total_excl_vat or 0)
            except Exception:
                pass
            try:
                section_total_incl += Decimal(wi.total_incl_vat or 0)
            except Exception:
                pass

        # Collect any images attached to the section and encode as base64 data-URIs
        images_data_uris = []
        try:
            from django.core.files.storage import default_storage
            import mimetypes
            for img in section.images.all():
                try:
                    with default_storage.open(img.image.name, 'rb') as fh:
                        raw = fh.read()
                    mime, _ = mimetypes.guess_type(img.image.name)
                    if not mime:
                        mime = 'image/png'
                    images_data_uris.append('data:%s;base64,%s' % (mime, base64.b64encode(raw).decode()))
                except Exception:
                    # Skip unreadable images silently
                    continue
        except Exception:
            images_data_uris = []

        section_data.append({
            "section":      section,
            "description":  generate_line_item_description(note_item) if note_item else "",
            "note_item":    note_item,
            "line_items": [
                {
                    "item":        item,
                    "description": generate_line_item_description(item),
                }
                for item in work_items
            ],
            "images": images_data_uris,
            # Persisted totals (do not recalculate pricing here)
            "section_total_excl_vat": section_total_excl,
            "section_total_incl_vat": section_total_incl,
        })

    # ── Sales rep profile ──────────────────────────────────────────────────
    sales_profile = None
    try:
        sales_profile = quotation.created_by.sales_profile
    except Exception:
        pass

    # ── Summary ───────────────────────────────────────────────────────────
    summary = get_quotation_summary(quotation)
    # ------------------------------------------------------------------
    # Specification report generation (Pack 5C4.3)
    # Build structured specification objects per section so templates
    # are purely presentation layers.
    try:
        from .spec_report import generate_spec_for_sections
        enriched_sections = generate_spec_for_sections(section_data)
    except Exception:
        enriched_sections = section_data

    # ── Branding (admin-controlled) + logo data URI ───────────────────────
    try:
        from system_tools.branding import get_branding, get_pdf_logo_data_uri
        branding = get_branding()
        logo_data_uri = get_pdf_logo_data_uri()
    except Exception:
        logger.exception("Failed to load branding for PDF; using safe defaults")
        branding = {
            "company_name": "ProStar Paints", "company_tagline": "", "pdf_footer_note": "",
            "support_email": "", "support_phone": "", "website": "",
        }
        logo_data_uri = _load_logo_data_uri()

    return {
        "quotation":          quotation,
        "customer_name":      quotation.customer_name,
        "customer_email":     quotation.customer_email,
        "customer_phone":     quotation.customer_phone,
        "project_name":       quotation.project_name,
        "project_location":   quotation.project_location,
        "created_by":         quotation.created_by,
        "sales_profile":      sales_profile,
        "sections":           enriched_sections,
        "quotation_summary":  summary,
        "pricing_status":     "pending",
        "logo_data_uri":      logo_data_uri,
        "branding":           branding,
        "generated_at":       timezone.now(),
        "notes":              quotation.notes,
    }


# Cache the logo data URI for the lifetime of the process — the logo is a
# static asset that does not change at runtime, so we avoid re-reading and
# re-encoding it on every PDF render. Sentinel object distinguishes "not yet
# loaded" from "loaded but missing" (None).
_LOGO_SENTINEL = object()
_LOGO_DATA_URI_CACHE = _LOGO_SENTINEL


def _load_logo_data_uri() -> str | None:
    """
    Return the ProStar Paints logo as a base64 data-URI, cached after the
    first call. Returns None silently if the file cannot be found or read.
    """
    global _LOGO_DATA_URI_CACHE
    if _LOGO_DATA_URI_CACHE is not _LOGO_SENTINEL:
        return _LOGO_DATA_URI_CACHE

    result: str | None = None
    try:
        from django.contrib.staticfiles.finders import find as static_find
        logo_path = static_find("images/prostar-logo.png")
        if logo_path and os.path.exists(logo_path):
            with open(logo_path, "rb") as fh:
                result = "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except Exception:
        result = None

    _LOGO_DATA_URI_CACHE = result
    return result


# ---------------------------------------------------------------------------
# PDF renderer
# ---------------------------------------------------------------------------

def render_quotation_pdf(
    quotation,
    template_key: str,
    generated_by,
    request=None,
):
    """
    Generate a PDF for *quotation* using the named *template_key*.

    Returns a ``QuotationPdfExport`` instance.  The export is always saved to
    the DB — callers should check ``export.status`` to detect failures.

    Failures are captured; this function does NOT raise.
    """
    from django.core.files.base import ContentFile
    from django.template.loader import render_to_string

    from .models import QuotationPdfExport

    # Create the export record immediately so there's always a row to
    # update even if an early exception occurs.
    export = QuotationPdfExport(
        quotation=quotation,
        generated_by=generated_by,
        template_key=template_key,
        status=QuotationPdfExport.Status.GENERATED,
    )

    try:
        # 1. Validate template key — raises KeyError on unknown key
        template_config = get_pdf_template(template_key)

        # 2. Build rendering context
        context = build_pdf_context(quotation, request=request)

        # 3. Render HTML
        html_string = render_to_string(template_config["template_path"], context)

        # 4. Convert to PDF via WeasyPrint
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_string, base_url=None).write_pdf()

        # 5. Save file to FileField
        filename = f"PSP_Quotation_{quotation.reference}_{template_key}.pdf"
        export.file.save(filename, ContentFile(pdf_bytes), save=False)
        export.status = QuotationPdfExport.Status.GENERATED
        export.save()

    except Exception as exc:
        logger.exception(
            "PDF generation failed for quotation %s (template=%s): %s",
            quotation.reference,
            template_key,
            exc,
        )
        # Provide a short, actionable hint when native WeasyPrint
        # dependencies are missing (common on Windows/dev machines).
        hint = ""
        try:
            msg = str(exc)
            if isinstance(exc, (ImportError, OSError)) or "libgobject" in msg or "WeasyPrint" in msg:
                hint = (
                    "\n\nHint: WeasyPrint requires native libraries (Pango/Cairo). "
                    "On Windows install instructions are here: "
                    "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation"
                )
        except Exception:
            hint = ""

        export.status = QuotationPdfExport.Status.FAILED
        export.error_message = (str(exc) + hint)[:1000]
        export.save()

    return export
