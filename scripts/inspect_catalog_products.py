#!/usr/bin/env python3
import os, sys
from decimal import Decimal
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from paints.models import Paint

names = ['PureMatt', 'Covercoat']
for name in names:
    qs = Paint.objects.filter(name__icontains=name)
    print(f"\nProducts matching '{name}': {qs.count()}")
    for p in qs:
        print({
            'pk': p.pk,
            'name': p.name,
            'package_size': getattr(p, 'package_size', None),
            'package_unit': getattr(p, 'package_unit', None),
            'price_excl_vat': getattr(p, 'price_excl_vat', None),
            'price_incl_vat': getattr(p, 'price_incl_vat', None),
            'priced_volume_litres': getattr(p, 'priced_volume_litres', None),
            'spread_rate_per_litre': getattr(p, 'spread_rate_per_litre', None),
            'is_active': getattr(p, 'is_active', None),
        })
