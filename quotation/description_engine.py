"""
quotation.description_engine
=============================
Converts QuotationLineItem metadata into clean, human-readable descriptions
for the review page and any future printed output.

All logic lives here — views call generate_line_item_description() and pass the
result to templates.  No description logic belongs in templates or models.

Supported item types
--------------------
NOTE          – Interior Walls section summary
PAINT         – Individual paint product application
PRIMER        – Primer application
WATERPROOFING – Waterproofing product application
PREP_WORK     – Surface preparation task

Safety guarantee
----------------
Every public function is wrapped so it **never raises**.  If metadata is
missing or malformed the function falls back gracefully to the stored
``line_item.description`` field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import QuotationLineItem


# ---------------------------------------------------------------------------
# Human-readable label lookups
# These mirror config.py but are reproduced here so the engine is self-
# contained and does not create circular imports (models → config is fine,
# but we want this file importable from anywhere).
# ---------------------------------------------------------------------------

_WALL_TYPE_LABELS: dict[str, str] = {
    "brick":    "Brick",
    "drywall":  "Drywall / Plasterboard",
    "block":    "Block / Concrete",
}

_SURFACE_CONDITION_LABELS: dict[str, str] = {
    "new":               "new surface",
    "previously_painted": "previously painted",
    "peeling":           "peeling / flaking",
    "stained":           "stained",
    "mould":             "mould / mildew present",
    "efflorescence":     "efflorescence",
    "cracks":            "cracks or holes",
    "rough":             "rough / uneven surface",
}

_FINISH_LABELS: dict[str, str] = {
    "smooth_matte":   "Smooth Matte",
    "smooth_sheen":   "Smooth Sheen",
    "deco_plast":     "Deco-plast",
    "fine_texture":   "Fine Texture",
    "coarse_texture": "Coarse Texture",
}

_PREP_WORK_SENTENCES: dict[str, str] = {
    "filling":         "Fill cracks and holes.",
    "mould_treatment": "Remove mould and treat affected surfaces.",
    "efflor_removal":  "Remove efflorescence and treat affected areas.",
    "cleaning":        "Clean and degrease surfaces.",
    "sanding":         "Sand surfaces smooth.",
    "remove_paint":    "Strip and remove old paint.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _format_list(items: list[str]) -> str:
    """
    Join a list of strings into a natural-language phrase.

    Examples
    --------
    []              → ""
    ["a"]           → "a"
    ["a", "b"]      → "a and b"
    ["a", "b", "c"] → "a, b and c"
    """
    clean = [s.strip() for s in items if s and s.strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + " and " + clean[-1]


def _resolve_surface_conditions(raw: list[str]) -> str:
    """
    Convert a list of surface condition keys into a readable phrase.
    Unknown keys are passed through unchanged (title-cased).
    Returns an empty string if the list is empty.
    """
    labels = [
        _SURFACE_CONDITION_LABELS.get(k, k.replace("_", " ").capitalize())
        for k in raw
        if k
    ]
    return _format_list(labels) if labels else ""


def _resolve_finishes(raw: list[str]) -> str:
    """
    Convert a list of finish keys into a readable phrase.
    """
    labels = [
        _FINISH_LABELS.get(k, k.replace("_", " ").capitalize())
        for k in raw
        if k
    ]
    return _format_list(labels) if labels else ""


def _coats_phrase(coats: int) -> str:
    """Return '1 coat' or '2 coats' (or 'N coats' for any N)."""
    return f"1 coat" if coats == 1 else f"{coats} coats"


# ---------------------------------------------------------------------------
# Per-type description generators
# ---------------------------------------------------------------------------

def _describe_note(line_item: "QuotationLineItem") -> str:
    """
    Build a human-readable summary for a NOTE (Interior Walls section header).

    Metadata keys used:
        wall_type            – machine key, e.g. "brick"
        wall_type_label      – pre-stored display label (preferred)
        surface_conditions   – list of condition keys
        surface_cond_labels  – pre-stored display labels (preferred)
        finishes             – list of finish keys
        finish_labels        – pre-stored display labels (preferred)
        area_sqm             – numeric or string
        moisture_level       – integer percentage
        notes                – free-text notes appended at the end
    """
    meta: dict = line_item.metadata or {}

    # ------------------------------------------------------------------
    # Opening line.
    # Generic sections (ceilings, floors, etc.) store "section_name" and
    # "type_labels" in metadata.
    # Legacy interior_walls uses "wall_type" / "wall_type_label".
    # ------------------------------------------------------------------
    _section_name: str = meta.get("section_name", "")
    if _section_name:
        _type_labels: list[str] = meta.get("type_labels") or []
        _type_str = _format_list(_type_labels)
        _opening  = f"{_section_name} ({_type_str})." if _type_str else f"{_section_name}."
    else:
        # Legacy interior walls
        wall_label = (
            meta.get("wall_type_label")
            or _WALL_TYPE_LABELS.get(meta.get("wall_type", ""), "")
            or "walls"
        )
        _opening = f"Interior walls ({wall_label})."

    # Surface conditions
    cond_labels: list[str] = meta.get("surface_cond_labels") or []
    if not cond_labels:
        cond_keys: list[str] = meta.get("surface_conditions") or []
        cond_labels = [
            _SURFACE_CONDITION_LABELS.get(k, k.replace("_", " "))
            for k in cond_keys
            if k
        ]

    # Finishes
    finish_labels: list[str] = meta.get("finish_labels") or []
    if not finish_labels:
        finish_keys: list[str] = meta.get("finishes") or []
        finish_labels = [
            _FINISH_LABELS.get(k, k.replace("_", " ").capitalize())
            for k in finish_keys
            if k
        ]

    # Area
    area_sqm = meta.get("area_sqm")

    # Moisture
    moisture = meta.get("moisture_level")

    # Build sentence
    parts: list[str] = []

    parts.append(_opening)

    # Surface conditions
    cond_str = _format_list(cond_labels)
    if cond_str:
        parts.append(f"Surface: {cond_str}.")

    # Finishes
    finish_str = _format_list(finish_labels)
    if finish_str:
        parts.append(f"Finish: {finish_str}.")

    # Area
    if area_sqm not in (None, "", "None"):
        try:
            parts.append(f"Area: {float(area_sqm):.0f} m\u00b2.")
        except (ValueError, TypeError):
            parts.append(f"Area: {area_sqm} m\u00b2.")

    # Moisture
    if moisture not in (None, "", 0, "0"):
        try:
            m_int = int(moisture)
            if m_int > 0:
                parts.append(f"Moisture: {m_int}%.")
        except (ValueError, TypeError):
            pass

    # Free-text notes
    extra_notes = (meta.get("notes") or "").strip()
    if extra_notes:
        parts.append(extra_notes)

    return " ".join(parts)


def _describe_paint(line_item: "QuotationLineItem") -> str:
    """
    Build a description for a PAINT line item.

    Priority order for the product name:
    1. Linked paint's display name (paint.name)
    2. paint_name from metadata
    3. Raw description on the line item

    Base/colour appended in parentheses when available.
    """
    meta: dict = line_item.metadata or {}

    # Product name
    if line_item.paint_id and line_item.paint:
        product = line_item.paint.name
    else:
        product = (meta.get("paint_name") or "").strip() or line_item.description.strip()

    # Base / colour
    base_label = (meta.get("base_label") or "").strip()
    if base_label:
        product = f"{product} ({base_label})"

    coats = line_item.coats or 1
    return f"Apply {_coats_phrase(coats)} of {product}."


def _describe_waterproofing(line_item: "QuotationLineItem") -> str:
    """
    Build a description for a WATERPROOFING line item.
    Uses the stored description (already the product label) as the product name.
    """
    product = line_item.description.strip() or "waterproofing system"
    return f"Apply {product} waterproofing system."


def _describe_primer(line_item: "QuotationLineItem") -> str:
    """
    Build a description for a PRIMER line item.
    Uses the stored description (already the product label) as the product name.
    """
    product = line_item.description.strip() or "primer"
    coats = line_item.coats or 1
    return f"Apply {_coats_phrase(coats)} of {product}."


def _describe_prep_work(line_item: "QuotationLineItem") -> str:
    """
    Build a description for a PREP_WORK line item.

    Uses a lookup table of polished sentences keyed by the stored metadata key.
    Falls back to the stored description if the key is not recognised.
    """
    meta: dict = line_item.metadata or {}
    key = meta.get("key", "")
    if key and key in _PREP_WORK_SENTENCES:
        return _PREP_WORK_SENTENCES[key]
    return line_item.description.strip() or "Surface preparation."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_line_item_description(line_item: "QuotationLineItem") -> str:
    """
    Return a clean, human-readable description for *line_item*.

    This is the single entry point called by views.  It dispatches to the
    appropriate per-type helper and guarantees it never raises — any exception
    is caught and the stored description is returned as a safe fallback.

    Parameters
    ----------
    line_item : QuotationLineItem
        The line item to describe.  The ``paint`` FK should be pre-fetched by
        the caller (``select_related("paint")``) to avoid N+1 queries.

    Returns
    -------
    str
        A non-empty description string.
    """
    try:
        from .models import QuotationLineItem as _LI

        item_type = line_item.item_type

        if item_type == _LI.ItemType.NOTE:
            return _describe_note(line_item)

        if item_type == _LI.ItemType.PAINT:
            return _describe_paint(line_item)

        if item_type == _LI.ItemType.WATERPROOFING:
            return _describe_waterproofing(line_item)

        if item_type == _LI.ItemType.PRIMER:
            return _describe_primer(line_item)

        if item_type == _LI.ItemType.PREP_WORK:
            return _describe_prep_work(line_item)

        # Unknown type – fall back to stored value
        return line_item.description.strip() or "—"

    except Exception:
        # Absolute safety net — never surface an error to the end user
        try:
            return line_item.description.strip() or "—"
        except Exception:
            return "—"
