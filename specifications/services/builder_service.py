"""Services for the Manual Specification Builder.

This service is intentionally thin: it reuses the existing
`SpecificationResolver` to produce an initial structured specification
and provides helpers to create and persist user-edited drafts.
"""
from __future__ import annotations

import copy
import logging
from decimal import Decimal
from typing import Any, Dict, Iterable

from .resolver import SpecificationResolver

logger = logging.getLogger(__name__)


class ManualSpecificationBuilderService:
    """High-level helper for preparing and persisting manual drafts."""

    def __init__(self):
        self.resolver = SpecificationResolver()

    def _candidate_section_keys(self, section: Dict[str, Any] | Any, index: int = 0) -> list[str]:
        candidates: list[str] = []

        def add_value(value):
            if value is None:
                return
            candidate = str(value).strip()
            if candidate not in ("", "None") and candidate not in candidates:
                candidates.append(candidate)

        if isinstance(section, dict):
            for key_name in ("section_pk", "pk", "id", "section_id"):
                add_value(section.get(key_name))
            section_key = section.get("section_key") or section.get("subsection_key")
            selection_order = section.get("selection_order")
            if section_key and selection_order is not None:
                add_value(f"{section_key}:{selection_order}")
            for key_name in ("resolved_id", "section_key", "subsection_key"):
                add_value(section.get(key_name))
            name = section.get("section_name")
            if name:
                add_value(str(name))
        else:
            for key_name in ("section_pk", "pk", "id", "section_id"):
                add_value(getattr(section, key_name, None))
            section_key = getattr(section, "section_key", None) or getattr(section, "subsection_key", None)
            selection_order = getattr(section, "selection_order", None)
            if section_key and selection_order is not None:
                add_value(f"{section_key}:{selection_order}")
            for key_name in ("resolved_id", "section_key", "subsection_key"):
                add_value(getattr(section, key_name, None))
            name = getattr(section, "section_name", None)
            if name:
                add_value(str(name))

        if not candidates:
            candidates.append(f"section_{index}")
        return candidates

    def _section_key(self, section: Dict[str, Any] | Any, index: int = 0) -> str:
        return self._candidate_section_keys(section, index)[0]

    def _section_identity(self, section: Dict[str, Any] | Any, index: int = 0) -> str:
        return self._section_key(section, index)

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

    def resolve_section_for_manual_key(self, quotation, section_key: str | int | Any):
        """Return the live QuotationSection that matches a persisted manual override key."""
        if quotation is None:
            return None

        if hasattr(section_key, "pk") and hasattr(section_key, "quotation"):
            section = section_key
            if getattr(section, "quotation_id", None) == getattr(quotation, "pk", None):
                return section
            return None

        if isinstance(section_key, dict):
            for candidate_key in ("section_pk", "pk", "id", "section_id", "section_key", "subsection_key"):
                if candidate_key in section_key:
                    return self.resolve_section_for_manual_key(quotation, section_key[candidate_key])
            return None

        if section_key is None:
            return None

        key_text = str(section_key).strip()
        if not key_text:
            return None

        try:
            section = quotation.sections.filter(pk=int(key_text)).first()
            if section is not None:
                return section
        except (TypeError, ValueError):
            pass

        for section in quotation.sections.all():
            if key_text == str(section.pk):
                return section
            if key_text == section.subsection_key:
                return section
            if key_text == f"{section.subsection_key}:{section.selection_order}":
                return section
            if key_text == str(section.section_id if hasattr(section, "section_id") else section.pk):
                return section
        return None

    def _automatic_section_values_for_section(self, quotation, section_obj) -> Dict[str, Any]:
        """Return the live automatic-prep/app/image values for a specific quotation section."""
        resolver = self.build_serialisable_automatic_context(quotation)
        for section in (resolver.get("sections") or []):
            if not isinstance(section, dict):
                continue
            matches = False
            for candidate in self._candidate_section_keys(section, 0):
                if str(candidate) == str(getattr(section_obj, "pk", "")):
                    matches = True
                    break
            if not matches:
                section_ref = section.get("section") if isinstance(section.get("section"), dict) else section.get("section")
                if isinstance(section_ref, dict) and str(section_ref.get("pk")) == str(getattr(section_obj, "pk", "")):
                    matches = True
            if not matches:
                section_key = (section.get("section_key") or section.get("subsection_key") or "")
                if str(section_key) == str(section_obj.subsection_key):
                    selection_order = section.get("selection_order")
                    if selection_order is None or selection_order == section_obj.selection_order:
                        matches = True
            if not matches:
                continue

            prep_values = section.get("prep_instructions") or []
            prep_text = "\n".join(str(value) for value in (prep_values or []) if str(value).strip())
            if not prep_text and isinstance(section.get("surface_default"), dict):
                prep_text = str(section["surface_default"].get("preparation_requirements") or "")
            if not prep_text:
                prep_text = str(section.get("manual_preparation_requirements") or "")
            if not prep_text:
                prep_text = str(section.get("application_requirements") or "") if section.get("application_requirements") else ""

            app_values = section.get("application_instructions") or []
            app_text = " ".join(str(value) for value in (app_values or []) if str(value).strip())
            if not app_text:
                app_text = str(section.get("application_requirements") or "")
            if not app_text and isinstance(section.get("surface_default"), dict):
                app_text = str(section["surface_default"].get("application_requirements") or "")

            images = []
            raw_images = section.get("images") or []
            if isinstance(raw_images, list):
                images = [
                    str(item.get("url") if isinstance(item, dict) else item).strip()
                    for item in raw_images
                    if isinstance(item, dict) and item.get("url") or isinstance(item, str) and item.strip()
                ]

            return {
                "preparation_requirements": prep_text,
                "application_requirements": app_text,
                "images": images,
            }
        return {
            "preparation_requirements": "",
            "application_requirements": "",
            "images": [],
        }

    def ensure_manual_items_for_quotation(self, quotation, created_by=None):
        """Ensure every quotation section has a persisted manual item with original values captured."""
        from specifications.models import ManualSpecificationItem

        for section in quotation.sections.all().order_by("selection_order", "pk"):
            item, _ = ManualSpecificationItem.objects.get_or_create(
                quotation=quotation,
                section=section,
                defaults={
                    "created_by": created_by,
                    "original_preparation_requirements": "",
                    "original_application_requirements": "",
                    "preparation_requirements": "",
                    "application_requirements": "",
                    "images": [],
                },
            )
            auto_values = self._automatic_section_values_for_section(quotation, section)
            original_prep = str(auto_values.get("preparation_requirements") or "")
            original_app = str(auto_values.get("application_requirements") or "")

            if not item.original_preparation_requirements:
                item.original_preparation_requirements = original_prep
            if not item.original_application_requirements:
                item.original_application_requirements = original_app
            if not item.preparation_requirements:
                item.preparation_requirements = item.original_preparation_requirements
            if not item.application_requirements:
                item.application_requirements = item.original_application_requirements
            if not item.images:
                item.images = auto_values.get("images") or []
            if created_by is not None and not item.created_by_id:
                item.created_by = created_by
            item.save()
        return list(ManualSpecificationItem.objects.filter(quotation=quotation).select_related("section"))

    def save_manual_item(
        self,
        quotation,
        section,
        preparation_requirements: str = "",
        application_requirements: str = "",
        images: list[str] | None = None,
        created_by=None,
    ):
        """Persist a single manual override row for a quotation section."""
        from specifications.models import ManualSpecificationItem

        section_obj = self.resolve_section_for_manual_key(quotation, section)
        if section_obj is None:
            return None

        auto_values = self._automatic_section_values_for_section(quotation, section_obj)
        payload = {
            "preparation_requirements": str(preparation_requirements or ""),
            "application_requirements": str(application_requirements or ""),
            "images": [],
        }
        if isinstance(images, (list, tuple)):
            payload["images"] = [
                str(image).strip()
                for image in images
                if (isinstance(image, str) and image.strip()) or (hasattr(image, "get") and isinstance(image.get("url"), str) and image.get("url").strip())
            ]
        elif isinstance(images, str):
            payload["images"] = [images.strip()] if images.strip() else []

        item, created = ManualSpecificationItem.objects.get_or_create(
            quotation=quotation,
            section=section_obj,
            defaults={
                "created_by": created_by,
                "original_preparation_requirements": str(auto_values.get("preparation_requirements") or ""),
                "original_application_requirements": str(auto_values.get("application_requirements") or ""),
                "preparation_requirements": payload["preparation_requirements"],
                "application_requirements": payload["application_requirements"],
                "images": payload["images"] or auto_values.get("images") or [],
            },
        )

        if not item.original_preparation_requirements:
            item.original_preparation_requirements = str(auto_values.get("preparation_requirements") or "")
        if not item.original_application_requirements:
            item.original_application_requirements = str(auto_values.get("application_requirements") or "")
        if created or not item.images:
            item.images = payload["images"] or auto_values.get("images") or []

        item.preparation_requirements = payload["preparation_requirements"]
        item.application_requirements = payload["application_requirements"]
        if created_by is not None and not item.created_by_id:
            item.created_by = created_by
        item.save()
        return item

    def manual_overrides_for_quotation(self, quotation) -> Dict[str, Dict[str, Any]]:
        """Return the authoritative manual rows for this quotation keyed by QuotationSection PK."""
        from specifications.models import ManualSpecificationItem

        overrides: Dict[str, Dict[str, Any]] = {}
        for item in ManualSpecificationItem.objects.filter(quotation=quotation).select_related("section"):
            overrides[str(item.section_id)] = {
                "preparation_requirements": item.preparation_requirements or item.original_preparation_requirements or "",
                "application_requirements": item.application_requirements or item.original_application_requirements or "",
                "images": list(item.images or []),
            }
        return overrides

    def revert_manual_item(self, quotation, section):
        """Restore a quotation section to its original captured preparation/application values."""
        from specifications.models import ManualSpecificationItem

        section_obj = self.resolve_section_for_manual_key(quotation, section)
        if section_obj is None:
            return None

        item, _ = ManualSpecificationItem.objects.get_or_create(
            quotation=quotation,
            section=section_obj,
            defaults={
                "original_preparation_requirements": "",
                "original_application_requirements": "",
                "preparation_requirements": "",
                "application_requirements": "",
                "images": [],
            },
        )
        auto_values = self._automatic_section_values_for_section(quotation, section_obj)
        if not item.original_preparation_requirements:
            item.original_preparation_requirements = str(auto_values.get("preparation_requirements") or "")
        if not item.original_application_requirements:
            item.original_application_requirements = str(auto_values.get("application_requirements") or "")
        item.preparation_requirements = item.original_preparation_requirements
        item.application_requirements = item.original_application_requirements
        item.save(update_fields=["original_preparation_requirements", "original_application_requirements", "preparation_requirements", "application_requirements", "updated_at"])
        return item

    def normalize_manual_overrides(self, manual_overrides: Dict[str, Any] | None) -> Dict[str, Any]:
        """Normalise per-item manual overrides to a serialisable dict keyed by the section identity."""
        if not isinstance(manual_overrides, dict):
            return {}

        normalized: Dict[str, Any] = {}
        for section_key, value in manual_overrides.items():
            if not isinstance(value, dict):
                continue

            item_override: Dict[str, Any] = {}
            if "preparation_requirements" in value:
                item_override["preparation_requirements"] = str(value.get("preparation_requirements") or "")
            if "application_requirements" in value:
                item_override["application_requirements"] = str(value.get("application_requirements") or "")
            if "images" in value:
                raw_images = value.get("images")
                cleaned_images: list[str] = []
                if isinstance(raw_images, (list, tuple)):
                    for entry in raw_images:
                        if isinstance(entry, dict):
                            url = entry.get("url") or entry.get("image") or entry.get("src")
                        else:
                            url = entry
                        if isinstance(url, str) and url.strip():
                            cleaned_images.append(url.strip())
                elif isinstance(raw_images, str):
                    if raw_images.strip():
                        cleaned_images = [raw_images.strip()]
                item_override["images"] = cleaned_images

            if item_override:
                normalized[str(section_key)] = item_override
        return normalized

    def filter_manual_overrides_for_resolver(self, manual_overrides: Dict[str, Any] | None, resolver: Dict[str, Any] | None) -> Dict[str, Any]:
        """Keep only manual overrides whose keys match the live resolver section identities."""
        normalized = self.normalize_manual_overrides(manual_overrides)
        if not isinstance(resolver, dict):
            return normalized

        live_keys: set[str] = set()
        for idx, section in enumerate((resolver.get("sections") or [])):
            live_keys.update(self._candidate_section_keys(section, idx))

        if not live_keys:
            return {}

        filtered: Dict[str, Any] = {}
        for key, value in normalized.items():
            if key in live_keys:
                filtered[key] = value
        return filtered

    def apply_manual_overrides(self, base_spec: Dict[str, Any] | None, manual_overrides: Dict[str, Any] | None) -> Dict[str, Any]:
        """Apply run-specific item overrides without mutating the source resolver payload."""
        if not isinstance(base_spec, dict):
            return base_spec

        result = copy.deepcopy(base_spec)
        normalized = self.normalize_manual_overrides(manual_overrides)
        if not normalized:
            return result

        for idx, section in enumerate(result.get("sections") or []):
            candidate_keys = self._candidate_section_keys(section, idx)
            override = None
            for candidate_key in candidate_keys:
                override = normalized.get(candidate_key)
                if isinstance(override, dict):
                    break
            if override is None:
                override = normalized.get(str(idx))
            if not isinstance(override, dict):
                continue

            if "images" in override:
                raw_images = override.get("images") or []
                normalized_images = []
                for image in raw_images:
                    if isinstance(image, dict):
                        url = image.get("url") or image.get("image") or image.get("src")
                        if isinstance(url, str) and url.strip():
                            normalized_images.append({"url": url.strip(), "sort_order": image.get("sort_order", len(normalized_images))})
                    elif isinstance(image, str) and image.strip():
                        normalized_images.append({"url": image.strip(), "sort_order": len(normalized_images)})
                section["images"] = normalized_images

            if "preparation_requirements" in override:
                prep_text = str(override.get("preparation_requirements") or "")
                section["manual_preparation_requirements"] = prep_text
                section["manual_preparation_requirements_present"] = True
                if isinstance(section.get("surface_default"), dict):
                    section["surface_default"] = {**section["surface_default"], "preparation_requirements": prep_text}
                section["prep_instructions"] = ([prep_text] if prep_text else [])

            if "application_requirements" in override:
                app_text = str(override.get("application_requirements") or "")
                section["manual_application_requirements"] = app_text
                section["manual_application_requirements_present"] = True
                section["application_requirements"] = app_text

        return result

    def prepare_spec(self, quotation) -> Dict[str, Any]:
        """Return the resolver-produced specification dict for *quotation*."""
        return self.resolver.resolve(quotation)

    def _json_safe_value(self, value):
        """Convert Decimal and model-backed objects to JSON-safe values."""
        if isinstance(value, Decimal):
            as_int = value.to_integral_value()
            if value == as_int:
                return int(as_int)
            return float(value)
        if isinstance(value, dict):
            return {str(key): self._json_safe_value(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe_value(item) for item in value]
        if isinstance(value, set):
            return [self._json_safe_value(item) for item in sorted(value, key=lambda x: str(x))]
        if hasattr(value, "isoformat") and callable(value.isoformat):
            try:
                return value.isoformat()
            except Exception:
                pass
        return value

    def build_serialisable_automatic_context(self, quotation) -> Dict[str, Any]:
        """Return a JSON-safe snapshot of the automatic detailed-spec context.

        The manual builder reuses the same automatic section payload as the real
        Detailed Specification and layers only the editable override values on top.
        We use the PDF context as the canonical automatic representation, then
        enrich it with the live resolver identity data so section matching stays
        stable across repeated subsection keys.
        """
        try:
            from quotation.pdf_service import build_pdf_context
            context = build_pdf_context(quotation, use_resolver=True)
        except Exception:
            context = {}

        resolver_sections = []
        try:
            resolver_sections = (self.resolver.resolve(quotation) or {}).get("sections") or []
        except Exception:
            resolver_sections = []

        resolver_by_identity: Dict[str, list[Dict[str, Any]]] = {}
        for index, resolver_section in enumerate(resolver_sections):
            for candidate in self._candidate_section_keys(resolver_section, index):
                resolver_by_identity.setdefault(candidate, []).append(resolver_section)

        sections = []
        for index, sec in enumerate(context.get("sections") or []):
            if not isinstance(sec, dict):
                continue

            section_obj = sec.get("section")
            section_key = getattr(section_obj, "subsection_key", None) or sec.get("section_key")
            if section_key is None:
                section_key = getattr(section_obj, "section_key", None)
            section_name = getattr(section_obj, "display_name", None) or sec.get("section_name")
            subsection_key = getattr(section_obj, "subsection_key", None) or sec.get("subsection_key")
            selection_order = getattr(section_obj, "selection_order", None) or sec.get("selection_order")

            matched_resolver = None
            for candidate in self._candidate_section_keys(section_obj or sec, index):
                bucket = resolver_by_identity.get(candidate)
                if isinstance(bucket, list) and bucket:
                    matched_resolver = bucket.pop(0)
                    break

            if matched_resolver is not None:
                sec.setdefault("resolved_id", matched_resolver.get("resolved_id"))
                sec.setdefault("blocks", matched_resolver.get("blocks") or [])
                sec.setdefault("resolved_blocks", matched_resolver.get("blocks") or [])
                sec.setdefault("resolved_clauses", matched_resolver.get("clauses") or [])
                sec.setdefault("resolved_product_descriptions", matched_resolver.get("product_descriptions") or [])
                sec.setdefault("resolved_knowledge", matched_resolver.get("knowledge_matches") or [])
                sec.setdefault("section_name", matched_resolver.get("section_name"))
                sec.setdefault("section_key", matched_resolver.get("section_key"))
                sec.setdefault("subsection_key", matched_resolver.get("subsection_key"))
                sec.setdefault("selection_order", matched_resolver.get("selection_order"))
                sec.setdefault("section_pk", matched_resolver.get("section_pk"))
                if section_obj is None:
                    sec["section"] = {
                        "pk": matched_resolver.get("section_pk"),
                        "display_name": matched_resolver.get("section_name"),
                        "subsection_key": matched_resolver.get("subsection_key") or matched_resolver.get("section_key"),
                        "selection_order": matched_resolver.get("selection_order"),
                        "substrate_type": None,
                        "sort_order": None,
                    }
                section_name = sec.get("section_name") or section_name
                subsection_key = sec.get("subsection_key") or subsection_key
                selection_order = sec.get("selection_order") or selection_order
                section_key = sec.get("section_key") or section_key

            if isinstance(section_obj, dict):
                section_ref = dict(section_obj)
            elif section_obj is not None:
                section_ref = {
                    "pk": getattr(section_obj, "pk", None),
                    "display_name": getattr(section_obj, "display_name", None),
                    "subsection_key": getattr(section_obj, "subsection_key", None),
                    "selection_order": getattr(section_obj, "selection_order", None),
                    "substrate_type": getattr(section_obj, "substrate_type", None),
                    "sort_order": getattr(section_obj, "sort_order", None),
                }
            else:
                section_ref = {
                    "pk": sec.get("section_pk"),
                    "display_name": section_name,
                    "subsection_key": subsection_key or section_key,
                    "selection_order": selection_order,
                    "substrate_type": None,
                    "sort_order": None,
                }

            def _format_quantity(value):
                if value in (None, '',):
                    return None
                try:
                    as_decimal = Decimal(str(value))
                except Exception:
                    return str(value).strip()
                if as_decimal == as_decimal.to_integral_value():
                    return int(as_decimal)
                return float(as_decimal)

            section_pk_for_items = sec.get("section_pk") or getattr(section_obj, "pk", None)
            line_items = []
            if hasattr(section_obj, "line_items"):
                try:
                    line_items = list(section_obj.line_items.select_related("paint").order_by("item_type", "pk"))
                except Exception:
                    line_items = []
            if not line_items and section_pk_for_items is not None:
                try:
                    section_model = quotation.sections.filter(pk=section_pk_for_items).prefetch_related("line_items").first()
                    if section_model is not None:
                        line_items = list(section_model.line_items.select_related("paint").order_by("item_type", "pk"))
                except Exception:
                    line_items = []

            selected_line_items = []
            for item in line_items:
                item_type = getattr(item, "item_type", None)
                if item_type in (None, "NOTE"):
                    continue
                if item_type not in ("PAINT", "PRIMER", "WATERPROOFING", "PREP_WORK"):
                    continue

                paint_name = getattr(getattr(item, "paint", None), "name", None)
                product_name = paint_name or (getattr(item, "description", None) or "").strip()
                description = (getattr(item, "description", None) or "").strip() or product_name or "Selected item"
                quantity = getattr(item, "quantity", None)
                if quantity is None:
                    quantity = getattr(item, "area_sqm", None)
                if quantity is None:
                    quantity = getattr(item, "coats", None)
                metadata = getattr(item, "metadata", None) or {}
                if quantity is None and isinstance(metadata, dict):
                    quantity = metadata.get("quantity") or metadata.get("package_count") or metadata.get("roll_count")
                unit = getattr(item, "unit", None) or ""
                if isinstance(metadata, dict):
                    if not unit and metadata.get("package_unit"):
                        unit = str(metadata.get("package_unit"))
                coats = getattr(item, "coats", None)
                selected_line_items.append({
                    "item_type": item_type,
                    "description": description,
                    "product_name": product_name,
                    "quantity": _format_quantity(quantity),
                    "coats": _format_quantity(coats),
                    "unit": unit,
                })

            section_payload = {
                "section_name": section_name,
                "section_key": section_key,
                "subsection_key": subsection_key,
                "section_pk": sec.get("section_pk") or getattr(section_obj, "pk", None),
                "selection_order": selection_order,
                "images": self._json_safe_value(sec.get("images") or []),
                "surface_default": self._serialise_surface_default(sec.get("surface_default")),
                "surface_info": self._json_safe_value(sec.get("surface_info") or {}),
                "prep_instructions": self._json_safe_value(sec.get("prep_instructions") or []),
                "application_instructions": self._json_safe_value(sec.get("application_instructions") or []),
                "application_requirements": self._json_safe_value(sec.get("application_requirements")),
                "prep_treatment_materials": self._json_safe_value(sec.get("prep_treatment_materials") or []),
                "coating_system": self._json_safe_value(sec.get("coating_system") or []),
                "material_summary": self._json_safe_value(sec.get("material_summary") or []),
                "technical": self._json_safe_value(sec.get("technical") or []),
                "section": section_ref,
                "clauses": self._json_safe_value(sec.get("clauses") or []),
                "product_descriptions": self._json_safe_value(sec.get("product_descriptions") or []),
                "knowledge_matches": self._json_safe_value(sec.get("knowledge_matches") or []),
                "blocks": self._json_safe_value(sec.get("blocks") or sec.get("resolved_blocks") or []),
                "resolved_id": sec.get("resolved_id"),
                "resolved_blocks": self._json_safe_value(sec.get("resolved_blocks") or sec.get("blocks") or []),
                "resolved_clauses": self._json_safe_value(sec.get("resolved_clauses") or sec.get("clauses") or []),
                "resolved_product_descriptions": self._json_safe_value(sec.get("resolved_product_descriptions") or sec.get("product_descriptions") or []),
                "resolved_knowledge": self._json_safe_value(sec.get("resolved_knowledge") or sec.get("knowledge_matches") or []),
                "selected_line_items": selected_line_items,
            }
            sections.append(section_payload)

        return {"sections": sections, "report_controls": self._json_safe_value(context.get("report_controls") or {}), "pricing_visible": bool(context.get("pricing_enabled", True))}

        payload = {
            "sections": sections,
            "report_controls": self._json_safe_value(context.get("report_controls") or {}),
            "pricing_visible": bool(context.get("pricing_enabled", True)),
        }
        return payload

    def _serialise_surface_default(self, value):
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        data = getattr(value, "__dict__", {})
        payload = {}
        for key in ("preparation_requirements", "application_requirements", "surface_rules", "surface", "subsection"):
            if hasattr(value, key):
                payload[key] = getattr(value, key)
        if not payload and isinstance(data, dict):
            for key, item in data.items():
                if key.startswith("_"):
                    continue
                payload[key] = item
        return payload

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
        resolved = self.build_serialisable_automatic_context(quotation)

        try:
            from quotation.pdf_service import build_pdf_context
            pdf_ctx = build_pdf_context(quotation, use_resolver=False)
        except Exception as exc:
            logger.exception("Failed to build pdf_ctx for quotation %s: %s", getattr(quotation, 'pk', None), exc)
            pdf_ctx = {}

        try:
            resolved_sections = (resolved or {}).get("sections", [])

            def _identity_candidates(section_obj):
                candidates: list[str] = []
                seen = set()

                def add_value(value):
                    if value is None:
                        return
                    candidate = str(value).strip()
                    if candidate not in ("", "None") and candidate not in seen:
                        seen.add(candidate)
                        candidates.append(candidate)

                if isinstance(section_obj, dict):
                    for key_name in ("section_pk", "pk", "id", "section_id"):
                        add_value(section_obj.get(key_name))
                    section_key = section_obj.get("section_key") or section_obj.get("subsection_key")
                    selection_order = section_obj.get("selection_order")
                    if section_key and selection_order is not None:
                        add_value(f"{section_key}:{selection_order}")
                    for key_name in ("resolved_id", "section_key", "subsection_key"):
                        add_value(section_obj.get(key_name))
                else:
                    for key_name in ("section_pk", "pk", "id", "section_id"):
                        add_value(getattr(section_obj, key_name, None))
                    section_key = getattr(section_obj, "section_key", None) or getattr(section_obj, "subsection_key", None)
                    selection_order = getattr(section_obj, "selection_order", None)
                    if section_key and selection_order is not None:
                        add_value(f"{section_key}:{selection_order}")
                    for key_name in ("resolved_id", "section_key", "subsection_key"):
                        add_value(getattr(section_obj, key_name, None))

                return candidates

            resolver_by_identity = {}
            for rs in resolved_sections:
                for key in _identity_candidates(rs):
                    resolver_by_identity.setdefault(key, []).append(rs)

            for sec in (pdf_ctx.get("sections") or []):
                try:
                    section_obj = sec.get("section")
                    candidates = []
                    if section_obj is not None:
                        candidates.extend(_identity_candidates(section_obj))
                    candidates.extend(_identity_candidates(sec))

                    rs = None
                    for candidate in candidates:
                        bucket = resolver_by_identity.get(candidate)
                        if isinstance(bucket, list) and bucket:
                            rs = bucket.pop(0)
                            break

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
                section_key = getattr(section_obj, "section_key", None) if section_obj is not None else sec.get("section_key")
                subsection_key = getattr(section_obj, "subsection_key", None) if section_obj is not None else sec.get("subsection_key")
                section_pk = getattr(section_obj, "pk", None) if section_obj is not None else sec.get("section_pk")
                selection_order = getattr(section_obj, "selection_order", None) if section_obj is not None else sec.get("selection_order")
                meta = {
                    "resolved_id": sec.get("resolved_id"),
                    "section_key": section_key or subsection_key,
                    "subsection_key": subsection_key or section_key,
                    "section_pk": section_pk,
                    "selection_order": selection_order,
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
            "manual_overrides": {},
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

            existing_manual_overrides = existing.get("manual_overrides") if isinstance(existing.get("manual_overrides"), dict) else {}
            incoming_manual_overrides = incoming.get("manual_overrides") if isinstance(incoming.get("manual_overrides"), dict) else existing_manual_overrides
            if incoming_manual_overrides is not None:
                incoming_manual_overrides = self.normalize_manual_overrides(incoming_manual_overrides)

            incoming = {
                "resolver": base_resolver,
                "draft_overrides": draft_overrides,
                "rendered_html": incoming.get("rendered_html", existing_rendered),
                "sections_metadata": existing.get("sections_metadata", incoming.get("sections_metadata")),
                "manual_overrides": incoming_manual_overrides,
            }
            if "pdf_context" in existing:
                incoming["pdf_context"] = existing["pdf_context"]
            if "ui_state" in incoming:
                incoming["ui_state"] = incoming["ui_state"]
        else:
            existing_manual_overrides = existing.get("manual_overrides") if isinstance(existing.get("manual_overrides"), dict) else {}
            incoming_manual_overrides = incoming.get("manual_overrides") if isinstance(incoming.get("manual_overrides"), dict) else existing_manual_overrides
            if incoming_manual_overrides is not None:
                incoming["manual_overrides"] = self.normalize_manual_overrides(incoming_manual_overrides)

        draft.data = incoming
        draft.save()
        return draft

    def resolver_is_stale_for_quotation(self, quotation, draft_or_data):
        """Return True when a stored resolver no longer matches this quotation's live section identity."""
        data = getattr(draft_or_data, "data", draft_or_data) if not isinstance(draft_or_data, dict) else draft_or_data
        if not isinstance(data, dict):
            return True

        resolver = data.get("resolver") if isinstance(data, dict) else None
        if not isinstance(resolver, dict):
            return True

        current_sections = resolver.get("sections") if isinstance(resolver.get("sections"), list) else []
        live_sections = (self.build_serialisable_automatic_context(quotation) or {}).get("sections") or []
        if not current_sections or not live_sections:
            return bool(current_sections) is False and bool(live_sections) is not False

        current_keys = set()
        for idx, section in enumerate(current_sections):
            current_keys.update(self._candidate_section_keys(section, idx))

        live_keys = set()
        for idx, section in enumerate(live_sections):
            live_keys.update(self._candidate_section_keys(section, idx))

        return current_keys != live_keys

    def repair_stale_draft_for_quotation(self, quotation, draft):
        """Rebuild a stale draft from the live quotation resolver while keeping only valid manual overrides."""
        if draft is None:
            return None

        data = draft.data or {}
        if not isinstance(data, dict):
            data = {}

        if not self.resolver_is_stale_for_quotation(quotation, data):
            return draft

        live_resolver = self.build_serialisable_automatic_context(quotation)
        existing_manual_overrides = data.get("manual_overrides") if isinstance(data.get("manual_overrides"), dict) else {}
        data["resolver"] = live_resolver
        data["manual_overrides"] = self.filter_manual_overrides_for_resolver(existing_manual_overrides, live_resolver)
        draft.data = data
        draft.save(update_fields=["data", "updated_at"])
        return draft

    def latest_draft_for_user(self, quotation, user):
        from specifications.models import ManualSpecificationDraft

        # Manual drafts belong to the quotation workflow, not to the current
        # builder user. Reusing the newest non-stale quotation-scoped draft keeps
        # Save Draft/reload/preview/PDF aligned on the same persisted state while
        # the quotation access checks continue to enforce permissions.
        drafts = ManualSpecificationDraft.objects.filter(quotation=quotation).order_by("-updated_at")

        fallback_draft = None
        for draft in drafts:
            if fallback_draft is None:
                fallback_draft = draft
            if not self.resolver_is_stale_for_quotation(quotation, draft.data):
                return draft

        if fallback_draft is not None:
            fallback_draft = self.repair_stale_draft_for_quotation(quotation, fallback_draft)
        return fallback_draft
