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
    SubsectionConfig("soffits_fascia",               "Soffits / Fascia",                "EXTERIOR", 3),
    SubsectionConfig("gutter",                       "Gutter",                          "EXTERIOR", 4),
    SubsectionConfig("deck_patio",                   "Deck / Patio",                    "EXTERIOR", 5),
    SubsectionConfig("fencing",                      "Fencing",                         "EXTERIOR", 6),
    SubsectionConfig("garage_door",                  "Garage Door",                     "EXTERIOR", 7),
    SubsectionConfig("pavings",                      "Pavings",                         "EXTERIOR", 8),
    SubsectionConfig("exterior_window_frames",       "Exterior Window Frames",          "EXTERIOR", 9),
]

# Flat lookup: key → SubsectionConfig
ALL_SUBSECTIONS: dict[str, SubsectionConfig] = {
    s.key: s
    for s in INTERIOR_SUBSECTIONS + EXTERIOR_SUBSECTIONS
}


# ---------------------------------------------------------------------------
# Quotation summary (for builder live panel)
# ---------------------------------------------------------------------------

def get_quotation_summary(quotation) -> dict:
    """
    Return a structured summary dict for the builder's live summary panel.
    No pricing logic — all financial fields are returned as "pending".

    Performs two DB queries: one for sections, one for all line items.
    """
    from .config import MOISTURE_WARNING_THRESHOLD
    from .models import QuotationLineItem

    ItemType = QuotationLineItem.ItemType

    sections: list = list(quotation.sections.order_by("sort_order"))
    all_items: list = list(
        QuotationLineItem.objects.filter(quotation=quotation).select_related("section")
    )

    # Index items by section pk for O(1) lookup
    items_by_section: dict = {}
    for li in all_items:
        items_by_section.setdefault(li.section_id, []).append(li)

    configured_count = 0
    paint_count = primer_count = waterproofing_count = prep_count = 0
    moisture_warnings: list[dict] = []
    section_summaries: list[dict] = []

    for section in sections:
        sec_items = items_by_section.get(section.pk, [])
        note_item = next((li for li in sec_items if li.item_type == ItemType.NOTE), None)
        configured = note_item is not None

        if configured:
            configured_count += 1

        moisture_level: int = 0
        if note_item and note_item.metadata:
            try:
                moisture_level = int(note_item.metadata.get("moisture_level") or 0)
            except (ValueError, TypeError):
                moisture_level = 0

        has_moisture_warning = configured and moisture_level > MOISTURE_WARNING_THRESHOLD
        if has_moisture_warning:
            moisture_warnings.append(
                {"section_name": section.display_name, "moisture_value": moisture_level}
            )

        # Count non-NOTE items per type (globally and for section badge)
        non_note_count = 0
        for li in sec_items:
            t = li.item_type
            if t == ItemType.PAINT:
                paint_count += 1
                non_note_count += 1
            elif t == ItemType.PRIMER:
                primer_count += 1
                non_note_count += 1
            elif t == ItemType.WATERPROOFING:
                waterproofing_count += 1
                non_note_count += 1
            elif t == ItemType.PREP_WORK:
                prep_count += 1
                non_note_count += 1

        section_summaries.append(
            {
                "section_name":       section.display_name,
                "substrate_type":     section.substrate_type,
                "configured":         configured,
                "line_item_count":    non_note_count,
                "has_moisture_warning": has_moisture_warning,
                "moisture_level":     moisture_level,
            }
        )

    total_sections = len(sections)
    progress_pct = round(configured_count / total_sections * 100) if total_sections else 0

    return {
        "customer_name":     quotation.customer_name,
        "project_name":      quotation.project_name or quotation.project_location,
        "total_sections":    total_sections,
        "configured_count":  configured_count,
        "unconfigured_count": total_sections - configured_count,
        "progress_pct":      progress_pct,
        "section_summaries": section_summaries,
        "item_counts": {
            "paint":          paint_count,
            "primer":         primer_count,
            "waterproofing":  waterproofing_count,
            "prep_work":      prep_count,
            "total":          paint_count + primer_count + waterproofing_count + prep_count,
        },
        "moisture_warnings": moisture_warnings,
        "pricing_status":    "pending",
    }
