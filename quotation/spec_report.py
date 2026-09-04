"""
quotation.spec_report
======================
Generate structured specification data from persisted Quotation rows.

This module deliberately performs no HTML rendering and no pricing
calculations — it only reshapes persisted data into a stable, testable
structure that templates and other consumers can rely upon.

The public functions are defensive and do not raise: callers may rely on
falling back to empty lists when metadata is missing or malformed.
"""
from __future__ import annotations

import re
from typing import Any

from .description_engine import generate_line_item_description


def _unique_preserve_order(seq: list[Any]) -> list[Any]:
    seen = set()
    out = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _collect_surface_conditions(note_item) -> list[str]:
    try:
        meta = note_item.metadata or {}
        labels = meta.get("surface_cond_labels") or []
        if labels:
            return [str(s).strip() for s in labels if s]
        keys = meta.get("surface_conditions") or []
        return [str(s).strip() for s in keys if s]
    except Exception:
        return []


def _split_surface_default_text(value: str | None) -> list[str]:
    if not value:
        return []
    candidates = []
    for block in re.split(r"\n+", str(value)):
        for segment in re.split(r"(?<=[.;])\s+|\s*;\s*", block):
            cleaned = re.sub(r"^[\-\*•\s]+", "", str(segment)).strip()
            if cleaned:
                candidates.append(cleaned)
    return _unique_preserve_order(candidates)


def _format_reference_areas(line_items: list) -> str:
    parts = []
    for li in line_items:
        try:
            if getattr(li, "area_sqm", None):
                parts.append(f"{li.area_sqm} m²")
        except Exception:
            continue
    return ", ".join(parts)


def _format_dft_range(min_value=None, max_value=None):
    try:
        if min_value is None and max_value is None:
            return None
        if min_value is not None and max_value is not None and min_value != max_value:
            return f"{min_value}-{max_value}"
        return str(min_value if min_value is not None else max_value)
    except Exception:
        return None


def _normalise_method_key(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _selected_application_method(item) -> str | None:
    paint = getattr(item, "paint", None)
    if paint is not None:
        product_method = getattr(paint, "application_method", None)
        if product_method:
            return str(product_method)

    metadata = getattr(item, "metadata", {}) or {}
    for key in ("application_method", "application_method_label", "method"):
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)

    if paint is None:
        return None

    methods = getattr(paint, "application_methods", None) or []
    if isinstance(methods, list):
        for entry in methods:
            if isinstance(entry, dict):
                method = entry.get("method") or entry.get("label") or entry.get("name")
                if method:
                    return str(method)

    return None


def _paint_application_method(item) -> str | None:
    selected = _selected_application_method(item)
    if selected:
        return selected

    paint = getattr(item, "paint", None)
    if paint is None:
        return None

    methods = getattr(paint, "application_methods", None) or []
    if isinstance(methods, list):
        for entry in methods:
            if isinstance(entry, dict):
                method = entry.get("method") or entry.get("label") or entry.get("name")
                if method:
                    return str(method)

    method = getattr(paint, "application_method", None)
    if method:
        return str(method)

    return None


def _matching_application_method_entry(paint, selected_method: str | None = None) -> dict:
    if paint is None:
        return {}

    methods = getattr(paint, "application_methods", None) or []
    if not isinstance(methods, list):
        return {}

    selected_key = _normalise_method_key(selected_method)
    if selected_key:
        for entry in methods:
            if not isinstance(entry, dict):
                continue
            method_name = entry.get("method") or entry.get("label") or entry.get("name")
            if _normalise_method_key(method_name) == selected_key:
                return entry

    product_method = getattr(paint, "application_method", None)
    if product_method:
        product_key = _normalise_method_key(product_method)
        for entry in methods:
            if not isinstance(entry, dict):
                continue
            method_name = entry.get("method") or entry.get("label") or entry.get("name")
            if _normalise_method_key(method_name) == product_key:
                return entry

    if methods and isinstance(methods[0], dict):
        return methods[0]
    return {}


