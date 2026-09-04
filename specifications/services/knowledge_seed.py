"""Default authoritative specification knowledge seeds.

These entries are intentionally lightweight but selection-aware. They provide the
live fallback content that the resolver consults when a quotation section is
configured without a bespoke manual override. The seed covers every supported
builder section and distinguishes common substrate, finish, and material families.
"""

from __future__ import annotations

from typing import Any, Iterable

from quotation.config import ALL_GENERIC_SECTION_CONFIGS
from specifications.models import KnowledgeEntry


def _default_knowledge_rows() -> Iterable[dict[str, Any]]:
    """Return the authoritative default knowledge entries for generic sections."""
    return [
        {
            "title": "Interior walls – drywall matte system",
            "body": "Prepare plasterboard surfaces by cleaning, filling, and sanding. Apply a compatible primer and lay down a durable matte finish for standard interior walls.",
            "metadata": {
                "section_key": "interior_walls",
                "substrate_type": "INTERIOR",
                "types": ["drywall", "plasterboard", "gypsum_boards"],
                "surface_conditions": ["new", "previously_painted"],
                "finishes": ["smooth_matte", "smooth_sheen"],
                "product_groups": ["pure_matte", "pro_sheen"],
                "preparations": ["cleaning", "sanding", "filling"],
                "primers": ["gp_universal"],
                "application": "interior",
                "tags": ["seed_default", "authoritative", "interior_walls"],
            },
            "priority": 100,
        },
        {
            "title": "Interior walls – brick repair and primer system",
            "body": "Brick interior walls need masonry-compatible preparation, crack repair, and a primer before the final coating is applied.",
            "metadata": {
                "section_key": "interior_walls",
                "substrate_type": "INTERIOR",
                "types": ["brick", "block"],
                "surface_conditions": ["new", "previously_painted", "cracks", "peeling", "mould", "efflorescence", "rough"],
                "finishes": ["smooth_matte", "fine_texture"],
                "product_groups": ["pure_matte", "texture_pro_fine"],
                "preparations": ["cleaning", "filling", "sanding", "mould_treatment", "efflor_removal", "remove_paint"],
                "primers": ["gp_universal", "masonry_sealer"],
                "application": "interior",
                "tags": ["seed_default", "authoritative", "interior_walls", "brick_masonry"],
            },
            "priority": 110,
        },
        {
            "title": "Interior walls – drywall repair and sheen system",
            "body": "Drywall and plasterboard should be repaired, degreased and coated with a sheen or smooth finish suited to interior use.",
            "metadata": {
                "section_key": "interior_walls",
                "substrate_type": "INTERIOR",
                "types": ["drywall", "plasterboard", "gypsum_boards"],
                "surface_conditions": ["new", "previously_painted", "cracks", "rough", "stained"],
                "finishes": ["smooth_matte", "smooth_sheen", "deco_plast"],
                "product_groups": ["pure_matte", "pro_sheen", "deco_plast_1mm"],
                "preparations": ["cleaning", "sanding", "filling", "patching"],
                "primers": ["gp_universal"],
                "application": "interior",
                "tags": ["seed_default", "authoritative", "interior_walls", "drywall_sheen"],
            },
            "priority": 110,
        },
        {
            "title": "Brick masonry primer system",
            "body": "Brick surfaces need a masonry primer and a matte finish selected for exterior wall service.",
            "metadata": {
                "substrate_type": "EXTERIOR",
                "types": ["brick"],
                "surface_conditions": ["new"],
                "finishes": ["smooth_matte"],
                "product_groups": ["pure_matte"],
                "tags": ["seed_default", "authoritative", "brick_masonry"],
            },
            "priority": 110,
        },
        {
            "title": "Drywall sheen system",
            "body": "Drywall and plasterboard should be prepared and coated using a sheen system sized to interior wear.",
            "metadata": {
                "substrate_type": "INTERIOR",
                "types": ["drywall"],
                "surface_conditions": ["previously_painted"],
                "finishes": ["smooth_sheen"],
                "product_groups": ["pro_sheen"],
                "tags": ["seed_default", "authoritative", "drywall_sheen"],
            },
            "priority": 110,
        },
        {
            "title": "Ceilings – gypsum board matte guidance",
            "body": "Ceiling substrates should be cleaned and sealed before application. Use a smooth matte or sheen finish where the substrate is gypsum board.",
            "metadata": {
                "section_key": "ceilings",
                "substrate_type": "INTERIOR",
                "types": ["concrete_socket", "gypsum_boards"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "deco_plast", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "deco_plast_1mm", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding"],
                "primers": ["gp_universal"],
                "application": "interior",
                "tags": ["seed_default", "authoritative", "ceilings"],
            },
            "priority": 95,
        },
        {
            "title": "Floors – hardwood smooth finish",
            "body": "For timber floors, ensure a sound, dry substrate and use a smooth finish suited to wear, traffic and preparation conditions.",
            "metadata": {
                "section_key": "floors",
                "substrate_type": "INTERIOR",
                "types": ["concrete", "soft_wood", "hardwood"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen"],
                "preparations": ["cleaning", "sanding"],
                "primers": ["gp_universal"],
                "application": "interior",
                "tags": ["seed_default", "authoritative", "floors"],
            },
            "priority": 95,
        },
        {
            "title": "Doors, trims & skirtings – timber finish guidance",
            "body": "Timber and metal joins require a durable finish and proper surface cleaning. Select a finish that tolerates handling and touch-up.",
            "metadata": {
                "section_key": "doors_trims_skirtings",
                "substrate_type": "INTERIOR",
                "types": ["hardwood", "soft_wood", "metal"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding", "filling"],
                "primers": ["gp_universal"],
                "application": "interior",
                "tags": ["seed_default", "authoritative", "doors_trims_skirtings"],
            },
            "priority": 90,
        },
        {
            "title": "Window frames – aluminium smooth sheen guidance",
            "body": "Window frames should be properly degreased and coated using a smooth, durable finish that handles environmental exposure and regular wiping.",
            "metadata": {
                "section_key": "window_frames",
                "substrate_type": "INTERIOR",
                "types": ["metal", "wood", "aluminium"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_sheen", "smooth_matte"],
                "product_groups": ["pro_sheen", "pure_matte", "pro_coat"],
                "preparations": ["cleaning", "sanding"],
                "primers": ["gp_universal"],
                "application": "interior",
                "tags": ["seed_default", "authoritative", "window_frames"],
            },
            "priority": 90,
        },
        {
            "title": "Exterior walls – brick masonry matte system",
            "body": "Use a masonry-compatible preparation and primer for brick walls, followed by a matte finish suitable for exterior exposure.",
            "metadata": {
                "section_key": "exterior_walls",
                "substrate_type": "EXTERIOR",
                "types": ["brick", "block"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "efflor_removal", "filling"],
                "primers": ["aqua_prime", "plaster_primerseal"],
                "waterproofing": ["hydro_shield", "aqua_proof"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "exterior_walls"],
            },
            "priority": 100,
        },
        {
            "title": "Exterior trims – hardwood masonry finish",
            "body": "Timber and metal exterior trims require cleaning, sanding and a suitable primer ahead of the final finish.",
            "metadata": {
                "section_key": "exterior_doors_trims_skirtings",
                "substrate_type": "EXTERIOR",
                "types": ["hardwood", "soft_wood", "metal"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding", "filling"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "exterior_doors_trims_skirtings"],
            },
            "priority": 95,
        },
        {
            "title": "Roof – steel protective coating",
            "body": "Roof steel should be prepared, primed and coated with a durable protective system selected for metal roof conditions.",
            "metadata": {
                "section_key": "roof",
                "substrate_type": "EXTERIOR",
                "types": ["steel"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen"],
                "preparations": ["cleaning", "sanding", "rust_treatment"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_repel", "hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "roof", "steel"],
            },
            "priority": 90,
        },
        {
            "title": "Roof – concrete protective coating",
            "body": "Concrete roofs require compatible preparation, moisture checks and a coating system selected for concrete substrate conditions.",
            "metadata": {
                "section_key": "roof",
                "substrate_type": "EXTERIOR",
                "types": ["concrete"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen"],
                "preparations": ["cleaning", "sanding", "efflor_removal"],
                "primers": ["aqua_prime", "plaster_primerseal"],
                "waterproofing": ["hydro_shield", "aqua_proof"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "roof", "concrete"],
            },
            "priority": 88,
        },
        {
            "title": "Soffits / fascia – pvc and wood finish",
            "body": "Soffits and fascia elements should be cleaned and primed before any coated finish is applied to protect against exposure.",
            "metadata": {
                "section_key": "soffits_fascia",
                "substrate_type": "EXTERIOR",
                "types": ["concrete", "pvc", "wood", "metal"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "soffits_fascia"],
            },
            "priority": 90,
        },
        {
            "title": "Gutter – metal drainage coating",
            "body": "Metal gutters and drainage systems should be cleaned, primed where required and coated with a hard-wearing finish appropriate for wet exterior conditions.",
            "metadata": {
                "section_key": "gutter",
                "substrate_type": "EXTERIOR",
                "types": ["metal"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "gutter", "metal"],
            },
            "priority": 90,
        },
        {
            "title": "Gutter – pvc drainage system",
            "body": "PVC gutters require a compatible cleaning and surface preparation regime with a finish selected to suit plastic drainage components and exposure conditions.",
            "metadata": {
                "section_key": "gutter",
                "substrate_type": "EXTERIOR",
                "types": ["pvc"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "degreasing"],
                "primers": ["gp_universal"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "gutter", "pvc"],
            },
            "priority": 88,
        },
        {
            "title": "Gutter – generic drainage fallback",
            "body": "General gutter drainage surfaces require cleaning, inspection and a weather-resistant coating selected to suit the substrate and exposure conditions.",
            "metadata": {
                "section_key": "gutter",
                "substrate_type": "EXTERIOR",
                "types": ["concrete"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "inspection"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "gutter", "generic_fallback"],
            },
            "priority": 70,
        },
        {
            "title": "Deck / patio – non-slip exterior system",
            "body": "Deck and patio surfaces need an exterior-appropriate finish that balances durability and slip resistance while remaining breathable.",
            "metadata": {
                "section_key": "deck_patio",
                "substrate_type": "EXTERIOR",
                "types": ["brick", "block", "hardwood", "soft_wood"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding", "filling"],
                "primers": ["aqua_prime"],
                "waterproofing": ["hydro_shield", "moistseal"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "deck_patio"],
            },
            "priority": 90,
        },
        {
            "title": "Fencing – timber and metal finish guidance",
            "body": "Fencing substrates must be sound, dry and correctly primed before applying a weather-resistant finish suitable for exterior use.",
            "metadata": {
                "section_key": "fencing",
                "substrate_type": "EXTERIOR",
                "types": ["concrete", "hardwood", "soft_wood", "metal"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding", "filling"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "fencing"],
            },
            "priority": 88,
        },
        {
            "title": "Garage door – metal and timber coating system",
            "body": "Garage doors require a durable finish with suitable cleaning and preparation for repeated handling and outdoor conditions.",
            "metadata": {
                "section_key": "garage_door",
                "substrate_type": "EXTERIOR",
                "types": ["hardwood", "soft_wood", "metal"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte", "smooth_sheen", "fine_texture", "coarse_texture"],
                "product_groups": ["pure_matte", "pro_coat", "pro_sheen", "texture_pro_fine", "texture_pro_medium_coarse"],
                "preparations": ["cleaning", "sanding", "filling"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "garage_door"],
            },
            "priority": 88,
        },
        {
            "title": "Pavings – concrete matte system",
            "body": "Paving substrates should be sound, clean and dry before any coating is placed; choose a matte finish suited to traffic and exposure.",
            "metadata": {
                "section_key": "pavings",
                "substrate_type": "EXTERIOR",
                "types": ["tar", "brick", "concrete"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_matte"],
                "product_groups": ["pure_matte", "pro_coat"],
                "preparations": ["cleaning", "filling"],
                "primers": ["aqua_prime"],
                "waterproofing": ["hydro_shield", "moistseal"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "pavings"],
            },
            "priority": 87,
        },
        {
            "title": "Exterior window frames – aluminium sheen guidance",
            "body": "Exterior window frames require a durable, weather-resistant finish with careful preparation and a compatible primer.",
            "metadata": {
                "section_key": "exterior_window_frames",
                "substrate_type": "EXTERIOR",
                "types": ["aluminium", "wood", "metal"],
                "surface_conditions": ["prev_painted_good", "prev_painted_poor", "prev_painted_chalky", "prev_painted_mouldy", "unpainted"],
                "finishes": ["smooth_sheen", "smooth_matte"],
                "product_groups": ["pro_sheen", "pure_matte", "pro_coat"],
                "preparations": ["cleaning", "sanding"],
                "primers": ["gp_universal", "aqua_prime"],
                "waterproofing": ["hydro_shield"],
                "application": "exterior",
                "tags": ["seed_default", "authoritative", "exterior_window_frames"],
            },
            "priority": 90,
        },
    ]


def seed_default_specification_knowledge():
    """Create or update the default authoritative knowledge entries for generic sections."""
    default_rows = list(_default_knowledge_rows())
    seeded = []

    for row in default_rows:
        title = row["title"]
        metadata = row["metadata"]
        defaults = {
            "body": row["body"],
            "kind": KnowledgeEntry.KIND_CLAUSE,
            "is_default": True,
            "is_active": True,
            "is_published": True,
            "priority": row.get("priority", 0),
            "sort_order": row.get("priority", 0),
            "tags": metadata.get("tags", []),
            "metadata": metadata,
        }
        entry, _ = KnowledgeEntry.objects.update_or_create(
            title=title,
            defaults=defaults,
        )
        seeded.append(entry)

    # Keep the seed known to the app by tagging it consistently without requiring a migration.
    seeded_titles = {entry.title for entry in seeded}
    for entry in KnowledgeEntry.objects.filter(is_active=True):
        current_tags = entry.tags or []
        if "seed_default" in current_tags and entry.title not in seeded_titles:
            entry.delete()
    return seeded
