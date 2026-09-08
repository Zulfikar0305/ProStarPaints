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
from decimal import Decimal
from typing import Any

from .config import ALL_GENERIC_SECTION_CONFIGS, WALL_TYPES
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


def _format_dft_value(value=None):
    if value is None:
        return ""
    try:
        text = str(value).strip()
        if text in ("", "None"):
            return ""
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    except Exception:
        return ""


def _format_dft_range(min_value=None, max_value=None):
    try:
        if min_value is None and max_value is None:
            return None
        if min_value is not None and max_value is not None:
            min_text = _format_dft_value(min_value)
            max_text = _format_dft_value(max_value)
            if min_value == max_value:
                return min_text
            return f"{min_text}–{max_text}"
        if min_value is not None:
            return _format_dft_value(min_value)
        if max_value is not None:
            return _format_dft_value(max_value)
        return None
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


def _normalise_method_words(value: str | None) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    text = text.replace("/", ",").replace("&", ",").replace(";", ",")
    parts = [part.strip().lower() for part in text.split(",") if part.strip()]
    if not parts:
        return []
    cleaned = []
    for part in parts:
        part = part.replace("and", " ").strip()
        part = re.sub(r"\s+", " ", part)
        if part:
            cleaned.append(part)
    return cleaned


def _application_method_phrase(value: str | None) -> str:
    methods = _normalise_method_words(value)
    if not methods:
        return ""

    if len(methods) == 1:
        method = methods[0]
        if method in {"brush", "roller", "spray"}:
            return f"with a {method}"
        return f"with {method}"

    if len(methods) == 2:
        first, second = methods[0], methods[1]
        if first in {"brush", "roller", "spray"} and second in {"brush", "roller", "spray"}:
            return f"with a {first} and {second}"
        return f"with {first} and {second}"

    human = ", ".join(methods[:-1])
    return f"with {human} and {methods[-1]}"


def compose_application_requirements(section_data: dict | list | None) -> str:
    """Compose a short deterministic application paragraph from persisted section data."""
    try:
        from .models import QuotationLineItem
    except Exception:
        QuotationLineItem = None

    if isinstance(section_data, dict):
        work_items = []
        for entry in (section_data.get("line_items") or []):
            if isinstance(entry, dict):
                item = entry.get("item")
            else:
                item = entry
            if item is not None:
                work_items.append(item)
        note_item = section_data.get("note_item")
    else:
        work_items = list(section_data or [])
        note_item = None

    sentences = []
    if note_item:
        conditions = _collect_surface_conditions(note_item)
        if conditions:
            label = conditions[0].strip()
            sentences.append(f"The substrate is {label}.")

    for item in work_items:
        if QuotationLineItem is not None:
            try:
                if getattr(item, "item_type", None) not in (
                    QuotationLineItem.ItemType.PAINT,
                    QuotationLineItem.ItemType.PRIMER,
                    QuotationLineItem.ItemType.WATERPROOFING,
                ):
                    continue
            except Exception:
                pass

        paint = getattr(item, "paint", None)
        product_name = getattr(paint, "name", None) or getattr(item, "description", "") or ""
        product_name = str(product_name).strip()
        if not product_name:
            continue

        coats = getattr(item, "coats", None)
        try:
            coats = int(coats)
        except Exception:
            coats = 1
        if coats <= 0:
            coats = 1

        sentence = f"Apply {coats} {'coat' if coats == 1 else 'coats'} of {product_name}"
        product_method = _selected_application_method(item) or getattr(paint, "application_method", None)
        method_phrase = _application_method_phrase(product_method)
        if method_phrase:
            sentence += f" {method_phrase}"

        drying_time = None
        if paint is not None:
            drying_time = getattr(paint, "drying_time", None) or None
        if not drying_time:
            drying_time = (getattr(item, "metadata", {}) or {}).get("drying_time")

        if drying_time:
            sentence += f" and allow to dry for approximately {drying_time} before proceeding"

        sentence = sentence.rstrip(". ") + "."
        sentences.append(sentence)

    if not sentences:
        return ""
    return " ".join(sentences)