def _gather_technical_for_item(item) -> dict:
    md = getattr(item, "metadata", {}) or {}
    info = {}

    try:
        paint = getattr(item, "paint", None)
        if paint is not None:
            method_entry = _matching_application_method_entry(paint, _selected_application_method(item))
            selected_method = _paint_application_method(item)
            if selected_method:
                info["application_method"] = selected_method

            for name in ("spread_rate_per_litre", "dft_min", "dft_max", "drying_time", "recoat_time", "tds_reference", "tds_revision", "tds_url"):
                value = method_entry.get(name)
                if value not in (None, ""):
                    info[name] = value

            if getattr(paint, "spread_rate_per_litre", None) is not None:
                info.setdefault("spread_rate_per_litre", paint.spread_rate_per_litre)
            if getattr(paint, "dft_min", None) is not None:
                info.setdefault("dft_min", paint.dft_min)
            if getattr(paint, "dft_max", None) is not None:
                info.setdefault("dft_max", paint.dft_max)
            if getattr(paint, "drying_time", None) not in (None, ""):
                info.setdefault("drying_time", paint.drying_time)
            if getattr(paint, "recoat_time", None) not in (None, ""):
                info.setdefault("recoat_time", paint.recoat_time)
            if getattr(paint, "tds_reference", None) not in (None, ""):
                info.setdefault("tds_reference", paint.tds_reference)
            if getattr(paint, "tds_revision", None) not in (None, ""):
                info.setdefault("tds_revision", paint.tds_revision)
            if getattr(paint, "tds_url", None) not in (None, ""):
                info.setdefault("tds_url", paint.tds_url)

            dft_range = _format_dft_range(info.get("dft_min"), info.get("dft_max"))
            if dft_range:
                info["dft"] = dft_range
    except Exception:
        pass

    fields = [
        "spread_rate_per_litre",
        "required_litres",
        "recommended_containers",
        "package_size",
        "package_unit",
        "rate_per_sqm_selected_coats_excl_vat",
        "price_per_litre_excl_vat",
        "coverage",
        "application_method",
        "application_method_label",
        "dft",
        "dft_min",
        "dft_max",
        "drying_time",
        "recoat_time",
        "tds_reference",
        "tds_revision",
        "tds_url",
    ]
    for f in fields:
        v = md.get(f)
        if v not in (None, "") and f not in info:
            info[f] = v

    if "dft" not in info:
        dft_metadata = md.get("dft")
        if dft_metadata not in (None, ""):
            info["dft"] = dft_metadata
    if "dft_min" not in info and "dft_max" not in info:
        md_min = md.get("dft_min")
        md_max = md.get("dft_max")
        if md_min is not None or md_max is not None:
            info["dft_min"] = md_min
            info["dft_max"] = md_max
            info["dft"] = _format_dft_range(md_min, md_max) or info.get("dft")

    return info


def _material_summary_for_item(item) -> dict:
    # Use persisted fields only; do not calculate new totals.
    product = None
    try:
        if getattr(item, "paint", None):
            product = item.paint.name
    except Exception:
        product = None

    return {
        "product": product or (getattr(item, "description", "") or ""),
        "finish": (getattr(item, "paint", None) and getattr(item.paint, "get_finish_display", lambda: None)()) if getattr(item, "paint", None) else None,
        "base": (getattr(item, "paint", None) and getattr(item.paint, "get_base_type_display", lambda: None)()) if getattr(item, "paint", None) else None,
        "area": getattr(item, "area_sqm", None),
        "coats": getattr(item, "coats", None),
        "required_litres": (item.metadata or {}).get("required_litres"),
        "recommended_containers": (item.metadata or {}).get("recommended_containers"),
        "est_material_cost": getattr(item, "total_excl_vat", None),
        "line_item_pk": getattr(item, "pk", None),
    }


