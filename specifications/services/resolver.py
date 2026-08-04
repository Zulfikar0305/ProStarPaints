from typing import Any, Dict, List
from decimal import Decimal
import hashlib

from django.db.models import Prefetch

from specifications.models import KnowledgeEntry
from specifications.services.clause_service import ClauseService
from specifications.services.rule_service import RuleService
from specifications.services.template_service import TemplateService


class SpecificationResolver:
    """Resolve a Quotation into a structured specification dict.

    Responsibilities:
    - Read quotation sections and line items
    - Resolve clauses via ClauseService and RuleService (moisture)
    - Gather product descriptions from linked Paint/Primer products
    - Attach section images

    Returns a pure data structure (dict / lists) suitable for downstream
    rendering by other components.
    """

    def __init__(self):
        self.clause_service = ClauseService
        self.rule_service = RuleService
        self.template_service = TemplateService

    def resolve(self, quotation) -> Dict[str, Any]:
        # Template
        tmpl = self.template_service.get_active_template()
        template_dict = self.template_service.as_dict(tmpl)

        # Prefetch section line items (with paint) and images
        from quotation.models import QuotationSection, QuotationLineItem

        sections_qs = (
            QuotationSection.objects.filter(quotation=quotation)
            .order_by("sort_order", "selection_order", "pk")
            .prefetch_related(
                Prefetch("line_items", queryset=QuotationLineItem.objects.select_related("paint").order_by("pk")),
                Prefetch("images", to_attr="_resolved_images"),
            )
        )

        sections: List[Dict[str, Any]] = []

        for section in sections_qs:
            # Build section container
            sec: Dict[str, Any] = {
                "section_name": section.display_name,
                "section_key": section.subsection_key,
                "clauses": [],
                "product_descriptions": [],
                "images": [],
            }

            # Find NOTE item for metadata (surface_condition, moisture_level)
            note_item = None
            _li_attr = getattr(section, "line_items", [])
            _li_iter = _li_attr.all() if hasattr(_li_attr, "all") else (_li_attr or [])
            for li in _li_iter:
                if li.item_type == QuotationLineItem.ItemType.NOTE:
                    note_item = li
                    break

            # Surface condition clauses (from note metadata)
            surface_cond = None
            if note_item and note_item.metadata:
                surface_cond = note_item.metadata.get("surface_condition")
            if surface_cond:
                clauses = self.clause_service.resolve("surface_condition", str(surface_cond))
                sec["clauses"].extend([self._clause_to_dict(c) for c in clauses])

            # Moisture rules
            moisture_val = None
            if note_item and note_item.metadata:
                mv = note_item.metadata.get("moisture_level")
                try:
                    moisture_val = Decimal(str(int(mv))) if mv is not None else None
                except Exception:
                    try:
                        moisture_val = Decimal(str(mv))
                    except Exception:
                        moisture_val = None

            if moisture_val is not None:
                m_clauses = self.rule_service.clauses_for_moisture(moisture_val)
                sec["clauses"].extend([self._clause_to_dict(c) for c in m_clauses])

            # Product descriptions and product-linked clauses (paint / primer)
            _li_attr = getattr(section, "line_items", [])
            _li_iter = _li_attr.all() if hasattr(_li_attr, "all") else (_li_attr or [])
            for li in _li_iter:
                if li.item_type in (QuotationLineItem.ItemType.PAINT, QuotationLineItem.ItemType.PRIMER):
                    p = li.paint
                    if p:
                        sec["product_descriptions"].append(
                            {
                                "item_type": li.get_item_type_display(),
                                "product_name": p.name,
                                "description": p.description,
                                "product_pk": p.pk,
                            }
                        )
                        # resolve paint/primer triggers by group_key or pk
                        trigger_key = p.group_key or str(p.pk)
                        ttype = "paint" if li.item_type == QuotationLineItem.ItemType.PAINT else "primer"
                        p_clauses = self.clause_service.resolve(ttype, trigger_key)
                        sec["clauses"].extend([self._clause_to_dict(c) for c in p_clauses])

            # Section images
            imgs = getattr(section, "_resolved_images", [])
            for img in imgs:
                sec["images"].append({"url": getattr(img.image, "url", getattr(img.image, "name", None)), "sort_order": img.sort_order})

            # Deduplicate clauses by PK preserve order
            seen = set()
            deduped = []
            for c in sec["clauses"]:
                cid = c.get("pk")
                if cid not in seen:
                    seen.add(cid)
                    deduped.append(c)
            sec["clauses"] = deduped

            # Stable resolved section identifier: deterministic hash of
            # section key + clause pks + product pks + image urls. This
            # allows downstream components to match resolved sections
            # without relying on positional ordering.
            try:
                sk = str(sec.get("section_key") or "")
                clause_ids = [str(c.get("pk")) for c in sec.get("clauses") or []]
                product_ids = [str(p.get("product_pk")) for p in sec.get("product_descriptions") or []]
                image_urls = [str(i.get("url")) for i in sec.get("images") or []]
                key_parts = [sk, "|".join(sorted(clause_ids)), "|".join(sorted(product_ids)), "|".join(sorted(image_urls))]
                key_str = "::".join(key_parts)
                resolved_id = hashlib.sha1(key_str.encode("utf-8")).hexdigest()[:16]
                sec["resolved_id"] = resolved_id
            except Exception:
                # Non-fatal: if hashing fails, proceed without resolved_id
                sec["resolved_id"] = None

            sections.append(sec)

        result: Dict[str, Any] = {
            "template": template_dict,
            "quotation": {"reference": quotation.reference, "customer_name": quotation.customer_name},
            "sections": sections,
        }

        return result

    def _clause_to_dict(self, clause: KnowledgeEntry) -> dict:
        return {"pk": clause.pk, "title": clause.title, "body": clause.body, "category": getattr(clause.category, "name", None)}
