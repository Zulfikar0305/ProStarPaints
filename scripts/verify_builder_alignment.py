#!/usr/bin/env python3
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from quotation.models import QuotationLineItem, QuotationSection, Quotation
from quotation.views import QuotationBuilderView
from quotation.services import get_quotation_summary

q = Quotation.objects.filter(line_items__item_type=QuotationLineItem.ItemType.PAINT).distinct().first()
if not q:
    print('NO_QUOTATION_FOUND')
    sys.exit(0)

print(f'Checking quotation {q.pk} {q.reference}')
summary = get_quotation_summary(q)
monetary = summary.get('monetary', {})
paint_total_summary = Decimal(monetary.get('paint_total_excl_vat') or '0')

# Sum totals from builder contexts
sum_from_rows = Decimal('0')
for sec in q.sections.all():
    # choose correct context
    if sec.subsection_key == 'interior_walls':
        ctx = QuotationBuilderView._iw_context(sec)
    else:
        ctx = QuotationBuilderView._generic_section_context(sec)
    for row in ctx.get('saved_paint_rows', []):
        te = row.get('total_excl_vat')
        if te is None:
            continue
        try:
            sum_from_rows += Decimal(str(te))
        except Exception:
            # maybe the stored value is string already
            sum_from_rows += Decimal(te)

print('summary_paint_total_excl_vat=', paint_total_summary)
print('sum_from_builder_rows=', sum_from_rows)
print('EQUALS?', paint_total_summary == sum_from_rows)
