#!/usr/bin/env python3
import os
import sys
import json
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from quotation.models import Quotation, QuotationLineItem
from quotation.pricing import calculate_product_pricing
from quotation.services import get_quotation_summary
from quotation.pdf_service import build_pdf_context
from quotation.spec_report import generate_spec_for_sections

# Find a quotation with at least one PAINT line
q = Quotation.objects.filter(line_items__item_type=QuotationLineItem.ItemType.PAINT).distinct().first()
if not q:
    print('NO_QUOTATION_FOUND')
    sys.exit(0)

# Pick the first paint line
li = q.line_items.filter(item_type=QuotationLineItem.ItemType.PAINT).select_related('paint').first()
if not li:
    print('NO_PAINT_LINE_FOUND')
    sys.exit(0)

print('--- TRACE START ---')
print(f'Quotation: pk={q.pk}, reference={q.reference}')
print(f'Line item: pk={li.pk}, item_type={li.item_type}, description={li.description}')
print('\n-- Stored Line Fields --')
print('price_excl_vat:', li.price_excl_vat)
print('price_incl_vat:', li.price_incl_vat)
print('area_sqm:', li.area_sqm)
print('coats:', li.coats)
print('quantity:', li.quantity)
print('unit:', li.unit)
print('total_excl_vat:', li.total_excl_vat)
print('total_incl_vat:', li.total_incl_vat)
print('metadata:', json.dumps(li.metadata or {}, indent=2, default=str))

# Product info
print('\n-- Product Record (if linked) --')
if li.paint:
    p = li.paint
    print('paint.pk:', p.pk)
    print('paint.name:', p.name)
    print('pricing_method:', getattr(p, 'pricing_method', None))
    print('price_excl_vat:', getattr(p, 'price_excl_vat', None))
    print('price_incl_vat:', getattr(p, 'price_incl_vat', None))
    print('priced_volume_litres:', getattr(p, 'priced_volume_litres', None))
    print('package_size:', getattr(p, 'package_size', None))
    print('package_unit:', getattr(p, 'package_unit', None))
    print('spread_rate_per_litre:', getattr(p, 'spread_rate_per_litre', None))
else:
    print('No linked paint')

# Reconstruct product snapshot as apply_paint_pricing_to_line_item would
print('\n-- Reconstructed Calculation Snapshot --')
meta = dict(li.metadata or {})
product_snapshot = meta.get('product_snapshot')
if product_snapshot is None:
    # Build snapshot similar to apply_paint_pricing_to_line_item
    ps = {
        'paint_pk': int(li.paint.pk) if li.paint and li.paint.pk is not None else None,
        'pricing_method': str(li.paint.pricing_method) if li.paint else None,
        'category': str(li.paint.category) if li.paint else None,
        'price_excl_vat': str(li.price_excl_vat),
        'price_incl_vat': str(li.price_incl_vat),
        'priced_volume_litres': str(getattr(li.paint, 'priced_volume_litres', None)) if li.paint else None,
        'spread_rate_per_litre': str(getattr(li.paint, 'spread_rate_per_litre', None)) if li.paint else None,
        'package_size': str(getattr(li.paint, 'package_size', None)) if li.paint else None,
        'package_unit': str(getattr(li.paint, 'package_unit', '')) if li.paint else None,
        'variant_label': str(getattr(li.paint, 'variant_label', '')) if li.paint else None,
        'predetermined_note': str(getattr(li.paint, 'predetermined_note', '')) if li.paint else None,
        'standard_coats': int(getattr(li.paint, 'standard_coats')) if getattr(li.paint, 'standard_coats', None) is not None else None,
        'finish': str(getattr(li.paint, 'finish', None)) if getattr(li.paint, 'finish', None) is not None else None,
        'base_type': str(getattr(li.paint, 'base_type', None)) if getattr(li.paint, 'base_type', None) is not None else None,
    }
    product_snapshot = ps

print(json.dumps(product_snapshot, indent=2, default=str))

# Convert numeric-string fields to Decimal where required by dispatcher
from decimal import Decimal

def _maybe_decimal(v):
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None

calc_snapshot_conv = dict(product_snapshot)
calc_snapshot_conv['price_excl_vat'] = _maybe_decimal(product_snapshot.get('price_excl_vat'))
calc_snapshot_conv['price_incl_vat'] = _maybe_decimal(product_snapshot.get('price_incl_vat'))
calc_snapshot_conv['priced_volume_litres'] = _maybe_decimal(product_snapshot.get('priced_volume_litres'))
calc_snapshot_conv['spread_rate_per_litre'] = _maybe_decimal(product_snapshot.get('spread_rate_per_litre'))
calc_snapshot_conv['package_size'] = _maybe_decimal(product_snapshot.get('package_size'))

print('\n-- Dispatcher Input (calc_snapshot_conv) --')
print(json.dumps({k: str(v) if isinstance(v, Decimal) else v for k,v in calc_snapshot_conv.items()}, indent=2))

# Call calculate_product_pricing
print('\n-- calculate_product_pricing Result --')
res = calculate_product_pricing(calc_snapshot_conv, area_sqm=li.area_sqm, coats=li.coats)

def _json_safe(obj):
    """Recursively convert Decimal to str for JSON-safe printing."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj

print(json.dumps(_json_safe(res), indent=2))

# Compare result totals to stored
print('\n-- Comparison --')
print('calc.total_excl_vat:', res.get('total_excl_vat'))
print('stored.total_excl_vat:', li.total_excl_vat)
print('EQUAL?', str(res.get('total_excl_vat')) == str(li.total_excl_vat))

# Quotation summary
print('\n-- Quotation Summary (get_quotation_summary) --')
sumry = get_quotation_summary(q)
print(json.dumps(sumry.get('monetary'), indent=2))

# PDF context
print('\n-- PDF Context (build_pdf_context) --')
ctx = build_pdf_context(q)
# Find section containing our line
found = False
for sec in ctx.get('sections', []):
    for item in sec.get('line_items', []):
        it = item.get('item')
        if it and getattr(it, 'pk', None) == li.pk:
            print('Found in PDF section:', sec.get('section').display_name if sec.get('section') else None)
            print('section_total_excl_vat:', sec.get('section_total_excl_vat'))
            print('item total_excl_vat from DB:', getattr(it, 'total_excl_vat', None))
            found = True
            break
    if found:
        break
if not found:
    print('Line not present in PDF context?')

# Spec report
print('\n-- Spec Report (generate_spec_for_sections) --')
from quotation.spec_report import generate_spec_for_sections
sections = ctx.get('sections')
enriched = generate_spec_for_sections(sections)
# locate material summary entry for our line
found = False
for sec in enriched:
    for m in sec.get('material_summary', []):
        if m.get('line_item_pk') == li.pk:
            print('Spec report est_material_cost:', m.get('est_material_cost'))
            found = True
            break
    if found:
        break
if not found:
    print('Line not present in spec report material summary?')

print('\n--- TRACE END ---')
