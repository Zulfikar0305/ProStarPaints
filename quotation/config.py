"""
quotation.config
================
Static configuration for the Interior Walls section of the Quotation Builder.

All branching rules live here so views and templates stay thin.
Import what you need:

    from quotation.config import (
        WALL_TYPES, SURFACE_CONDITIONS, FINISHES,
        FINISH_TO_PAINT_GROUPS, PAINT_GROUPS,
        WATERPROOFING_OPTIONS, PRIMER_OPTIONS, OTHER_PREP_OPTIONS,
        MOISTURE_WARNING_THRESHOLD,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Wall types
# ---------------------------------------------------------------------------

WALL_TYPES: list[tuple[str, str]] = [
    ("brick",    "Brick"),
    ("drywall",  "Drywall / Plasterboard"),
    ("block",    "Block / Concrete"),
]

# ---------------------------------------------------------------------------
# Surface conditions  (multi-select)
# ---------------------------------------------------------------------------

SURFACE_CONDITIONS: list[tuple[str, str]] = [
    ("new",           "New surface"),
    ("previously_painted", "Previously painted"),
    ("peeling",       "Peeling / flaking"),
    ("stained",       "Stained"),
    ("mould",         "Mould / mildew present"),
    ("efflorescence", "Efflorescence"),
    ("cracks",        "Cracks or holes"),
    ("rough",         "Rough / uneven surface"),
]

# ---------------------------------------------------------------------------
# Finishes  (multi-select)
# ---------------------------------------------------------------------------

FINISHES: list[tuple[str, str]] = [
    ("smooth_matte",    "Smooth Matte"),
    ("smooth_sheen",    "Smooth Sheen"),
    ("deco_plast",      "Deco-plast"),
    ("fine_texture",    "Fine Texture"),
    ("coarse_texture",  "Coarse Texture"),
]

# ---------------------------------------------------------------------------
# Paint groups
#
# Each group has:
#   key          – machine-readable identifier
#   label        – display name in the UI
#   paint_name   – the Paint.name to attempt a DB match on (case-insensitive contains)
#   bases        – list of (value, label) base / colour options
#                  empty list means no colour choice (single product)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaintGroup:
    key: str
    label: str
    paint_name: str                          # used for DB lookup
    bases: list[tuple[str, str]] = field(default_factory=list)


PAINT_GROUPS: dict[str, PaintGroup] = {
    # ── Smooth Matte ────────────────────────────────────────────────────────
    "pure_matte": PaintGroup(
        key="pure_matte",
        label="Pure Matte",
        paint_name="Pure Matte",
        bases=[
            ("WHITE",   "White"),
            ("PASTEL",  "Pastel Base"),
            ("MEDIUM",  "Medium Base"),
            ("DEEP",    "Deep Base"),
        ],
    ),
    "pro_coat": PaintGroup(
        key="pro_coat",
        label="Pro Coat",
        paint_name="Pro Coat",
        bases=[
            ("WHITE",   "White"),
            ("PASTEL",  "Pastel Base"),
            ("MEDIUM",  "Medium Base"),
            ("DEEP",    "Deep Base"),
        ],
    ),

    # ── Smooth Sheen ────────────────────────────────────────────────────────
    "pro_sheen": PaintGroup(
        key="pro_sheen",
        label="Pro Sheen",
        paint_name="Pro Sheen",
        bases=[
            ("WHITE",   "White"),
            ("PASTEL",  "Pastel Base"),
            ("MEDIUM",  "Medium Base"),
            ("DEEP",    "Deep Base"),
        ],
    ),
    "pure_satin": PaintGroup(
        key="pure_satin",
        label="Pure Satin",
        paint_name="Pure Satin",
        bases=[
            ("WHITE",   "White"),
            ("PASTEL",  "Pastel Base"),
            ("MEDIUM",  "Medium Base"),
            ("DEEP",    "Deep Base"),
        ],
    ),
    "pure_silk": PaintGroup(
        key="pure_silk",
        label="Pure Silk",
        paint_name="Pure Silk",
        bases=[
            ("WHITE",   "White"),
            ("PASTEL",  "Pastel Base"),
            ("MEDIUM",  "Medium Base"),
            ("DEEP",    "Deep Base"),
        ],
    ),
    "anti_fungal": PaintGroup(
        key="anti_fungal",
        label="Anti Fungal",
        paint_name="Anti Fungal",
        bases=[
            ("WHITE",   "White"),
        ],
    ),
    "scented_silk": PaintGroup(
        key="scented_silk",
        label="Scented Silk",
        paint_name="Scented Silk",
        bases=[
            ("WHITE",   "White"),
            ("PASTEL",  "Pastel Base"),
        ],
    ),

    # ── Deco-plast ──────────────────────────────────────────────────────────
    "deco_plast_1mm": PaintGroup(
        key="deco_plast_1mm",
        label="Deco-plast 1mm",
        paint_name="Deco-plast 1mm",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),
    "deco_plast_1_5mm": PaintGroup(
        key="deco_plast_1_5mm",
        label="Deco-plast 1.5mm",
        paint_name="Deco-plast 1.5mm",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),
    "deco_plast_2mm": PaintGroup(
        key="deco_plast_2mm",
        label="Deco-plast 2mm",
        paint_name="Deco-plast 2mm",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),
    "deco_plast_2_5mm": PaintGroup(
        key="deco_plast_2_5mm",
        label="Deco-plast 2.5mm",
        paint_name="Deco-plast 2.5mm",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),

    # ── Fine Texture ────────────────────────────────────────────────────────
    "texture_pro_smooth": PaintGroup(
        key="texture_pro_smooth",
        label="Texture Pro Smooth Finish",
        paint_name="Texture Pro Smooth Finish",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),
    "texture_pro_fine": PaintGroup(
        key="texture_pro_fine",
        label="Texture Pro Fine Texture Finish",
        paint_name="Texture Pro Fine Texture Finish",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),

    # ── Coarse Texture ──────────────────────────────────────────────────────
    "texture_pro_medium_coarse": PaintGroup(
        key="texture_pro_medium_coarse",
        label="Texture Pro Medium Coarse",
        paint_name="Texture Pro Medium Coarse",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),
    "texture_pro_coarse": PaintGroup(
        key="texture_pro_coarse",
        label="Texture Pro Coarse",
        paint_name="Texture Pro Coarse",
        bases=[
            ("WHITE",  "White"),
            ("PASTEL", "Pastel Base"),
        ],
    ),
}

# ---------------------------------------------------------------------------
# Finish → paint group keys  (the branching rule)
# ---------------------------------------------------------------------------

FINISH_TO_PAINT_GROUPS: dict[str, list[str]] = {
    "smooth_matte":   ["pure_matte", "pro_coat"],
    "smooth_sheen":   ["pro_sheen", "pure_satin", "pure_silk", "anti_fungal", "scented_silk"],
    "deco_plast":     ["deco_plast_1mm", "deco_plast_1_5mm", "deco_plast_2mm", "deco_plast_2_5mm"],
    "fine_texture":   ["texture_pro_smooth", "texture_pro_fine"],
    "coarse_texture": ["texture_pro_medium_coarse", "texture_pro_coarse"],
}

# ---------------------------------------------------------------------------
# Waterproofing options
# ---------------------------------------------------------------------------

WATERPROOFING_OPTIONS: list[tuple[str, str]] = [
    ("hydro_shield",  "Hydro Shield"),
    ("hydro_repel",   "Hydro Repel"),
    ("slurry_mix",    "Slurry Mix"),
    ("moistseal",     "Moistseal"),
    ("aqua_proof",    "Aqua Proof"),
]

# ---------------------------------------------------------------------------
# Primer options  (each allows 1 or 2 coats)
# ---------------------------------------------------------------------------

PRIMER_OPTIONS: list[tuple[str, str]] = [
    ("plaster_primerseal", "4/1 Plaster Primerseal"),
    ("gp_universal",       "GP Universal Undercoat"),
    ("aqua_prime",         "Aqua Prime"),
]

# ---------------------------------------------------------------------------
# Other prep work options
# ---------------------------------------------------------------------------

OTHER_PREP_OPTIONS: list[tuple[str, str]] = [
    ("filling",         "Filling cracks and holes"),
    ("mould_treatment", "Mould treatment"),
    ("efflor_removal",  "Efflorescence removal"),
    ("cleaning",        "Cleaning"),
    ("sanding",         "Sanding"),
    ("remove_paint",    "Removing old paint"),
]

# ---------------------------------------------------------------------------
# Moisture warning threshold (%)
# ---------------------------------------------------------------------------

MOISTURE_WARNING_THRESHOLD: int = 15

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_paint_groups_for_finishes(finish_keys: list[str]) -> list[PaintGroup]:
    """
    Return deduplicated ordered list of PaintGroup objects for the given
    finish keys.  Unknown finish keys are silently ignored.
    """
    seen: set[str] = set()
    result: list[PaintGroup] = []
    for fk in finish_keys:
        for group_key in FINISH_TO_PAINT_GROUPS.get(fk, []):
            if group_key not in seen:
                seen.add(group_key)
                result.append(PAINT_GROUPS[group_key])
    return result
