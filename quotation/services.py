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

    # Monetary totals derived from persisted QuotationLineItem totals
    from decimal import Decimal
    paint_total = Decimal("0.00")
    primer_total = Decimal("0.00")
    waterproof_total = Decimal("0.00")
    prep_total = Decimal("0.00")
    subtotal = Decimal("0.00")
    total_incl = Decimal("0.00")
    for li in all_items:
        excl = Decimal(li.total_excl_vat or 0)
        incl = Decimal(li.total_incl_vat or 0)
        subtotal += excl
        total_incl += incl
        if li.item_type == ItemType.PAINT:
            paint_total += excl
        elif li.item_type == ItemType.PRIMER:
            primer_total += excl
        elif li.item_type == ItemType.WATERPROOFING:
            waterproof_total += excl
        elif li.item_type == ItemType.PREP_WORK:
            prep_total += excl
    vat_amount = total_incl - subtotal

    # Pricing status: consider totals available when subtotal > 0
    pricing_status = "ready" if subtotal and subtotal > Decimal("0.00") else "pending"

    # If pricing is present, surface the builder progress as 100%
    if pricing_status == "ready":
        progress_pct = 100

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
        "pricing_status":    pricing_status,
        "monetary": {
            "paint_total_excl_vat": str(paint_total),
            "primer_total_excl_vat": str(primer_total),
            "waterproofing_total_excl_vat": str(waterproof_total),
            "prep_total_excl_vat": str(prep_total),
            "subtotal_excl_vat": str(subtotal),
            "vat_amount": str(vat_amount),
            "total_incl_vat": str(total_incl),
        },
    }


# ---------------------------------------------------------------------------
# Repeatable selection helpers
# ---------------------------------------------------------------------------
def create_repeatable_section(*, quotation, subsection_key):
    """Create a new repeatable QuotationSection for an already-selected category.

    Behaviour summary:
    - Validate that `subsection_key` is present in the canonical `ALL_SUBSECTIONS`.
    - Within a `transaction.atomic()` block, lock existing sibling rows for
      this (quotation, subsection_key) group using `select_for_update()` so
      concurrent creators serialize.
    - Materialize the locked siblings, compute `next_order = max(existing
      selection_order) + 1`, and create exactly one new placeholder
      `QuotationSection` with `is_placeholder=True`.
    - This helper does not copy or clone any `QuotationLineItem` rows.

    Raises:
    - `ValueError` if the provided key is not known or if the category is
      not already selected on the quotation.
    - Database exceptions such as `IntegrityError` will propagate to the
      caller and are not retried within this function.
    """
    from django.db import transaction
    from django.db.models import Max

    if subsection_key not in ALL_SUBSECTIONS:
        raise ValueError("Invalid subsection_key")

    from .models import QuotationSection

    cfg = ALL_SUBSECTIONS[subsection_key]

    # Use a row-level lock on existing siblings so concurrent creators
    # serialize and we can safely compute the next selection_order.
    with transaction.atomic():
        qs = (
            QuotationSection.objects
            .select_for_update()
            .filter(quotation=quotation, subsection_key=subsection_key)
            .order_by("selection_order", "pk")
        )
        siblings = list(qs)

        # If there are no locked sibling rows the category is not selected
        # for this quotation — preserve the previous validation behaviour.
        if not siblings:
            raise ValueError("Category not selected for quotation")

        max_order = max((s.selection_order or 0) for s in siblings) if siblings else 0
        next_order = max_order + 1

        section = QuotationSection.objects.create(
            quotation=quotation,
            substrate_type=cfg.substrate,
            subsection_key=subsection_key,
            display_name=f"{cfg.display_name} {next_order}",
            sort_order=cfg.sort_order,
            selection_order=next_order,
            is_placeholder=True,
        )

        return section