def generate_spec_for_sections(section_data: list[dict]) -> list[dict]:
    """
    Accept the ``section_data`` structure built by ``build_pdf_context``
    and return an enriched list where each section dict includes the keys:

    - ``prep_instructions``: ordered list[str]
    - ``application_instructions``: ordered list[str]
    - ``coating_system``: list[dict]
    - ``technical``: list[dict]
    - ``material_summary``: list[dict]

    This function is defensive and will return empty lists on error.
    """
    out_sections = []
    try:
        from .models import QuotationLineItem
    except Exception:
        QuotationLineItem = None

    try:
        from specifications.models import SurfaceDefault
        surface_defaults = list(SurfaceDefault.objects.filter(is_active=True))
        default_map = {
            (str(item.main_section).upper(), item.subsection, str(item.surface).lower()): item
            for item in surface_defaults
        }
    except Exception:
        default_map = {}

    for sec in section_data:
        try:
            note_item = sec.get("note_item")
            # line_items in the section_data are dicts with 'item' and 'description'
            li_dicts = sec.get("line_items") or []
            work_items = [d.get("item") for d in li_dicts if d.get("item") is not None]

            section_obj = sec.get("section")
            section_key = getattr(section_obj, "subsection_key", "") or ""
            subset = getattr(section_obj, "substrate_type", None)
            main_section = str(subset).upper() if subset else ""
            surface_default = None
            surface_key = None

            if note_item and getattr(note_item, "metadata", None):
                meta = note_item.metadata or {}
                for candidate in ("wall_type", "surface", "type", "types"):
                    value = meta.get(candidate)
                    if isinstance(value, (list, tuple)):
                        value = value[0] if value else None
                    if value not in (None, ""):
                        surface_key = str(value).strip().lower()
                        break

            if main_section and section_key and surface_key:
                surface_default = default_map.get((main_section, section_key, surface_key))
            if surface_default is None and section_key and surface_key:
                surface_default = default_map.get(("INTERIOR", section_key, surface_key))
                if surface_default is None:
                    surface_default = default_map.get(("EXTERIOR", section_key, surface_key))

            # --- Surface info ---
            wall_type = None
            if note_item and getattr(note_item, "metadata", None):
                wall_type = (note_item.metadata or {}).get("wall_type_label")
            if not wall_type:
                try:
                    wall_type = getattr(sec.get("section"), "get_substrate_type_display", lambda: None)()
                except Exception:
                    wall_type = None

            reference_area = _format_reference_areas(work_items)
            surface_conditions = []
            if note_item:
                surface_conditions = _collect_surface_conditions(note_item)

            # --- Preparation instructions ---
            prep_instructions = []
            if surface_default and surface_default.preparation_requirements:
                prep_instructions.extend(_split_surface_default_text(surface_default.preparation_requirements))

            # If there are paint/primer/waterproofing items, recommend inspection
            if any(getattr(it, "item_type", None) in (QuotationLineItem.ItemType.PAINT, QuotationLineItem.ItemType.PRIMER, QuotationLineItem.ItemType.WATERPROOFING) for it in work_items if it is not None):
                prep_instructions.append("Inspect existing coating.")

            # Surface-derived rules
            for cond in surface_conditions:
                lc = cond.lower()
                if "peel" in lc or "flak" in lc:
                    prep_instructions.append("Remove loose paint.")
                elif "mould" in lc:
                    prep_instructions.append("Remove mould and treat affected surfaces.")
                elif "effloresc" in lc or "efflor" in lc:
                    prep_instructions.append("Remove efflorescence and treat affected areas.")
                elif "crack" in lc or "hole" in lc:
                    prep_instructions.append("Repair cracks and holes.")
                elif "stain" in lc:
                    prep_instructions.append("Clean and degrease stained areas.")
                elif "rough" in lc:
                    prep_instructions.append("Sanding may be required to achieve a smooth surface.")

            # Moisture handling
            try:
                if note_item and note_item.metadata:
                    m = note_item.metadata.get("moisture_level")
                    if m not in (None, "", 0, "0"):
                        try:
                            if int(m) > 0:
                                prep_instructions.append("Allow surfaces to dry; re-check moisture before painting.")
                        except Exception:
                            pass
            except Exception:
                pass

            # Include explicit PREP_WORK line items (generate descriptions)
            for it in work_items:
                try:
                    if getattr(it, "item_type", None) == QuotationLineItem.ItemType.PREP_WORK:
                        prep_instructions.append(generate_line_item_description(it))
                except Exception:
                    continue

            prep_instructions = _unique_preserve_order([p for p in prep_instructions if p])

            # --- Application instructions ---
            app_instructions = []
            has_primer = False
            has_waterproof = False
            has_paint = False
            paint_descriptions = []
            for it in work_items:
                try:
                    t = getattr(it, "item_type", None)
                    if t == QuotationLineItem.ItemType.PRIMER:
                        has_primer = True
                        paint_descriptions.append(generate_line_item_description(it))
                    elif t == QuotationLineItem.ItemType.WATERPROOFING:
                        has_waterproof = True
                        paint_descriptions.append(generate_line_item_description(it))
                    elif t == QuotationLineItem.ItemType.PAINT:
                        has_paint = True
                        paint_descriptions.append(generate_line_item_description(it))
                except Exception:
                    continue

            if has_primer:
                app_instructions.append("Apply primer where specified.")
                app_instructions.append("Allow primer to cure before applying topcoat.")
            if has_waterproof:
                app_instructions.append("Apply specified waterproofing where indicated.")
                app_instructions.append("Allow waterproofing to cure before further coatings.")

            # Per-product application lines
            for desc in paint_descriptions:
                if desc:
                    app_instructions.append(desc)

            if has_paint:
                app_instructions.append("Respect drying times between coats and stages.")

            app_instructions = _unique_preserve_order([a for a in app_instructions if a])

            # --- Coating system ---
            coating_system = []
            stage = 0
            for it in work_items:
                try:
                    if getattr(it, "item_type", None) in (QuotationLineItem.ItemType.PRIMER, QuotationLineItem.ItemType.WATERPROOFING, QuotationLineItem.ItemType.PAINT):
                        stage += 1
                        product = None
                        try:
                            if it.paint:
                                product = it.paint.name
                        except Exception:
                            product = None
                        if not product:
                            product = it.description or ""
                        finish = None
                        base = None
                        try:
                            if it.paint and getattr(it.paint, "get_finish_display", None):
                                finish = it.paint.get_finish_display()
                        except Exception:
                            finish = None
                        try:
                            if it.paint and getattr(it.paint, "get_base_type_display", None):
                                base = it.paint.get_base_type_display()
                        except Exception:
                            base = None

                        meta = getattr(it, "metadata", {}) or {}
                        app_method = _paint_application_method(it) or meta.get("application_method") or meta.get("application_method_label") or "Brush / Roller / Spray"
                        tech_info = _gather_technical_for_item(it)
                        coating_system.append({
                            "stage": stage,
                            "product": product,
                            "finish": finish,
                            "base": base,
                            "coats": getattr(it, "coats", None),
                            "area": getattr(it, "area_sqm", None) or getattr(it, "quantity", None),
                            "line_item_pk": getattr(it, "pk", None),
                            "application_method": app_method,
                            "coverage": tech_info.get("coverage") or meta.get("coverage"),
                            "dft": tech_info.get("dft") or meta.get("dft"),
                            "dft_min": tech_info.get("dft_min") or meta.get("dft_min"),
                            "dft_max": tech_info.get("dft_max") or meta.get("dft_max"),
                            "drying_time": tech_info.get("drying_time") or meta.get("drying_time"),
                            "recoat_time": tech_info.get("recoat_time") or meta.get("recoat_time"),
                            "tds_reference": tech_info.get("tds_reference") or meta.get("tds_reference"),
                            "spread_rate_per_litre": tech_info.get("spread_rate_per_litre") or meta.get("spread_rate_per_litre"),
                            "required_litres": tech_info.get("required_litres") or meta.get("required_litres"),
                        })
                except Exception:
                    continue

            # --- Technical information ---
            technical = []
            for it in work_items:
                info = _gather_technical_for_item(it)
                if info:
                    technical.append({"line_item_pk": getattr(it, "pk", None), "info": info})

            # --- Material summary ---
            material_summary = []
            for it in work_items:
                if getattr(it, "item_type", None) in (QuotationLineItem.ItemType.PAINT, QuotationLineItem.ItemType.PRIMER, QuotationLineItem.ItemType.WATERPROOFING):
                    material_summary.append(_material_summary_for_item(it))

            surface_description = (sec.get("description") or "").strip()
            if surface_default and surface_default.surface_rules:
                surface_rule_text = surface_default.surface_rules.strip()
                if surface_rule_text and surface_rule_text not in surface_description:
                    surface_description = (
                        f"{surface_description} {surface_rule_text}" if surface_description else surface_rule_text
                    ).strip()

            # Attach everything to a new enriched section dict (preserve existing keys)
            enriched = dict(sec)
            enriched.update({
                "surface_info": {
                    "wall_type": wall_type,
                    "reference_area": reference_area,
                    "surface_conditions": surface_conditions,
                    "general_notes": sec.get("description", ""),
                },
                "surface_default": surface_default,
                "surface_description": surface_description,
                "prep_instructions": prep_instructions,
                "application_instructions": app_instructions,
                "coating_system": coating_system,
                "technical": technical,
                "material_summary": material_summary,
            })

            out_sections.append(enriched)

        except Exception:
            # Defensive fallback: preserve original section object but ensure keys exist
            s = dict(sec)
            s.setdefault("prep_instructions", [])
            s.setdefault("application_instructions", [])
            s.setdefault("coating_system", [])
            s.setdefault("technical", [])
            s.setdefault("material_summary", [])
            s.setdefault("surface_info", {"wall_type": None, "reference_area": "", "surface_conditions": [], "general_notes": s.get("description", "")})
            out_sections.append(s)

    return out_sections
