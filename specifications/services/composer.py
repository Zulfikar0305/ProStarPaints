"""Document composition helpers.

Small, stateless utilities to merge template defaults and draft instance
metadata with the enriched section data produced by `spec_report` and
the `SpecificationResolver`.

This module is intentionally conservative: if no metadata is present
it returns the original `enriched_sections` unchanged to guarantee
backwards compatibility.
"""
from typing import Any, Dict, List, Optional


def _index_by_key(items: List[Dict[str, Any]], key_name: str) -> Dict[str, Dict[str, Any]]:
    out = {}
    for it in items or []:
        k = it.get(key_name)
        if k:
            out[str(k)] = it
    return out


def _section_identity_candidates(section: Any) -> List[str]:
    values: List[str] = []
    seen = set()

    def add_value(value):
        if value is None:
            return
        value_str = str(value)
        if value_str not in ("", "None") and value_str not in seen:
            seen.add(value_str)
            values.append(value_str)

    if isinstance(section, dict):
        for key_name in ("section_pk", "pk", "id", "section_id"):
            add_value(section.get(key_name))
        section_key = section.get("section_key") or section.get("subsection_key")
        selection_order = section.get("selection_order")
        if section_key and selection_order is not None:
            add_value(f"{section_key}:{selection_order}")
        for key_name in ("resolved_id", "section_key", "subsection_key"):
            add_value(section.get(key_name))
        nested = section.get("section")
        if nested is not None:
            for value in _section_identity_candidates(nested):
                add_value(value)
    else:
        for key_name in ("section_pk", "pk", "id", "section_id"):
            add_value(getattr(section, key_name, None))
        section_key = getattr(section, "section_key", None) or getattr(section, "subsection_key", None)
        selection_order = getattr(section, "selection_order", None)
        if section_key and selection_order is not None:
            add_value(f"{section_key}:{selection_order}")
        for key_name in ("resolved_id", "section_key", "subsection_key"):
            add_value(getattr(section, key_name, None))
        nested = getattr(section, "section", None)
        if nested is not None:
            for value in _section_identity_candidates(nested):
                add_value(value)

    return values


def _metadata_for_identity(section: Any, mapping: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    for key in _section_identity_candidates(section):
        meta = mapping.get(key)
        if isinstance(meta, dict):
            return meta
    return {}


def compose_sections(
    enriched_sections: List[Dict[str, Any]],
    template_sections: Optional[List[Dict[str, Any]]] = None,
    instance_metadata: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return a composed list of sections.

    - If neither `template_sections` nor `instance_metadata` are provided,
      return `enriched_sections` unchanged (backwards compatible).
    - Match sections by `resolved_id` when available, falling back to
      `section_key` (subsection_key).
    - Apply merged metadata (template defaults overridden by instance
      metadata) and attach it under `composed_metadata` on each section
      dict. Respect `visible` and `order` where present.
    """
    if not enriched_sections:
        return enriched_sections or []

    if not template_sections and not instance_metadata:
        return enriched_sections

    # Build lookup maps for enriched sections
    enriched_by_resolved = {}
    enriched_by_key = {}
    for idx, sec in enumerate(enriched_sections):
        rid = sec.get("resolved_id")
        sk = None
        try:
            section_obj = sec.get("section")
            sk = getattr(section_obj, "subsection_key", None) if section_obj is not None else sec.get("section_key")
        except Exception:
            sk = sec.get("section_key")

        if rid:
            enriched_by_resolved[str(rid)] = (idx, sec)
        if sk:
            enriched_by_key[str(sk)] = (idx, sec)

    # Index template defaults and instance metadata by the actual section identity
    # when available; fall back to section_key only for legacy records. Matching by
    # section_key alone can collapse repeated sections with the same subsection key.
    template_map = {}
    for t in template_sections or []:
        if not isinstance(t, dict):
            continue
        for key in _section_identity_candidates(t):
            template_map.setdefault(str(key), {}).update(t)

    instance_map = {}
    for im in instance_metadata or []:
        if not isinstance(im, dict):
            continue
        for key in _section_identity_candidates(im):
            instance_map.setdefault(str(key), {}).update(im)

    # Helper to merge default -> instance metadata
    def _merge_meta(def_meta: Dict[str, Any], inst_meta: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        if isinstance(def_meta, dict):
            out.update(def_meta)
        if isinstance(inst_meta, dict):
            out.update(inst_meta)
        # Ensure visibility default True
        if out.get("visible") is None:
            out["visible"] = True
        return out

    # Build a working list of (original_index, composed_section, order_hint)
    working: List[Dict[str, Any]] = []
    for idx, sec in enumerate(enriched_sections):
        # Determine matching keys
        rid = sec.get("resolved_id")
        sk = None
        try:
            section_obj = sec.get("section")
            sk = getattr(section_obj, "subsection_key", None) if section_obj is not None else sec.get("section_key")
        except Exception:
            sk = sec.get("section_key")

        def_meta = _metadata_for_identity(sec, template_map)
        inst_meta = _metadata_for_identity(sec, instance_map)

        merged = _merge_meta(def_meta, inst_meta)

        # Attach composed metadata but do not mutate original sec
        composed = dict(sec)
        composed["composed_metadata"] = merged

        # Determine order hint
        order_hint = None
        try:
            if isinstance(merged.get("order"), (int, float)):
                order_hint = float(merged.get("order"))
        except Exception:
            order_hint = None

        working.append({"orig_index": idx, "section": composed, "order": order_hint})

    # Sort according to order hints where present; otherwise preserve original order
    # Items with None order go after those with numeric order, preserving relative order
    with_order = [w for w in working if w.get("order") is not None]
    without_order = [w for w in working if w.get("order") is None]

    with_order.sort(key=lambda w: (w.get("order", 0), w.get("orig_index", 0)))
    without_order.sort(key=lambda w: w.get("orig_index", 0))

    ordered = with_order + without_order

    # Apply visibility filtering
    final_sections: List[Dict[str, Any]] = []
    for w in ordered:
        sec = w.get("section")
        meta = sec.get("composed_metadata") or {}
        if meta.get("visible", True):
            final_sections.append(sec)

    # Backwards-compatibility: if sections expose `blocks` but do not
    # include legacy arrays (`clauses`, `product_descriptions`, `images`),
    # derive them from blocks so older consumers keep working.
    try:
        for sec in final_sections:
            blocks = sec.get("blocks") or []
            if blocks and not sec.get("clauses"):
                sec["clauses"] = [
                    {"pk": b.get("pk"), "title": b.get("title"), "body": b.get("content"), "category": (b.get("metadata") or {}).get("category")}
                    for b in blocks if b.get("block_type") == "clause"
                ]
            if blocks and not sec.get("product_descriptions"):
                sec["product_descriptions"] = [
                    {
                        "item_type": (b.get("metadata") or {}).get("item_type"),
                        "product_name": b.get("title"),
                        "description": b.get("content"),
                        "product_pk": b.get("pk"),
                        "product_group": (b.get("metadata") or {}).get("product_group"),
                    }
                    for b in blocks if b.get("block_type") == "product_description"
                ]
            if blocks and not sec.get("images"):
                sec["images"] = [
                    {"url": b.get("content"), "sort_order": (b.get("metadata") or {}).get("sort_order")}
                    for b in blocks
                    if b.get("block_type") == "image" and b.get("content")
                ]
    except Exception:
        # Keep composition resilient: if derivation fails, return composed
        # sections as-is.
        pass

    return final_sections
