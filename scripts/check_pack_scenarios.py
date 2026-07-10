#!/usr/bin/env python3
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()

from decimal import Decimal
from quotation.pricing import calculate_product_pricing

scenarios = [
    (Decimal('20'), Decimal('2.5'), 1),
    (Decimal('20'), Decimal('19.9'), 1),
    (Decimal('20'), Decimal('20.1'), 2),
    (Decimal('10'), Decimal('25'), 3),
    (Decimal('5'),  Decimal('12'), 3),
]

for pkg_size, req_litres, expected in scenarios:
    snap = {
        'pricing_method': 'AREA_COATING',
        'category': 'INTERIOR',
        'price_excl_vat': Decimal('100.00'),
        'price_incl_vat': Decimal('115.00'),
        'priced_volume_litres': Decimal('1.00'),
        'package_size': pkg_size,
        'package_unit': 'L',
    }
    # supply a spread_rate that makes required litres equal to area (coats=1)
    snap['spread_rate_per_litre'] = Decimal('1.00')
    res = calculate_product_pricing(snap, area_sqm=req_litres, coats=1)
    print(f'pkg={pkg_size}L req={req_litres} => quantity={res.get("quantity")}, unit={res.get("unit")}, total_excl={res.get("total_excl_vat")}, expected_qty={expected}')
