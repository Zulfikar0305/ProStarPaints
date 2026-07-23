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
        """Return a context dict for preview templates using only draft data."""
        data = draft.data or {}

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

        # Pull sections from draft payload; ensure stable defaults
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
