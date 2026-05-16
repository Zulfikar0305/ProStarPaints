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


# ---------------------------------------------------------------------------
# Generic interior surface conditions
# ---------------------------------------------------------------------------

# Full set – used by ceilings, doors_trims_skirtings, window_frames
GENERIC_SURFACE_CONDITIONS_FULL: list[tuple[str, str]] = [
    ("prev_painted_good",   "Previously painted \u2013 good condition"),
    ("prev_painted_poor",   "Previously painted \u2013 poor condition"),
    ("prev_painted_chalky", "Previously painted \u2013 chalky surface"),
    ("prev_painted_mouldy", "Previously painted \u2013 mouldy surface"),
    ("unpainted",           "Unpainted"),
]

# Floors only (no chalky)
GENERIC_SURFACE_CONDITIONS_FLOORS: list[tuple[str, str]] = [
    ("prev_painted_good",   "Previously painted \u2013 good condition"),
    ("prev_painted_poor",   "Previously painted \u2013 poor condition"),
    ("prev_painted_mouldy", "Previously painted \u2013 mouldy surface"),
    ("unpainted",           "Unpainted"),
]


# ---------------------------------------------------------------------------
# Interior section configuration dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InteriorSectionConfig:
    """
    Configuration for a single surface section in the builder.
    Used for both interior and exterior generic sections.

    Attributes
    ----------
    key               : matches QuotationSection.subsection_key
    display_name      : human-readable section title shown in the UI
    type_label        : label for the surface-type field, e.g. "Ceiling type"
    types             : list of (value, label) surface-type choices
    surface_conditions: list of (value, label) applicable surface conditions
    finishes          : list of (value, label) finishes available for this section
    substrate_type    : "INTERIOR" or "EXTERIOR" – stored in metadata and audit log
    """
    key: str
    display_name: str
    type_label: str
    types: list[tuple[str, str]]
    surface_conditions: list[tuple[str, str]]
    finishes: list[tuple[str, str]]
    substrate_type: str = "INTERIOR"


# ---------------------------------------------------------------------------
# Finish-list helpers (shared across section configs)
# ---------------------------------------------------------------------------

_ALL_FIVE_FINISHES: list[tuple[str, str]] = [
    ("smooth_matte",   "Smooth Matte"),
    ("smooth_sheen",   "Smooth Sheen"),
    ("deco_plast",     "Deco-plast"),
    ("fine_texture",   "Fine Texture"),
    ("coarse_texture", "Coarse Texture"),
]

_TWO_SMOOTH_FINISHES: list[tuple[str, str]] = [
    ("smooth_matte", "Smooth Matte"),
    ("smooth_sheen", "Smooth Sheen"),
]

_FOUR_NO_DECO_FINISHES: list[tuple[str, str]] = [
    ("smooth_matte",   "Smooth Matte"),
    ("smooth_sheen",   "Smooth Sheen"),
    ("fine_texture",   "Fine Texture"),
    ("coarse_texture", "Coarse Texture"),
]


# ---------------------------------------------------------------------------
# INTERIOR_SECTION_CONFIGS
#
# Config for every generic interior section (i.e. all interior sections
# EXCEPT interior_walls which has its own dedicated partial and save view).
# The builder view uses this dict to determine which template and save logic
# to apply for each QuotationSection.subsection_key.
# ---------------------------------------------------------------------------

