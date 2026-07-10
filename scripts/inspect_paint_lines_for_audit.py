#!/usr/bin/env python3
import os
import sys
import json

# Ensure project root is importable and Django settings module
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from quotation.models import Quotation, QuotationLineItem

# Find a quotation with at least one PAINT line
q = Quotation.objects.filter(line_items__item_type=QuotationLineItem.ItemType.PAINT).distinct().first()
if not q:
    print('NO_QUOTATION_FOUND')
    sys.exit(0)

print(f"QUOTATION_PKS\t{q.pk}\t{q.reference}")

paint_lines = q.line_items.filter(item_type=QuotationLineItem.ItemType.PAINT).select_related('paint')
out = []
for li in paint_lines:
    paint_name = li.paint.name if li.paint else None
    rec = (li.metadata or {}).get('recommended_containers')
    pricing_method = (li.metadata or {}).get('pricing_method') or (li.paint.pricing_method if li.paint else None)
    out.append({
        'line_pk': li.pk,
        'product': paint_name,
        'price_excl_vat': str(li.price_excl_vat),
        'total_excl_vat': str(li.total_excl_vat),
        'quantity': str(li.quantity) if li.quantity is not None else None,
        'recommended_containers': rec,
        'pricing_method': pricing_method,
        'metadata': li.metadata or {},
    })

print(json.dumps(out, indent=2))
