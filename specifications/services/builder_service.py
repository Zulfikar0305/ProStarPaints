"""Services for the Manual Specification Builder.

This service is intentionally thin: it reuses the existing
`SpecificationResolver` to produce an initial structured specification
and provides helpers to create and persist user-edited drafts.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Iterable

from .resolver import SpecificationResolver

logger = logging.getLogger(__name__)


class ManualSpecificationBuilderService:
    """High-level helper for preparing and persisting manual drafts."""

    def __init__(self):
        self.resolver = SpecificationResolver()

    def _section_key(self, section: Dict[str, Any] | Any, index: int = 0) -> str:
        if isinstance(section, dict):
            key = section.get("section_key")
            if key is not None:
                return str(key)
            name = section.get("section_name")
            if name:
                return str(name)
            return f"section_{index}"
        key = getattr(section, "subsection_key", None)
        if key is not None:
            return str(key)
        name = getattr(section, "section_name", None)
        if name:
            return str(name)
        return f"section_{index}"

    def _block_id(self, block: Dict[str, Any] | Any) -> str:
        if isinstance(block, dict):
            resolved = block.get("resolved_id")
            if resolved:
                return str(resolved)
            block_type = block.get("block_type") or "block"
            pk = block.get("pk")
            if pk is not None:
                return f"{block_type}:{pk}"
            title = block.get("title") or block.get("content") or ""
            return f"{block_type}:{title}"

        resolved = getattr(block, "resolved_id", None)
        if resolved:
            return str(resolved)
        block_type = getattr(block, "block_type", "block")
        pk = getattr(block, "pk", None)
        if pk is not None:
            return f"{block_type}:{pk}"
        title = getattr(block, "title", None) or getattr(block, "content", None) or ""
        return f"{block_type}:{title}"

    def prepare_spec(self, quotation) -> Dict[str, Any]:
        """Return the resolver-produced specification dict for *quotation*."""
        return self.resolver.resolve(quotation)

    def extract_draft_overrides(self, base_spec: Dict[str, Any], edited_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Return the serializable draft-level differences between resolver data and edited data.

        The resolver payload remains the source-of-truth; the returned dict stores only
        presentation edits such as section ordering, block visibility, heading overrides,
        editable content changes and report-control toggles. Non-editable source blocks are ignored.
        """
        from specifications.services.template_service import TemplateService

        base_spec = base_spec or {}
        edited_spec = edited_spec or {}

        pricing_visible = edited_spec.get("pricing_visible", base_spec.get("pricing_visible", True))
        defaults = TemplateService.normalize_report_controls(base_spec.get("report_controls"))
        edited_controls = edited_spec.get("report_controls") if isinstance(edited_spec.get("report_controls"), dict) else {}
        base_controls = base_spec.get("report_controls") if isinstance(base_spec.get("report_controls"), dict) else {}
        normalized_base = defaults.copy()
        normalized_base.update(base_controls)
        normalized_edited = defaults.copy()
        normalized_edited.update(base_controls)
        normalized_edited.update(edited_controls)
        control_overrides = {}
        for key, default_value in defaults.items():
            base_value = bool(normalized_base.get(key, default_value))
            edited_value = bool(normalized_edited.get(key, default_value))
            if base_value != edited_value:
                control_overrides[key] = edited_value

        overrides: Dict[str, Any] = {
            "pricing_visible": bool(pricing_visible),
            "sections": {},
            "report_controls": control_overrides,
        }

        base_sections = base_spec.get("sections") or []
        edited_sections = edited_spec.get("sections") or []

        for idx, base_section in enumerate(base_sections):
            sec_key = self._section_key(base_section, idx)
            edited_section = edited_sections[idx] if idx < len(edited_sections) else {}
            if not isinstance(edited_section, dict):
                edited_section = {}

            section_blocks = edited_section.get("blocks") or []
            order = [self._block_id(block) for block in section_blocks]
            block_visibility = {}
            title_overrides: Dict[str, Any] = {}
            content_overrides: Dict[str, Any] = {}
            heading_override = None

            if isinstance(base_section, dict):
                base_name = base_section.get("section_name")
                edited_name = edited_section.get("section_name", base_name)
                if base_name != edited_name:
                    heading_override = edited_name

            base_blocks = base_section.get("blocks") or [] if isinstance(base_section, dict) else []
            edited_block_map = {self._block_id(block): block for block in section_blocks if self._block_id(block)}

            for base_block in base_blocks:
                bid = self._block_id(base_block)
                edited_block = edited_block_map.get(bid)
                if edited_block is None:
                    continue

                base_visible = base_block.get("visible", True)
                edited_visible = edited_block.get("visible", base_visible)
                if base_visible != edited_visible:
                    block_visibility[bid] = bool(edited_visible)

                if (
                    base_block.get("editable", False)
                    or base_block.get("block_type") in {"heading", "product_description", "image"}
                ):
                    if base_block.get("title") != edited_block.get("title"):
                        title_overrides[bid] = edited_block.get("title")
                    if base_block.get("content") != edited_block.get("content"):
                        content_overrides[bid] = edited_block.get("content")

            section_override = {
                "order": order,
                "visible": block_visibility,
                "title_overrides": title_overrides,
                "content_overrides": content_overrides,
            }
            if heading_override is not None:
                section_override["heading_override"] = heading_override
            overrides["sections"][sec_key] = section_override

        return overrides

    def _sync_section_legacy_arrays(self, section: Dict[str, Any]) -> Dict[str, Any]:
        """Keep legacy section arrays in sync with the canonical block list.

        Preview and PDF templates still consume `clauses`, `product_descriptions`,
        `images`, and `knowledge_matches`. If a block is hidden/edited in the draft,
        the legacy arrays must reflect that saved state.
        """
        if not isinstance(section, dict):
            return section

        blocks = section.get("blocks") or []
        visible_blocks = [b for b in blocks if b.get("visible", True) is not False]

        heading_block = next((b for b in visible_blocks if b.get("block_type") == "heading"), None)
        if isinstance(heading_block, dict):
            heading_title = heading_block.get("title")
            if heading_title is not None:
                section["section_name"] = heading_title

        section["clauses"] = [
            {
                "pk": b.get("pk"),
                "title": b.get("title"),
                "body": b.get("content"),
                "category": (b.get("metadata") or {}).get("category"),
            }
            for b in visible_blocks if b.get("block_type") == "clause"
        ]

        section["product_descriptions"] = [
            {
                "item_type": (b.get("metadata") or {}).get("item_type"),
                "product_name": b.get("title"),
                "description": b.get("content"),
                "product_pk": b.get("pk"),
                "product_group": (b.get("metadata") or {}).get("product_group"),
            }
            for b in visible_blocks if b.get("block_type") == "product_description"
        ]

        section["images"] = [
            {"url": b.get("content"), "sort_order": (b.get("metadata") or {}).get("sort_order")}
            for b in visible_blocks if b.get("block_type") == "image" and b.get("content")
        ]

        section["knowledge_matches"] = [
            {
                "pk": b.get("pk"),
                "title": b.get("title"),
                "body": b.get("content"),
                "priority": (b.get("metadata") or {}).get("priority"),
                "score": (b.get("metadata") or {}).get("score"),
                "reason": (b.get("metadata") or {}).get("reason"),
                "matched_conditions": (b.get("metadata") or {}).get("matched_conditions"),
            }
            for b in visible_blocks if b.get("block_type") == "knowledge"
        ]

        return section

    def apply_draft_overrides(self, base_spec: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Return a shallow copy of *base_spec* with draft-level overrides applied."""
        from specifications.services.template_service import TemplateService

        if not isinstance(base_spec, dict):
            return base_spec

        result = copy.deepcopy(base_spec)
        overrides = overrides or {}

        pricing_visible = overrides.get("pricing_visible", result.get("pricing_visible", True))
        result["pricing_visible"] = bool(pricing_visible)

        base_controls = result.get("report_controls") if isinstance(result.get("report_controls"), dict) else {}
        merged_controls = TemplateService.normalize_report_controls(base_controls)
        override_controls = overrides.get("report_controls") if isinstance(overrides.get("report_controls"), dict) else {}
        for key, value in override_controls.items():
            if key in merged_controls:
                merged_controls[key] = bool(value)
        result["report_controls"] = merged_controls

        section_overrides = overrides.get("sections") or {}
        for idx, section in enumerate(result.get("sections") or []):
            sec_key = self._section_key(section, idx)
            section_override = section_overrides.get(sec_key)
            if section_override is None and str(idx) in section_overrides:
                section_override = section_overrides.get(str(idx))
            if not isinstance(section_override, dict):
                # Preserve any live legacy arrays already present on the
                # resolver payload unless there are actual blocks to reconcile.
                blocks = section.get("blocks") or []
                has_legacy_arrays = any(
                    section.get(key)
                    for key in ("clauses", "product_descriptions", "images", "knowledge_matches")
                )
                if blocks or not has_legacy_arrays:
                    self._sync_section_legacy_arrays(section)
                continue

            heading_override = section_override.get("heading_override")
            if heading_override is not None:
                section["section_name"] = heading_override

            if isinstance(section_override.get("visible"), dict):
                for block in section.get("blocks") or []:
                    block_id = self._block_id(block)
                    if block_id in section_override["visible"]:
                        block["visible"] = bool(section_override["visible"][block_id])

            title_overrides = section_override.get("title_overrides") or {}
            if isinstance(title_overrides, dict):
                for block in section.get("blocks") or []:
                    block_id = self._block_id(block)
                    if block_id in title_overrides:
                        block["title"] = title_overrides[block_id]

            content_overrides = section_override.get("content_overrides") or {}
            if isinstance(content_overrides, dict):
                for block in section.get("blocks") or []:
                    block_id = self._block_id(block)
                    if block_id in content_overrides:
                        block["content"] = content_overrides[block_id]

            order = section_override.get("order") or []
            if isinstance(order, list) and order:
                original_blocks = list(section.get("blocks") or [])
                lookup = {self._block_id(block): block for block in original_blocks}
                ordered = []
                seen = set()
                for block_id in order:
                    block = lookup.get(block_id)
                    if block is not None and block_id not in seen:
                        ordered.append(block)
                        seen.add(block_id)
                for block in original_blocks:
                    block_id = self._block_id(block)
                    if block_id not in seen:
                        ordered.append(block)
                section["blocks"] = ordered

            self._sync_section_legacy_arrays(section)

        return result

    def create_draft_from_resolver(self, quotation, created_by=None, title: str = "", template_key: str = "manual_specification"):
        """Create and return a ManualSpecificationDraft populated from resolver output.

        The draft is saved and returned. Caller may further update the draft
        via `save_draft()`.
        """
        resolved = self.prepare_spec(quotation)

        try:
            from quotation.pdf_service import build_pdf_context
            pdf_ctx = build_pdf_context(quotation, use_resolver=False)
        except Exception as exc:
            logger.exception("Failed to build pdf_ctx for quotation %s: %s", getattr(quotation, 'pk', None), exc)
            pdf_ctx = {}

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
                        sec["resolved_knowledge"] = rs.get("knowledge_matches", [])
                        sec["resolved_blocks"] = rs.get("blocks", [])
                        sec["resolved_id"] = rs.get("resolved_id")
                        if rs.get("recommendation"):
                            sec["recommendation"] = rs.get("recommendation")
                except Exception as exc:
                    logger.exception("Error merging resolver section for quotation %s: %s", getattr(quotation, 'pk', None), exc)
                    continue
        except Exception as exc:
            logger.exception("Failed to merge resolver output into pdf_ctx for quotation %s: %s", getattr(quotation, 'pk', None), exc)

        sections_metadata = []
        try:
            for sec in (pdf_ctx.get("sections") or []):
                section_obj = sec.get("section")
                sk = getattr(section_obj, "subsection_key", None) if section_obj is not None else sec.get("section_key")
                meta = {
                    "resolved_id": sec.get("resolved_id"),
                    "section_key": sk,
                    "type": "section",
                    "order": getattr(section_obj, "sort_order", None) if section_obj is not None else None,
                    "visible": True,
                    "heading": None,
                    "bindings": {},
                    "notes": None,
                    "images": sec.get("images") or [],
                    "metadata": {},
                }
                sections_metadata.append(meta)
        except Exception:
            sections_metadata = []

        rendered_html_map = {}
        try:
            from django.template.loader import render_to_string
            from quotation.pdf_templates import get_template_config

            tpl_cfg = get_template_config(template_key)
            tpl_path = tpl_cfg.get("template_path")
            try:
                if not (pdf_ctx and pdf_ctx.get("sections")):
                    from quotation.spec_report import generate_spec_for_sections
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

        try:
            from specifications.services.composer import compose_sections
            from specifications.services.template_service import TemplateService

            tmpl = TemplateService.get_active_template(template_key)
            tmpl_defaults = TemplateService.as_dict(tmpl)
            template_sections = tmpl_defaults.get("sections") or []
            pdf_ctx_sections = pdf_ctx.get("sections") if isinstance(pdf_ctx, dict) else None
            if pdf_ctx_sections:
                composed_sections = compose_sections(pdf_ctx_sections, template_sections=template_sections, instance_metadata=sections_metadata)
                pdf_ctx["sections"] = composed_sections
        except Exception:
            pass

        from specifications.services.template_service import TemplateService

        data = {
            "resolver": resolved,
            "draft_overrides": {
                "pricing_visible": True,
                "sections": {},
                "report_controls": TemplateService.normalize_report_controls((resolved or {}).get("report_controls")),
            },
            "rendered_html": rendered_html_map,
            "sections_metadata": sections_metadata,
        }

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
        incoming = data if isinstance(data, dict) else {}

        if "rendered_html" in incoming:
            logger.warning(
                "Ignoring client-supplied rendered_html for draft save (draft=%s, quotation=%s)",
                getattr(draft, 'pk', None),
                getattr(draft, 'quotation', None) and getattr(draft.quotation, 'pk', None),
            )
            incoming = dict(incoming)
            incoming.pop("rendered_html", None)

        existing = (draft.data or {}) if getattr(draft, 'data', None) else {}
        if not isinstance(existing, dict):
            existing = {}

        existing_rendered = existing.get("rendered_html") if isinstance(existing, dict) else None
        if existing_rendered and isinstance(existing_rendered, dict):
            incoming = dict(incoming)
            incoming.setdefault("rendered_html", existing_rendered)

        base_resolver = existing.get("resolver") if isinstance(existing.get("resolver"), dict) else None
        if base_resolver is None and isinstance(incoming.get("resolver"), dict):
            base_resolver = incoming.get("resolver")

        if base_resolver:
            from specifications.services.template_service import TemplateService

            draft_overrides = incoming.get("draft_overrides") if isinstance(incoming.get("draft_overrides"), dict) else None
            if draft_overrides is None and isinstance(incoming.get("sections"), list):
                draft_overrides = self.extract_draft_overrides(base_resolver, incoming)
            elif draft_overrides is None:
                draft_overrides = {"pricing_visible": bool(incoming.get("pricing_visible", True)), "sections": {}}

            if not isinstance(draft_overrides, dict):
                draft_overrides = {"pricing_visible": bool(incoming.get("pricing_visible", True)), "sections": {}}
            if "report_controls" not in draft_overrides and isinstance(incoming.get("report_controls"), dict):
                draft_overrides["report_controls"] = TemplateService.normalize_report_controls(incoming.get("report_controls"))
            elif "report_controls" not in draft_overrides:
                draft_overrides["report_controls"] = TemplateService.normalize_report_controls(base_resolver.get("report_controls"))

            incoming = {
                "resolver": base_resolver,
                "draft_overrides": draft_overrides,
                "rendered_html": incoming.get("rendered_html", existing_rendered),
                "sections_metadata": existing.get("sections_metadata", incoming.get("sections_metadata")),
            }
            if "pdf_context" in existing:
                incoming["pdf_context"] = existing["pdf_context"]
            if "ui_state" in incoming:
                incoming["ui_state"] = incoming["ui_state"]

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