INTERIOR_SECTION_CONFIGS: dict[str, "InteriorSectionConfig"] = {
    "ceilings": InteriorSectionConfig(
        key="ceilings",
        display_name="Ceilings",
        type_label="Ceiling type",
        types=[
            ("concrete_socket", "Concrete socket"),
            ("gypsum_boards",   "Gypsum boards"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_ALL_FIVE_FINISHES,
    ),
    "floors": InteriorSectionConfig(
        key="floors",
        display_name="Floors",
        type_label="Floor type",
        types=[
            ("concrete",  "Concrete"),
            ("soft_wood", "Soft wood"),
            ("hardwood",  "Hardwood"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FLOORS,
        finishes=_TWO_SMOOTH_FINISHES,
    ),
    "doors_trims_skirtings": InteriorSectionConfig(
        key="doors_trims_skirtings",
        display_name="Doors, Trims & Skirtings",
        type_label="Surface type",
        types=[
            ("hardwood",  "Hardwood"),
            ("soft_wood", "Soft wood"),
            ("metal",     "Metal"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_FOUR_NO_DECO_FINISHES,
    ),
    "window_frames": InteriorSectionConfig(
        key="window_frames",
        display_name="Window Frames",
        type_label="Frame type",
        types=[
            ("metal",     "Metal"),
            ("wood",      "Wood"),
            ("aluminium", "Aluminium"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_TWO_SMOOTH_FINISHES,
    ),
}


# Finish-list helper: single-finish sections (e.g. Pavings)
_ONE_SMOOTH_MATTE_FINISH: list[tuple[str, str]] = [
    ("smooth_matte", "Smooth Matte"),
]


# ---------------------------------------------------------------------------
# EXTERIOR_SECTION_CONFIGS
#
# Config for every supported exterior section.  Reuses the same
# InteriorSectionConfig dataclass with substrate_type="EXTERIOR".
# ---------------------------------------------------------------------------

EXTERIOR_SECTION_CONFIGS: dict[str, "InteriorSectionConfig"] = {
    "exterior_walls": InteriorSectionConfig(
        key="exterior_walls",
        display_name="Exterior Walls",
        type_label="Wall type",
        types=[
            ("brick",  "Brick"),
            ("block",  "Block"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_ALL_FIVE_FINISHES,
        substrate_type="EXTERIOR",
    ),
    "roof": InteriorSectionConfig(
        key="roof",
        display_name="Roof",
        type_label="Roof type",
        types=[
            ("steel",    "Steel"),
            ("concrete", "Concrete"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_TWO_SMOOTH_FINISHES,
        substrate_type="EXTERIOR",
    ),
    "soffits_fascia": InteriorSectionConfig(
        key="soffits_fascia",
        display_name="Soffits / Fascia",
        type_label="Surface type",
        types=[
            ("concrete", "Concrete"),
            ("pvc",      "PVC"),
            ("metal",    "Metal"),
            ("wood",     "Wood"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_FOUR_NO_DECO_FINISHES,
        substrate_type="EXTERIOR",
    ),
    "gutter": InteriorSectionConfig(
        key="gutter",
        display_name="Gutter",
        type_label="Gutter type",
        types=[
            ("concrete", "Concrete"),
            ("pvc",      "PVC"),
            ("metal",    "Metal"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_FOUR_NO_DECO_FINISHES,
        substrate_type="EXTERIOR",
    ),
    "deck_patio": InteriorSectionConfig(
        key="deck_patio",
        display_name="Deck / Patio",
        type_label="Surface type",
        types=[
            ("brick",     "Brick"),
            ("block",     "Block"),
            ("soft_wood", "Soft wood"),
            ("hardwood",  "Hardwood"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_ALL_FIVE_FINISHES,
        substrate_type="EXTERIOR",
    ),
    "fencing": InteriorSectionConfig(
        key="fencing",
        display_name="Fencing",
        type_label="Fence type",
        types=[
            ("concrete",  "Concrete"),
            ("soft_wood", "Soft wood"),
            ("hardwood",  "Hardwood"),
            ("metal",     "Metal"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_FOUR_NO_DECO_FINISHES,
        substrate_type="EXTERIOR",
    ),
    "garage_door": InteriorSectionConfig(
        key="garage_door",
        display_name="Garage Door",
        type_label="Door type",
        types=[
            ("hardwood",  "Hardwood"),
            ("soft_wood", "Soft wood"),
            ("metal",     "Metal"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_FOUR_NO_DECO_FINISHES,
        substrate_type="EXTERIOR",
    ),
    "pavings": InteriorSectionConfig(
        key="pavings",
        display_name="Pavings",
        type_label="Paving type",
        types=[
            ("tar",      "Tar"),
            ("brick",    "Brick"),
            ("concrete", "Concrete"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FLOORS,
        finishes=_ONE_SMOOTH_MATTE_FINISH,
        substrate_type="EXTERIOR",
    ),
    "exterior_window_frames": InteriorSectionConfig(
        key="exterior_window_frames",
        display_name="Exterior Window Frames",
        type_label="Frame type",
        types=[
            ("metal",     "Metal"),
            ("wood",      "Wood"),
            ("aluminium", "Aluminium"),
        ],
        surface_conditions=GENERIC_SURFACE_CONDITIONS_FULL,
        finishes=_TWO_SMOOTH_FINISHES,
        substrate_type="EXTERIOR",
    ),
}


# ---------------------------------------------------------------------------
# Combined lookup: all generic sections (interior + exterior).
# Used by the generic save view and builder to handle any configured section.
# ---------------------------------------------------------------------------

ALL_GENERIC_SECTION_CONFIGS: dict[str, "InteriorSectionConfig"] = {
    **INTERIOR_SECTION_CONFIGS,
    **EXTERIOR_SECTION_CONFIGS,
}
