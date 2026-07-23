"""Services for the Manual Specification Builder.

This service is intentionally thin: it reuses the existing
`SpecificationResolver` to produce an initial structured specification
and provides helpers to create and persist user-edited drafts.
"""
from __future__ import annotations

from typing import Any, Dict

from .resolver import SpecificationResolver
import logging

logger = logging.getLogger(__name__)


class ManualSpecificationBuilderService:
    """High-level helper for preparing and persisting manual drafts."""

    def __init__(self):
        self.resolver = SpecificationResolver()

    def prepare_spec(self, quotation) -> Dict[str, Any]:
        """Return the resolver-produced specification dict for *quotation*."""
        return self.resolver.resolve(quotation)

    def create_draft_from_resolver(self, quotation, created_by=None, title: str = "", template_key: str = "detailed_spec"):
        """Create and return a ManualSpecificationDraft populated from resolver output.

        The draft is saved and returned. Caller may further update the draft
        via `save_draft()`.
        """
        # Resolver output (kept for builder/editor use)
        resolved = self.prepare_spec(quotation)

        # Build a PDF-ready enriched context from the quotation without
        # invoking the resolver (we will merge resolved output below).
        try:
            from quotation.pdf_service import build_pdf_context
            # compute enriched sections but do not run resolver here
            pdf_ctx = build_pdf_context(quotation, use_resolver=False)
        except Exception as exc:
            logger.exception("Failed to build pdf_ctx for quotation %s: %s", getattr(quotation, 'pk', None), exc)
            pdf_ctx = {}

        # Merge resolver-provided clauses/product descriptions into the
        # enriched sections so the draft contains the final document model.
        try:
            resolved_sections = (resolved or {}).get("sections", [])
            resolver_by_key = {}
            for rs in resolved_sections:
                resolver_by_key.setdefault(rs.get("section_key"), []).append(rs)

            for sec in (pdf_ctx.get("sections") or []):
                try:
                    section_obj = sec.get("section")
                    sk = getattr(section_obj, "subsection_key", None)
                    lst = resolver_by_key.get(sk) or []
                    rs = lst.pop(0) if lst else None
                    if rs:
                        sec["resolved_clauses"] = rs.get("clauses", [])
                        sec["resolved_product_descriptions"] = rs.get("product_descriptions", [])
                        if rs.get("recommendation"):
                            sec["recommendation"] = rs.get("recommendation")
                except Exception as exc:
                    logger.exception("Error merging resolver section for quotation %s: %s", getattr(quotation, 'pk', None), exc)
                    continue
        except Exception as exc:
            logger.exception("Failed to merge resolver output into pdf_ctx for quotation %s: %s", getattr(quotation, 'pk', None), exc)

        # Render HTML for the default template and store it on the draft so
        # preview and export can use a single canonical document representation.
        rendered_html_map = {}
        try:
            from django.template.loader import render_to_string
            from quotation.pdf_templates import get_template_config

            tpl_cfg = get_template_config(template_key)
            tpl_path = tpl_cfg.get("template_path")
            # Ensure the PDF context contains sections by enriching via
            # generate_spec_for_sections if needed.
            try:
                if not (pdf_ctx and pdf_ctx.get("sections")):
                    from quotation.spec_report import generate_spec_for_sections
                    # build a minimal section_data from resolved output
                    section_data = []
                    for rsec in (resolved or {}).get("sections", []):
                        section_data.append({
                            "section": None,
                            "description": "",
                            "note_item": None,
                            "line_items": [],
                            "images": rsec.get("images", []),
                        })
                    pdf_ctx["sections"] = generate_spec_for_sections(section_data)
            except Exception as exc:
                logger.exception("Failed to ensure pdf_ctx.sections for quotation %s: %s", getattr(quotation, 'pk', None), exc)

            rendered_html_map[template_key] = render_to_string(tpl_path, pdf_ctx)
        except Exception as exc:
            logger.exception("Pre-rendering HTML for quotation %s failed: %s", getattr(quotation, 'pk', None), exc)
            rendered_html_map = {}

        data = {"resolver": resolved, "rendered_html": rendered_html_map}
        # Import model lazily to avoid circular imports during app registry
        from specifications.models import ManualSpecificationDraft

        draft = ManualSpecificationDraft.objects.create(
            quotation=quotation, title=title or "", data=data, created_by=created_by
        )
        return draft

    def save_draft(self, draft, data: Dict[str, Any]):
        """Persist edited draft data (replace entire JSON blob).

        Security: ignore any client-supplied `rendered_html` to ensure only
        server-generated HTML is stored on drafts. Preserve any existing
        server-generated `rendered_html` on the draft.
        """
        # Defensive copy
        incoming = data if isinstance(data, dict) else {}

        # Remove client-supplied rendered_html if present
        if "rendered_html" in incoming:
            logger.warning("Ignoring client-supplied rendered_html for draft save (draft=%s, quotation=%s)", getattr(draft, 'pk', None), getattr(draft, 'quotation', None) and getattr(draft.quotation, 'pk', None))
            incoming = dict(incoming)
            incoming.pop("rendered_html", None)

        # Preserve existing server-generated rendered_html if present
        existing = (draft.data or {}) if getattr(draft, 'data', None) else {}
        existing_rendered = existing.get("rendered_html") if isinstance(existing, dict) else None
        if existing_rendered and isinstance(existing_rendered, dict):
            incoming = dict(incoming)
            # Do not overwrite if client provided (we removed client values above)
            incoming.setdefault("rendered_html", existing_rendered)

        draft.data = incoming
        draft.save()
        return draft

    def latest_draft_for_user(self, quotation, user):
        from specifications.models import ManualSpecificationDraft

        return (
            ManualSpecificationDraft.objects.filter(quotation=quotation, created_by=user)
            .order_by("-updated_at")
            .first()
        )