def delete_repeatable_section(*, quotation, section_pk):
    """Delete a single QuotationSection and renumber remaining siblings.

    Strategy:
    - Delete the target section.
    - If siblings remain for the same (quotation, subsection_key) group,
      renumber them to contiguous values using a two-phase update to avoid
      uniqueness collisions.
    - If no siblings remain, the category is considered unselected and no
      placeholder is created.

    Returns True on success, or None if the category became empty.
    """
    from django.db import transaction

    from .models import QuotationSection

    with transaction.atomic():
        sec = QuotationSection.objects.get(pk=section_pk, quotation=quotation)
        key = sec.subsection_key
        # Delete the target section
        sec.delete()

        siblings = list(
            QuotationSection.objects.filter(quotation=quotation, subsection_key=key)
            .order_by("selection_order", "pk")
        )

        if not siblings:
            # No remaining selections for this category: category is removed
            return None

        # Capture original ordering (selection_order, pk)
        orig = [(s.pk, s.selection_order) for s in siblings]
        max_old = max(o for _, o in orig) if orig else 0
        offset = max_old + 1000

        # Phase 1: move to high-offset values to avoid uniqueness collisions
        for s in siblings:
            QuotationSection.objects.filter(pk=s.pk).update(selection_order=s.selection_order + offset)

        # Phase 2: assign contiguous values in desired order (by old sort)
        ordered = sorted(orig, key=lambda x: (x[1], x[0]))
        for idx, (pk, _) in enumerate(ordered, start=1):
            QuotationSection.objects.filter(pk=pk).update(selection_order=idx)

        return True


def get_leaflet_groups(quotation) -> list:
    """
    Build an ordered list of leaflet/category groups from existing
    `QuotationSection` rows for the provided `quotation`.

    Returns a list of dicts with the keys:

    - `key`: subsection_key
    - `display_name`: canonical display name (from `ALL_SUBSECTIONS`),
      or fallback to the section's `display_name` for unknown keys.
    - `substrate_type`: canonical substrate type or fallback from section.
    - `sort_order`: canonical category sort order or fallback from section.
    - `selection_count`: number of selections in this group.
    - `selections`: ordered list of selection dicts with:
        - `section`: the `QuotationSection` object
        - `section_pk`: stable PK of the section
        - `selection_order`: the numeric order for the selection
        - `selection_label`: human label for the selection (e.g. "Interior Walls 1")

    Behaviour notes:
    - Only categories with at least one `QuotationSection` for this
      quotation are included.
    - Categories are ordered by `sort_order` (canonical if available),
      then by display name as a stable tie-breaker.
    - Selections within a category are ordered by `selection_order`, then PK.
    - This helper performs no database writes.
    - Unknown/historical `subsection_key` values are handled safely using
      the existing section fields as a fallback.
    """
    from .models import QuotationSection

    # Query all sections for the quotation ordered for deterministic grouping
    secs = list(
        QuotationSection.objects.filter(quotation=quotation)
        .order_by("sort_order", "selection_order", "pk")
    )

    # Group by subsection_key
    groups: dict[str, list[QuotationSection]] = {}
    for s in secs:
        groups.setdefault(s.subsection_key, []).append(s)

    result: list[dict] = []
    for key, items in groups.items():
        cfg = ALL_SUBSECTIONS.get(key)
        if cfg:
            display_name = cfg.display_name
            substrate_type = cfg.substrate
            cat_sort = cfg.sort_order
        else:
            # Safe fallback for historical/unknown keys
            first = items[0]
            display_name = first.display_name
            substrate_type = first.substrate_type
            cat_sort = first.sort_order

        ordered = sorted(items, key=lambda s: (s.selection_order or 0, s.pk))

        selections = []
        for s in ordered:
            if cfg:
                sel_label = f"{display_name} {s.selection_order}"
            else:
                sel_label = s.display_name
            selections.append({
                "section": s,
                "section_pk": s.pk,
                "selection_order": s.selection_order,
                "selection_label": sel_label,
            })

        result.append({
            "key": key,
            "display_name": display_name,
            "substrate_type": substrate_type,
            "sort_order": cat_sort,
            "selection_count": len(ordered),
            "selections": selections,
        })

    # Deterministic category ordering: sort_order, then display_name (or key)
    result.sort(key=lambda g: (g["sort_order"], g["display_name"] or g["key"]))
    return result
