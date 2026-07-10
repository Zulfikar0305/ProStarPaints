#!/usr/bin/env python3
import os, sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from quotation.models import QuotationLineItem, Quotation
from quotation.pricing import apply_paint_pricing_to_line_item

ItemType = QuotationLineItem.ItemType

lines = QuotationLineItem.objects.filter(
    item_type__in=[ItemType.PAINT, ItemType.PRIMER, ItemType.WATERPROOFING],
    quotation__status=Quotation.Status.DRAFT,
).select_related('quotation', 'paint')

print('Target lines (DRAFT quotations):', lines.count())
changed = []
errors = []

for li in lines:
    before = li.total_excl_vat or Decimal('0.00')
    try:
        apply_paint_pricing_to_line_item(li)
        after = li.total_excl_vat or Decimal('0.00')
        if Decimal(str(before)) != Decimal(str(after)):
            changed.append({'line_pk': li.pk, 'quotation_ref': li.quotation.reference, 'before': str(before), 'after': str(after)})
    except Exception as e:
        errors.append({'line_pk': li.pk, 'quotation_ref': getattr(li.quotation, 'reference', None), 'error': str(e)})

print('Recompute complete. Lines changed:', len(changed))
if changed:
    for c in changed[:50]:
        print(c)
if errors:
    print('Errors:', len(errors))
    for e in errors[:20]:
        print(e)

# summary exit code
if errors:
    sys.exit(2)
else:
    sys.exit(0)
