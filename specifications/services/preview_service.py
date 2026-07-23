"""Preview service for rendering saved specification drafts.

The PreviewService consumes `ManualSpecificationDraft` data and produces a
template context suitable for HTML preview pages. It deliberately does not
call the `SpecificationResolver` — previews are rendered from the saved
draft JSON only.
"""
from __future__ import annotations

from typing import Any, Dict
from django.utils import timezone


class PreviewService:
    """Service to build render context from a ManualSpecificationDraft."""

    def preview_context_for_draft(self, draft) -> Dict[str, Any]:
        """Return a context dict for preview templates using only draft data.

        If the draft contains a pre-built `pdf_context` (created by the builder)
        use that as the authoritative template context so previews and exports
        render the same document representation.
        """

        data = draft.data or {}

        # If the draft contains pre-rendered HTML for templates, prefer that
        rendered_html_map = None
        if isinstance(data, dict) and data.get("rendered_html"):
            rendered_html_map = data.get("rendered_html")

        # If the draft contains a PDF-ready context, use it directly
        pdf_ctx = None
        if isinstance(data, dict) and data.get("pdf_context"):
            pdf_ctx = data.get("pdf_context")

        # Branding and logo (best-effort — preview is tolerant)
        try:
            from system_tools.branding import get_branding, get_pdf_logo_data_uri

            branding = get_branding()
            logo_data_uri = get_pdf_logo_data_uri()
        except Exception:
            branding = {
                "company_name": "ProStar Paints",
                "company_tagline": "",
                "pdf_footer_note": "",
                "support_email": "",
                "support_phone": "",
                "website": "",
            }
            logo_data_uri = None

        if rendered_html_map:
            # Return a minimal context that tells consumers to render the
            # pre-rendered HTML for a chosen template. The preview view will
            # handle selecting the right template HTML.
            ctx = {
                "rendered_html": rendered_html_map,
                "draft": draft,
                "quotation": getattr(draft, "quotation", None),
                "branding": branding,
                "logo_data_uri": logo_data_uri,
                "generated_at": timezone.now(),
            }
            return ctx

        if pdf_ctx and isinstance(pdf_ctx, dict):
            # Ensure branding/logo and generated timestamp exist
            ctx = dict(pdf_ctx)
            ctx.setdefault("branding", branding)
            ctx.setdefault("logo_data_uri", logo_data_uri)
            ctx.setdefault("generated_at", timezone.now())
            ctx["draft"] = draft
            return ctx

        # Fallback: construct a minimal preview context from resolver-shaped data
        sections = data.get("sections", []) if isinstance(data, dict) else []

        context = {
            "draft": draft,
            "quotation": getattr(draft, "quotation", None),
            "template": data.get("template", {}),
            "sections": sections,
            "branding": branding,
            "logo_data_uri": logo_data_uri,
            "generated_at": timezone.now(),
        }

        return context

    def latest_draft_for_quotation(self, quotation, user=None):
        from specifications.models import ManualSpecificationDraft

        qs = ManualSpecificationDraft.objects.filter(quotation=quotation)
        if user is not None:
            qs = qs.filter(created_by=user)
        return qs.order_by("-updated_at").first()