def _normalise_selection_value(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            label = _normalise_selection_value(item)
            if label:
                return label
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _resolve_selected_substrate(note_item, section_obj=None) -> str | None:
    if note_item is None:
        return None
    meta = getattr(note_item, "metadata", {}) or {}
    if not isinstance(meta, dict):
        return None

    section_key = getattr(section_obj, "subsection_key", None) or meta.get("section_key")
    mapping = {}
    if section_key == "interior_walls":
        mapping.update(dict(WALL_TYPES))
    cfg = ALL_GENERIC_SECTION_CONFIGS.get(section_key) if section_key else None
    if cfg is not None:
        mapping.update(dict(cfg.types))

    lower_map = {str(k).lower(): v for k, v in mapping.items()}

    for candidate in (
        meta.get("wall_type_label"),
        meta.get("wall_type"),
        meta.get("type_label"),
        meta.get("type_labels"),
        meta.get("types"),
        meta.get("type"),
        meta.get("surface"),
        meta.get("surface_label"),
        meta.get("surface_type"),
    ):
        value = _normalise_selection_value(candidate)
        if not value:
            continue
        key = str(value).lower()
        if key in lower_map:
            return str(lower_map[key])
        return value

    return None


def _material_summary_for_item(item, item_no=None, surface_type=None, substrate=None) -> dict:
    # Use persisted fields only; do not recalculate pricing or quantities here.
    product = None
    paint = getattr(item, "paint", None)
    metadata = getattr(item, "metadata", {}) or {}
    try:
        if paint:
            product = paint.name
    except Exception:
        product = None

    spread_rate = None
    if paint is not None and getattr(paint, "spread_rate_per_litre", None) not in (None, ""):
        spread_rate = paint.spread_rate_per_litre
    if spread_rate is None:
        spread_rate = metadata.get("spread_rate_per_litre")

    coverage = None
    try:
        if spread_rate not in (None, ""):
            coverage = Decimal(str(spread_rate).replace(",", ""))
    except Exception:
        coverage = None

    coverage_per_20l = None
    if coverage is not None:
        try:
            coverage_per_20l = coverage * Decimal("20")
        except Exception:
            coverage_per_20l = None

    pack_size = None
    if paint is not None:
        for key in ("package_size", "priced_volume_litres"):
            value = getattr(paint, key, None)
            if value not in (None, ""):
                pack_size = value
                break
    if pack_size is None:
        for key in ("package_size", "recommended_containers", "priced_volume_litres"):
            value = metadata.get(key)
            if value not in (None, ""):
                pack_size = value
                break

    package_unit = None
    if paint is not None:
        package_unit = getattr(paint, "package_unit", None)
    if package_unit in (None, "") and isinstance(metadata, dict):
        package_unit = metadata.get("package_unit")

    unit_price = getattr(item, "price_excl_vat", None)
    if unit_price in (None, "") and paint is not None:
        unit_price = getattr(paint, "price_excl_vat", None)

    paint_cost_per_m2 = None
    try:
        area = getattr(item, "area_sqm", None)
        total = getattr(item, "total_excl_vat", None)
        if area not in (None, "", 0) and total not in (None, ""):
            paint_cost_per_m2 = Decimal(str(total).replace(",", "")) / Decimal(str(area).replace(",", ""))
    except Exception:
        paint_cost_per_m2 = None

    return {
        "item_no": item_no,
        "surface_type": surface_type,
        "substrate": substrate,
        "product": product or (getattr(item, "description", "") or ""),
        "finish": (getattr(item, "paint", None) and getattr(item.paint, "get_finish_display", lambda: None)()) if getattr(item, "paint", None) else None,
        "base": (getattr(item, "paint", None) and getattr(item.paint, "get_base_type_display", lambda: None)()) if getattr(item, "paint", None) else None,
        "area": getattr(item, "area_sqm", None),
        "coats": getattr(item, "coats", None),
        "coverage": coverage,
        "coverage_per_20l": coverage_per_20l,
        "colour": getattr(paint, "colour", None) if paint is not None else "",
        "pack_size": pack_size,
        "package_unit": package_unit,
        "unit_price_excl_vat": unit_price,
        "paint_cost_per_m2_excl_vat": paint_cost_per_m2,
        "required_litres": metadata.get("required_litres"),
        "recommended_containers": metadata.get("recommended_containers"),
        "est_material_cost": getattr(item, "total_excl_vat", None),
        "line_item_pk": getattr(item, "pk", None),
    }


def _prep_treatment_materials_for_item(item) -> dict:
    paint = getattr(item, "paint", None)
    metadata = getattr(item, "metadata", {}) or {}
    tech = _gather_technical_for_item(item)

    quantity = getattr(item, "quantity", None)
    if quantity is None:
        quantity = getattr(item, "area_sqm", None)
    if quantity is None and isinstance(metadata, dict):
        quantity = metadata.get("quantity") or metadata.get("package_count") or metadata.get("roll_count")

    unit = getattr(item, "unit", None) or ""
    if not unit and isinstance(metadata, dict):
        unit = str(metadata.get("package_unit") or "")

    pack_size = None
    if paint is not None:
        for key in ("package_size", "pack_size", "priced_volume_litres"):
            value = getattr(paint, key, None)
            if value not in (None, ""):
                pack_size = value
                break
    if pack_size is None and isinstance(metadata, dict):
        for key in ("package_size", "pack_size", "recommended_containers", "priced_volume_litres"):
            value = metadata.get(key)
            if value not in (None, ""):
                pack_size = value
                break

    unit_price = getattr(item, "price_excl_vat", None)
    if unit_price in (None, "") and paint is not None:
        unit_price = getattr(paint, "price_excl_vat", None)

    total_price = getattr(item, "total_excl_vat", None)
    if total_price in (None, "") and paint is not None:
        total_price = getattr(paint, "total_excl_vat", None)

    return {
        "line_item_pk": getattr(item, "pk", None),
        "description": generate_line_item_description(item),
        "product": getattr(paint, "name", None) or (getattr(item, "description", "") or ""),
        "quantity": quantity,
        "unit": unit,
        "pack_size": pack_size,
        "unit_price_excl_vat": unit_price,
        "total_excl_vat": total_price,
        "tds_reference": tech.get("tds_reference") or metadata.get("tds_reference"),
        "spread_rate_per_litre": tech.get("spread_rate_per_litre") or metadata.get("spread_rate_per_litre"),
        "dft": tech.get("dft") or _format_dft_range(metadata.get("dft_min"), metadata.get("dft_max")),
        "application_method": tech.get("application_method") or metadata.get("application_method") or metadata.get("application_method_label"),
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

    for section_index, sec in enumerate(section_data):
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
            wall_type = _resolve_selected_substrate(note_item, section_obj)
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
            application_requirements = compose_application_requirements({
                "line_items": [
                    {"item": item}
                    for item in work_items
                    if getattr(item, "item_type", None) in (
                        QuotationLineItem.ItemType.PAINT,
                        QuotationLineItem.ItemType.PRIMER,
                        QuotationLineItem.ItemType.WATERPROOFING,
                    )
                ],
                "note_item": note_item,
            })

            # --- Preparation / treatment materials ---
            prep_treatment_materials = []
            for it in work_items:
                try:
                    if getattr(it, "item_type", None) == QuotationLineItem.ItemType.PREP_WORK:
                        prep_treatment_materials.append(_prep_treatment_materials_for_item(it))
                except Exception:
                    continue

            # --- Coating system ---
            coating_system = []
            stage = 0
            for it in work_items:
                try:
                    if getattr(it, "item_type", None) in (QuotationLineItem.ItemType.PRIMER, QuotationLineItem.ItemType.WATERPROOFING, QuotationLineItem.ItemType.PAINT):
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
                        dft_min = tech_info.get("dft_min")
                        dft_max = tech_info.get("dft_max")
                        if dft_min is None:
                            dft_min = meta.get("dft_min")
                        if dft_max is None:
                            dft_max = meta.get("dft_max")
                        dft_value = _format_dft_range(dft_min, dft_max)
                        coat_count = getattr(it, "coats", None)
                        try:
                            coat_count = int(coat_count)
                        except Exception:
                            coat_count = 1
                        if coat_count <= 0:
                            coat_count = 1

                        for coat_index in range(1, coat_count + 1):
                            stage += 1
                            coating_system.append({
                                "stage": stage,
                                "coat_number": coat_index,
                                "coat_label": f"Coat {stage}: {product}" if product else f"Coat {stage}",
                                "product": product,
                                "finish": finish,
                                "base": base,
                                "coats": getattr(it, "coats", None),
                                "area": getattr(it, "area_sqm", None) or getattr(it, "quantity", None),
                                "line_item_pk": getattr(it, "pk", None),
                                "application_method": app_method,
                                "coverage": tech_info.get("coverage") or meta.get("coverage"),
                                "dft": dft_value,
                                "dft_min": dft_min,
                                "dft_max": dft_max,
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
                if getattr(it, "item_type", None) in (
                    QuotationLineItem.ItemType.PAINT,
                    QuotationLineItem.ItemType.PRIMER,
                    QuotationLineItem.ItemType.WATERPROOFING,
                    QuotationLineItem.ItemType.PREP_WORK,
                ):
                    material_summary.append(
                        _material_summary_for_item(
                            it,
                            item_no=section_index + 1,
                            surface_type=getattr(section_obj, "display_name", None) or None,
                            substrate=wall_type,
                        )
                    )

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
                    "substrate": wall_type,
                    "reference_area": reference_area,
                    "surface_conditions": surface_conditions,
                    "general_notes": sec.get("description", ""),
                },
                "surface_default": surface_default,
                "surface_description": surface_description,
                "prep_instructions": prep_instructions,
                "application_instructions": app_instructions,
                "application_requirements": application_requirements,
                "prep_treatment_materials": prep_treatment_materials,
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
            s.setdefault("application_requirements", "")
            s.setdefault("prep_treatment_materials", [])
            s.setdefault("coating_system", [])
            s.setdefault("technical", [])
            s.setdefault("material_summary", [])
            s.setdefault("surface_info", {"wall_type": None, "substrate": None, "reference_area": "", "surface_conditions": [], "general_notes": s.get("description", "")})
            out_sections.append(s)

    return out_sections
