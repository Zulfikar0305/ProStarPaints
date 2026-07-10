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

from quotation.models import QuotationLineItem
from quotation.pricing import calculate_product_pricing

# Helper to mimic apply_paint_pricing_to_line_item snapshot construction
from decimal import Decimal

def _maybe_decimal(v):
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def build_calc_snapshot_from_line(li: QuotationLineItem) -> dict:
    meta = dict(li.metadata or {})
    ps = meta.get('product_snapshot')
    if ps is None:
        paint = li.paint
        ps = {
            'paint_pk': int(paint.pk) if paint and paint.pk is not None else None,
            'pricing_method': str(paint.pricing_method) if paint else None,
            'category': str(paint.category) if paint else None,
            'price_excl_vat': str(li.price_excl_vat),
            'price_incl_vat': str(li.price_incl_vat),
            'priced_volume_litres': str(getattr(paint, 'priced_volume_litres', None)) if paint else None,
            'spread_rate_per_litre': str(getattr(paint, 'spread_rate_per_litre', None)) if paint else None,
            'package_size': str(getattr(paint, 'package_size', None)) if paint else None,
            'package_unit': str(getattr(paint, 'package_unit', "")) if paint else None,
            'variant_label': str(getattr(paint, 'variant_label', "")) if paint else None,
            'predetermined_note': str(getattr(paint, 'predetermined_note', "")) if paint else None,
            'standard_coats': int(getattr(paint, 'standard_coats', None)) if getattr(paint, 'standard_coats', None) is not None else None,
            'finish': str(getattr(paint, 'finish', None)) if getattr(paint, 'finish', None) is not None else None,
            'base_type': str(getattr(paint, 'base_type', None)) if getattr(paint, 'base_type', None) is not None else None,
        }
        # overlay legacy top-level metadata keys if present
        for legacy_key in ("package_size", "package_unit", "spread_rate_per_litre", "priced_volume_litres", "price_excl_vat", "price_incl_vat"):
            if meta.get(legacy_key) is not None:
                ps[legacy_key] = meta.get(legacy_key)
    return ps


# Scan for paint-like items
ItemType = QuotationLineItem.ItemType
qset = QuotationLineItem.objects.filter(item_type__in=[ItemType.PAINT, ItemType.PRIMER, ItemType.WATERPROOFING])

mismatches = []
checked = 0
for li in qset.select_related('quotation', 'paint'):
    checked += 1
    calc_snapshot = build_calc_snapshot_from_line(li)
    # convert numeric-string fields to Decimal
    calc_snapshot_conv = dict(calc_snapshot)
    calc_snapshot_conv['price_excl_vat'] = _maybe_decimal(calc_snapshot.get('price_excl_vat'))
    calc_snapshot_conv['price_incl_vat'] = _maybe_decimal(calc_snapshot.get('price_incl_vat'))
    calc_snapshot_conv['priced_volume_litres'] = _maybe_decimal(calc_snapshot.get('priced_volume_litres'))
    calc_snapshot_conv['spread_rate_per_litre'] = _maybe_decimal(calc_snapshot.get('spread_rate_per_litre'))
    calc_snapshot_conv['package_size'] = _maybe_decimal(calc_snapshot.get('package_size'))

    try:
        res = calculate_product_pricing(calc_snapshot_conv, area_sqm=li.area_sqm, coats=li.coats)
    except Exception as e:
        mismatches.append({'line_pk': li.pk, 'error': str(e), 'note': 'calculate_product_pricing crashed'})
        continue

    # Only consider priced results
    if res.get('pricing_status') != 'priced':
        continue

    calc_total = res.get('total_excl_vat')
    stored_total = (li.total_excl_vat or Decimal('0.00'))

    # Compare as strings to avoid Decimal context differences
    if calc_total is None:
        calc_total = Decimal('0.00')
    if Decimal(str(calc_total)) != Decimal(str(stored_total)):
        mismatches.append({
            'line_pk': li.pk,
            'quotation_pk': li.quotation.pk if li.quotation else None,
            'quotation_ref': li.quotation.reference if li.quotation else None,
            'description': li.description,
            'stored_total': str(stored_total),
            'calc_total': str(calc_total),
            'product_snapshot_present': 'product_snapshot' in (li.metadata or {}),
            'metadata': li.metadata or {},
        })

# Print summary
print('Checked lines:', checked)
print('Mismatches found:', len(mismatches))
if mismatches:
    print('\nSample mismatches (up to 20):')
    for m in mismatches[:20]:
        print(json.dumps(m, indent=2, default=str))

# Exit code non-zero if mismatches exist to draw attention
if mismatches:
    sys.exit(2)
else:
    sys.exit(0)
