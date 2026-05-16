"""
quotation.services
==================
Substrate / subsection configuration for the Quotation Builder.

Each subsection is a lightweight dataclass that carries:
- key          : machine-readable identifier (stored in QuotationSection.subsection_key)
- display_name : human-readable label
- substrate    : "INTERIOR" | "EXTERIOR"
- sort_order   : relative ordering within its group (0-indexed)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubsectionConfig:
    key: str
    display_name: str
    substrate: str
    sort_order: int


# ---------------------------------------------------------------------------
# Interior subsections
# ---------------------------------------------------------------------------

INTERIOR_SUBSECTIONS: list[SubsectionConfig] = [
    SubsectionConfig("interior_walls",          "Interior Walls",            "INTERIOR", 0),
    SubsectionConfig("ceilings",                "Ceilings",                  "INTERIOR", 1),
    SubsectionConfig("floors",                  "Floors",                    "INTERIOR", 2),
    SubsectionConfig("doors_trims_skirtings",   "Doors, Trims & Skirtings",  "INTERIOR", 3),
    SubsectionConfig("window_frames",           "Window Frames",             "INTERIOR", 4),
]

# ---------------------------------------------------------------------------
# Exterior subsections
# ---------------------------------------------------------------------------

EXTERIOR_SUBSECTIONS: list[SubsectionConfig] = [
    SubsectionConfig("exterior_walls",               "Exterior Walls",                  "EXTERIOR", 0),
    SubsectionConfig("exterior_doors_trims_skirtings","Exterior Doors, Trims & Skirtings","EXTERIOR", 1),
    SubsectionConfig("roof",                         "Roof",                            "EXTERIOR", 2),
    SubsectionConfig("soffits_fascia",               "Soffits & Fascia",                "EXTERIOR", 3),
    SubsectionConfig("gutter",                       "Gutter",                          "EXTERIOR", 4),
    SubsectionConfig("deck_patio",                   "Deck / Patio",                    "EXTERIOR", 5),
    SubsectionConfig("fencing",                      "Fencing",                         "EXTERIOR", 6),
    SubsectionConfig("garage_door",                  "Garage Door",                     "EXTERIOR", 7),
    SubsectionConfig("pavings",                      "Pavings",                         "EXTERIOR", 8),
]

# Flat lookup: key → SubsectionConfig
ALL_SUBSECTIONS: dict[str, SubsectionConfig] = {
    s.key: s
    for s in INTERIOR_SUBSECTIONS + EXTERIOR_SUBSECTIONS
}
