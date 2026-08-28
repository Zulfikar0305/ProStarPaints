"""Preview service for rendering saved specification drafts.

The PreviewService consumes `ManualSpecificationDraft` data and produces a
template context suitable for HTML preview pages. It deliberately does not
call the `SpecificationResolver` — previews are rendered from the saved
draft JSON only.
"""
from __future__ import annotations

from typing import Any, Dict
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class PreviewService:
    """Service to build render context from a ManualSpecificationDraft."""

    def preview_context_for_draft(self, draft) -> Dict[str, Any]:
        """Return a context dict for preview templates using only draft data.

        If the draft contains a pre-built `pdf_context` (created by the builder)
        use that as the authoritative template context so previews and exports
        render the same document representation.
        """

        data = draft.data or {}

        resolver = data.get("resolver") if isinstance(data, dict) else None
        draft_overrides = data.get("draft_overrides") if isinstance(data, dict) else None
        if isinstance(resolver, dict) and isinstance(draft_overrides, dict):
            try:
                from specifications.services.builder_service import ManualSpecificationBuilderService
                resolver = ManualSpecificationBuilderService().apply_draft_overrides(resolver, draft_overrides)
            except Exception:
                logger.exception("Failed to apply draft overrides for preview")

        from specifications.services.template_service import TemplateService
        report_controls = TemplateService.normalize_report_controls(
            (resolver or {}).get("report_controls") if isinstance(resolver, dict) else None
        )
        if isinstance(draft_overrides, dict) and isinstance(draft_overrides.get("report_controls"), dict):
            report_controls = TemplateService.normalize_report_controls(draft_overrides.get("report_controls"))

        # If the draft contains pre-rendered HTML for templates, prefer that
        rendered_html_map = None
        if isinstance(data, dict) and data.get("rendered_html") and not (resolver and isinstance(draft_overrides, dict) and draft_overrides):
            rendered_html_map = data.get("rendered_html")

        # Optional per-section metadata persisted by the builder
        sections_metadata = None
        if isinstance(data, dict) and data.get("sections_metadata"):
            sections_metadata = data.get("sections_metadata")

        # If the draft contains a PDF-ready context, use it directly
        pdf_ctx = None
        if isinstance(data, dict) and data.get("pdf_context"):
            pdf_ctx = data.get("pdf_context")

        # Branding and logo (best-effort — preview is tolerant)
        try:
            from system_tools.branding import get_branding, get_pdf_logo_data_uri

            branding = get_branding()
            logo_data_uri = get_pdf_logo_data_uri()
        except Exception as exc:
            logger.exception("Failed to load branding for preview: %s", exc)
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
                "sections_metadata": sections_metadata,
                "report_controls": report_controls,
                "report_options": {"pricing_enabled": bool(report_controls.get("show_pricing", True))},
            }
            return ctx

        if pdf_ctx and isinstance(pdf_ctx, dict):
            # Ensure branding/logo and generated timestamp exist
            ctx = dict(pdf_ctx)
            ctx.setdefault("branding", branding)
            ctx.setdefault("logo_data_uri", logo_data_uri)
            ctx.setdefault("generated_at", timezone.now())
            ctx["draft"] = draft
            ctx["report_controls"] = report_controls
            ctx["report_options"] = {"pricing_enabled": bool(report_controls.get("show_pricing", True))}
            # propagate any sections metadata into the preview context
            if sections_metadata is not None:
                ctx.setdefault("sections_metadata", sections_metadata)
            # Apply composition if any metadata defaults or instance
            # overrides are available. Composition is conservative and
            # will leave sections unchanged if no metadata exists.
            try:
                from specifications.services.composer import compose_sections
                from specifications.services.template_service import TemplateService

                tmpl = TemplateService.get_active_template()
                tmpl_defaults = TemplateService.as_dict(tmpl)
                template_sections = tmpl_defaults.get("sections") or []
                # instance metadata comes from sections_metadata variable
                inst_meta = sections_metadata
                sections = ctx.get("sections") or []
                composed = compose_sections(sections, template_sections=template_sections, instance_metadata=inst_meta)
                ctx["sections"] = composed
            except Exception:
                # Keep context unchanged on composition errors
                pass

            return ctx

        # Fallback: construct a minimal preview context from resolver-shaped data
        if isinstance(resolver, dict):
            sections = resolver.get("sections", [])
            template = resolver.get("template", {})
        else:
            sections = data.get("sections", []) if isinstance(data, dict) else []
            template = data.get("template", {})

        context = {
            "draft": draft,
            "quotation": getattr(draft, "quotation", None),
            "template": template,
            "sections": sections,
            "branding": branding,
            "logo_data_uri": logo_data_uri,
            "generated_at": timezone.now(),
            "sections_metadata": sections_metadata,
            "report_controls": report_controls,
            "report_options": {"pricing_enabled": bool(report_controls.get("show_pricing", True))},
        }

        # If any metadata exists, attempt to compose the sections before
        # returning the fallback context.
        try:
            if sections_metadata:
                from specifications.services.composer import compose_sections
                from specifications.services.template_service import TemplateService

                tmpl = TemplateService.get_active_template()
                tmpl_defaults = TemplateService.as_dict(tmpl)
                template_sections = tmpl_defaults.get("sections") or []
                composed = compose_sections(context.get("sections") or [], template_sections=template_sections, instance_metadata=sections_metadata)
                context["sections"] = composed
        except Exception:
            pass

        return context

    def latest_draft_for_quotation(self, quotation, user=None):
        from specifications.models import ManualSpecificationDraft

        qs = ManualSpecificationDraft.objects.filter(quotation=quotation)
        if user is not None:
            qs = qs.filter(created_by=user)
        return qs.order_by("-updated_at").first()
