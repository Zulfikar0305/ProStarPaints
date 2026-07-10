#!/usr/bin/env python3
import os, sys, json
from decimal import Decimal, ROUND_CEILING

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from quotation.models import QuotationLineItem
from quotation.pricing import calculate_product_pricing

LINE_PKS = [157, 159]

from decimal import Decimal

def _to_json_safe(v):
    if isinstance(v, Decimal):
        return str(v)
    return v

def _maybe_decimal(v):
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None

for pk in LINE_PKS:
    try:
        li = QuotationLineItem.objects.select_related('quotation','paint').get(pk=pk)
    except QuotationLineItem.DoesNotExist:
        print(f'Line {pk} not found')
        continue
    meta = dict(li.metadata or {})
    ps = meta.get('product_snapshot')
    paint = li.paint
    created_snapshot = False
    if ps is None and paint is not None:
        ps = {
            'paint_pk': int(paint.pk) if paint and paint.pk is not None else None,
            'pricing_method': str(paint.pricing_method),
            'category': str(paint.category),
            'price_excl_vat': _to_json_safe(li.price_excl_vat),
            'price_incl_vat': _to_json_safe(li.price_incl_vat),
            'priced_volume_litres': _to_json_safe(getattr(paint, 'priced_volume_litres', None)),
            'spread_rate_per_litre': _to_json_safe(getattr(paint, 'spread_rate_per_litre', None)),
            'package_size': _to_json_safe(getattr(paint, 'package_size', None)),
            'package_unit': str(getattr(paint, 'package_unit', '')),
            'variant_label': str(getattr(paint, 'variant_label', '')),
            'predetermined_note': str(getattr(paint, 'predetermined_note', '')),
            'standard_coats': int(getattr(paint, 'standard_coats', None)) if getattr(paint, 'standard_coats', None) is not None else None,
            'finish': str(getattr(paint, 'finish', None)) if getattr(paint, 'finish', None) is not None else None,
            'base_type': str(getattr(paint, 'base_type', None)) if getattr(paint, 'base_type', None) is not None else None,
        }
        # overlay legacy metadata
        for legacy_key in ("package_size", "package_unit", "spread_rate_per_litre", "priced_volume_litres", "price_excl_vat", "price_incl_vat"):
            if meta.get(legacy_key) is not None:
                ps[legacy_key] = _to_json_safe(meta.get(legacy_key))
        created_snapshot = True

    calc_snapshot = dict(ps) if ps is not None else {}
    if created_snapshot:
        calc_snapshot['price_excl_vat'] = _to_json_safe(li.price_excl_vat)
        calc_snapshot['price_incl_vat'] = _to_json_safe(li.price_incl_vat)

    calc_snapshot_conv = dict(calc_snapshot)
    calc_snapshot_conv['price_excl_vat'] = _maybe_decimal(calc_snapshot.get('price_excl_vat'))
    calc_snapshot_conv['price_incl_vat'] = _maybe_decimal(calc_snapshot.get('price_incl_vat'))
    calc_snapshot_conv['priced_volume_litres'] = _maybe_decimal(calc_snapshot.get('priced_volume_litres'))
    calc_snapshot_conv['spread_rate_per_litre'] = _maybe_decimal(calc_snapshot.get('spread_rate_per_litre'))
    calc_snapshot_conv['package_size'] = _maybe_decimal(calc_snapshot.get('package_size'))

    # run dispatcher
    try:
        res = calculate_product_pricing(calc_snapshot_conv, area_sqm=li.area_sqm, coats=li.coats)
    except Exception as e:
        res = {'error': str(e)}

    # derive package price and packs_needed using same logic as calculate_product_pricing
    package_size = calc_snapshot_conv.get('package_size')
    snap_price_excl = calc_snapshot_conv.get('price_excl_vat')
    snap_priced_vol = calc_snapshot_conv.get('priced_volume_litres')
    price_per_package_excl = None
    if package_size is not None and snap_price_excl is not None and snap_priced_vol is not None and snap_priced_vol > 0:
        price_per_package_excl = snap_price_excl * (package_size / snap_priced_vol)
    else:
        # fallback to price per litre from calc
        price_per_litre_excl = res.get('price_per_litre_excl_vat') if isinstance(res.get('price_per_litre_excl_vat'), Decimal) else _maybe_decimal(res.get('price_per_litre_excl_vat'))
        if package_size is not None and price_per_litre_excl is not None:
            price_per_package_excl = price_per_litre_excl * package_size

    req = res.get('required_litres')
    packs_needed = None
    if package_size is not None and req is not None:
        try:
            packs_needed = (req / package_size).to_integral_value(rounding=ROUND_CEILING)
        except Exception:
            packs_needed = None

    out = {
        'line_pk': li.pk,
        'quotation_ref': getattr(li.quotation, 'reference', None),
        'product': paint.name if paint else None,
        'area_sqm': str(li.area_sqm),
        'coats': li.coats,
        'spread_rate': str(calc_snapshot_conv.get('spread_rate_per_litre')),
        'package_size': str(calc_snapshot_conv.get('package_size')),
        'package_unit': calc_snapshot.get('package_unit'),
        'package_price_computed': str(price_per_package_excl) if price_per_package_excl is not None else None,
        'required_litres': str(req) if req is not None else None,
        'packages_required': str(packs_needed) if packs_needed is not None else None,
        'old_total_excl_vat': str(li.total_excl_vat),
        'new_total_excl_vat': str(res.get('total_excl_vat')) if res.get('total_excl_vat') is not None else None,
        'product_snapshot': ps,
        'metadata': meta,
        'calc_snapshot_conv': {k: str(v) for k,v in calc_snapshot_conv.items()},
        'calculate_result': {k: (str(v) if not isinstance(v, dict) else v) for k,v in res.items()},
    }
    print(json.dumps(out, indent=2, default=str))
