from typing import Any, Dict, List
from decimal import Decimal
import hashlib

from django.db.models import Prefetch

from specifications.models import KnowledgeEntry
from specifications.services.clause_service import ClauseService
from specifications.services.rule_service import RuleService
from specifications.services.template_service import TemplateService
from specifications.services.knowledge_service import KnowledgeService
from specifications.services.blocks import SpecificationBlock


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
                                "product_group": getattr(p, "group_key", None),
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

            # Knowledge resolution + Block assembly: evaluate KnowledgeEntry
            # items and convert section contents into `SpecificationBlock`
            # objects. For backwards compatibility we keep the legacy
            # `clauses`, `product_descriptions`, `images` and
            # `knowledge_matches` keys while also exposing a canonical
            # `blocks` list.
            try:
                product_pks = [p.get("product_pk") for p in sec.get("product_descriptions") or []]
                product_groups = [p.get("product_group") for p in sec.get("product_descriptions") or [] if p.get("product_group")]
                section_meta = (note_item.metadata if note_item and note_item.metadata else {})
                section_context = {
                    "section_key": sec.get("section_key"),
                    "product_pks": product_pks,
                    "product_groups": product_groups,
                    "moisture": moisture_val,
                    "surface_condition": surface_cond,
                    "surface_conditions": section_meta.get("surface_conditions") or [],
                    "substrate_type": getattr(section, "substrate_type", None) or section_meta.get("substrate_type"),
                    "types": section_meta.get("types") or section_meta.get("type") or [],
                    "finish": None,
                    "finishes": [],
                    "preparation": None,
                    "preparations": section_meta.get("preparations") or section_meta.get("preparation") or [],
                    "primer": None,
                    "primers": [],
                    "waterproofing": None,
                    "waterproofing_options": [],
                    "application": None,
                    "applications": [],
                    "location": getattr(quotation, "project_location", None),
                }

                for li in _li_iter:
                    if li.item_type == QuotationLineItem.ItemType.PAINT and li.paint:
                        finish_value = (li.metadata or {}).get("finish") or getattr(li.paint, "finish", None)
                        if finish_value:
                            section_context.setdefault("finishes", [])
                            section_context["finishes"].append(str(finish_value))
                            section_context["finish"] = str(finish_value)
                    elif li.item_type == QuotationLineItem.ItemType.PRIMER and li.paint:
                        section_context.setdefault("primers", [])
                        section_context["primers"].append(str(li.paint.name))
                        section_context["primer"] = str(li.paint.name)
                    elif li.item_type == QuotationLineItem.ItemType.WATERPROOFING and li.paint:
                        section_context.setdefault("waterproofing_options", [])
                        section_context["waterproofing_options"].append(str(li.paint.name))
                        section_context["waterproofing"] = str(li.paint.name)

                    prep_values = (li.metadata or {}).get("preparation") or (li.metadata or {}).get("preparations") or []
                    if prep_values:
                        section_context.setdefault("preparations", [])
                        if isinstance(prep_values, (list, tuple, set)):
                            section_context["preparations"].extend([str(p) for p in prep_values])
                        else:
                            section_context["preparations"].append(str(prep_values))
                        if section_context.get("preparation") is None:
                            section_context["preparation"] = str(prep_values) if not isinstance(prep_values, (list, tuple, set)) else str(list(prep_values)[0])

                    app_values = (li.metadata or {}).get("application") or (li.metadata or {}).get("applications") or []
                    if app_values:
                        section_context.setdefault("applications", [])
                        if isinstance(app_values, (list, tuple, set)):
                            section_context["applications"].extend([str(a) for a in app_values])
                        else:
                            section_context["applications"].append(str(app_values))
                        if section_context.get("application") is None:
                            section_context["application"] = str(app_values) if not isinstance(app_values, (list, tuple, set)) else str(list(app_values)[0])

                section_context["types"] = list(dict.fromkeys(section_context.get("types") or []))
                section_context["surface_conditions"] = list(dict.fromkeys(section_context.get("surface_conditions") or []))
                section_context["finishes"] = list(dict.fromkeys(section_context.get("finishes") or []))
                section_context["preparations"] = list(dict.fromkeys(section_context.get("preparations") or []))
                section_context["primers"] = list(dict.fromkeys(section_context.get("primers") or []))
                section_context["waterproofing_options"] = list(dict.fromkeys(section_context.get("waterproofing_options") or []))
                section_context["applications"] = list(dict.fromkeys(section_context.get("applications") or []))

                kmatches = []
                try:
                    kmatches = KnowledgeService.find_matches_for_section(quotation, section_context)
                except Exception:
                    kmatches = []

                # Keep legacy knowledge_matches list (serialisable dicts)
                sec["knowledge_matches"] = [
                    {
                        "pk": k.pk,
                        "title": k.title,
                        "body": k.body,
                        "priority": k.priority,
                        "score": k.score,
                        "reason": k.reason,
                        "matched_conditions": k.matched_conditions,
                        "created_at": (k.created_at.isoformat() if getattr(k.created_at, "isoformat", None) else k.created_at),
                    }
                    for k in kmatches
                ]

                # Build canonical blocks list. Include heading, products,
                # clauses, knowledge matches and images in a stable order.
                images = sec.get("images") or []
                if not images:
                    images = [{"url": "", "sort_order": 1}]

                blocks = []

                # Heading block
                heading_blk = SpecificationBlock(
                    block_type="heading",
                    title=sec.get("section_name"),
                    content=None,
                    pk=None,
                    source="section:heading",
                    metadata={"section_key": sec.get("section_key")},
                    visible=True,
                    editable=True,
                )
                heading_blk.compute_resolved_id(sec.get("resolved_id"))
                blocks.append(heading_blk)

                # Product description blocks
                for pd in sec.get("product_descriptions") or []:
                    pb = SpecificationBlock(
                        block_type="product_description",
                        title=pd.get("product_name"),
                        content=pd.get("description"),
                        pk=pd.get("product_pk"),
                        source="resolver:product",
                        metadata={"item_type": pd.get("item_type"), "product_group": pd.get("product_group")},
                        visible=True,
                        editable=False,
                    )
                    pb.compute_resolved_id(sec.get("resolved_id"))
                    blocks.append(pb)

                # Clause blocks
                for c in sec.get("clauses") or []:
                    cb = SpecificationBlock(
                        block_type="clause",
                        title=c.get("title"),
                        content=c.get("body"),
                        pk=c.get("pk"),
                        source="resolver:clause",
                        metadata={"category": c.get("category")},
                        visible=True,
                        editable=True,
                    )
                    cb.compute_resolved_id(sec.get("resolved_id"))
                    blocks.append(cb)

                # Knowledge blocks
                for k in sec.get("knowledge_matches") or []:
                    kb = SpecificationBlock(
                        block_type="knowledge",
                        title=k.get("title"),
                        content=k.get("body"),
                        pk=k.get("pk"),
                        source="resolver:knowledge",
                        metadata={"priority": k.get("priority"), "score": k.get("score"), "matched_conditions": k.get("matched_conditions")},
                        visible=True,
                        editable=False,
                    )
                    kb.compute_resolved_id(sec.get("resolved_id"))
                    blocks.append(kb)

                # Image blocks
                for img in images:
                    ib = SpecificationBlock(
                        block_type="image",
                        title=None,
                        content=img.get("url"),
                        pk=None,
                        source="resolver:image",
                        metadata={"sort_order": img.get("sort_order")},
                        visible=True,
                        editable=False,
                    )
                    ib.compute_resolved_id(sec.get("resolved_id"))
                    blocks.append(ib)

                # Attach serialisable blocks
                sec["blocks"] = [b.to_dict() for b in blocks]
            except Exception:
                # Non-fatal: ensure blocks/knowledge_matches exist
                sec.setdefault("knowledge_matches", [])
                sec.setdefault("blocks", [])

            sections.append(sec)

        result: Dict[str, Any] = {
            "template": template_dict,
            "quotation": {"reference": quotation.reference, "customer_name": quotation.customer_name},
            "sections": sections,
            "report_controls": self.template_service.normalize_report_controls(template_dict.get("report_controls")),
        }

        return result

    def _clause_to_dict(self, clause: KnowledgeEntry) -> dict:
        return {"pk": clause.pk, "title": clause.title, "body": clause.body, "category": getattr(clause.category, "name", None)}
