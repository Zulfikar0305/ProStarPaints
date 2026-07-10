#!/usr/bin/env python3
import os, sys
from decimal import Decimal, ROUND_CEILING

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

# Allow Django test client host when running standalone script
from django.conf import settings as _dj_settings
try:
    _dj_settings.ALLOWED_HOSTS = _dj_settings.ALLOWED_HOSTS + ['testserver']
except Exception:
    _dj_settings.ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from quotation.models import Quotation, QuotationSection, QuotationLineItem
from paints.models import Paint

User = get_user_model()

username = 'verify_user'
password = 'pass1234'
user, created = User.objects.get_or_create(username=username, defaults={'email': 'verify@example.com', 'first_name': 'Verify', 'last_name': 'User'})
if created or not user.has_usable_password():
    user.set_password(password)
    user.save()

# Create a new quotation
q = Quotation.objects.create(created_by=user, customer_name='Verify Test Customer')
section = QuotationSection.objects.create(quotation=q, subsection_key='interior_walls', display_name='Interior Walls', sort_order=1, selection_order=1)

# Choose PureMatt product (or first available)
paint = Paint.objects.filter(name__icontains='PureMatt').first() or Paint.objects.first()
if paint is None:
    print('No Paint products available in DB; aborting')
    sys.exit(2)

# Build POST data for interior walls save
url = reverse('quotation:interior_walls_save', kwargs={'pk': q.pk, 'section_pk': section.pk})

data = {
    'wall_type': 'brick',
    'surface_conditions': ['new'],
    'finishes': ['smooth_matte'],
    'area_sqm': '20',
    'moisture_level': '0',
    'notes': '',
    # single paint row
    'paint_row_finish': ['smooth_matte'],
    'paint_row_paint_pk': [str(paint.pk)],
    'paint_row_area_sqm': ['20.00'],
    'paint_row_coats': ['1'],
    'paint_row_base': ['WHITE'],
    'paint_row_line_pk': [''],
}

c = Client()
logged_in = c.login(username=username, password=password)
print('logged_in=', logged_in)
resp = c.post(url, data, follow=True)
print('POST status_code:', resp.status_code)

# Query created paint lines for this quotation
lines = QuotationLineItem.objects.filter(quotation=q, item_type=QuotationLineItem.ItemType.PAINT)
print('Created paint lines count:', lines.count())

for li in lines:
    print('--- Line pk:', li.pk)
    print(' paint pk:', li.paint.pk if li.paint else None)
    print(' area_sqm:', li.area_sqm)
    print(' coats:', li.coats)
    print(' spread_rate (snapshot/metadata):', (li.metadata or {}).get('spread_rate_per_litre'))
    print(' priced_vol_litres (snapshot):', (li.metadata or {}).get('priced_volume_litres'))
    print(' package_size (snapshot/metadata):', (li.metadata or {}).get('package_size'))
    print(' price_excl_vat on line:', li.price_excl_vat)
    print(' product.price_excl_vat:', paint.price_excl_vat)
    print(' stored total_excl_vat:', li.total_excl_vat)

    # Compute expected according to new engine rules
    area = li.area_sqm or Decimal('0')
    coats = li.coats or 1
    spread = _ = None
    try:
        spread = Decimal((li.metadata or {}).get('spread_rate_per_litre') or paint.spread_rate_per_litre)
    except Exception:
        spread = None
    if spread is None or spread == 0:
        print(' no spread rate to compute required litres; skipping expected check')
        continue
    required_litres = (Decimal(area) * Decimal(coats)) / Decimal(spread)
    # package size resolved: prefer metadata/package_size then priced_volume
    pkg_sz = (li.metadata or {}).get('package_size')
    try:
        pkg_sz_d = Decimal(str(pkg_sz)) if pkg_sz is not None else None
    except Exception:
        pkg_sz_d = None
    if pkg_sz_d is None:
        pkg_sz_d = paint.priced_volume_litres
    if pkg_sz_d is None or pkg_sz_d == 0:
        print(' no package size available; skipping expected check')
        continue
    packs_needed = (required_litres / pkg_sz_d).to_integral_value(rounding=ROUND_CEILING)
    expected_total = packs_needed * paint.price_excl_vat
    print(' required_litres:', required_litres)
    print(' pkg_sz:', pkg_sz_d, ' packs_needed:', packs_needed)
    print(' expected_total_excl_vat:', expected_total)
    print(' stored == expected?', str(li.total_excl_vat) == str(expected_total))

# Also verify quotation totals
q.refresh_from_db()
print('quotation subtotal_excl_vat:', q.subtotal_excl_vat, 'total_incl_vat:', q.total_incl_vat)

print('Done.')
