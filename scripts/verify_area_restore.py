#!/usr/bin/env python3
import os, sys, re
from decimal import Decimal

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
from quotation.models import Quotation, QuotationSection
from paints.models import Paint

User = get_user_model()

username = 'verify_area_user'
password = 'pass1234'
user, created = User.objects.get_or_create(username=username, defaults={'email': 'verify_area@example.com', 'first_name': 'Verify', 'last_name': 'Area'})
if created or not user.has_usable_password():
    user.set_password(password)
    user.save()

# Create a new quotation and section
q = Quotation.objects.create(created_by=user, customer_name='Verify Area Customer')
section = QuotationSection.objects.create(quotation=q, subsection_key='interior_walls', display_name='Interior Walls', sort_order=1, selection_order=1)

# Choose a paint product
paint = Paint.objects.filter(name__icontains='PureMatt').first() or Paint.objects.first()
if paint is None:
    print('No Paint products available in DB; aborting')
    sys.exit(2)

posted_area = '33.25'

# Build POST data for interior walls save
url = reverse('quotation:interior_walls_save', kwargs={'pk': q.pk, 'section_pk': section.pk})

data = {
    'wall_type': 'brick',
    'surface_conditions': ['new'],
    'finishes': ['smooth_matte'],
    'area_sqm': posted_area,
    'moisture_level': '0',
    'notes': '',
    # single paint row
    'paint_row_finish': ['smooth_matte'],
    'paint_row_paint_pk': [str(paint.pk)],
    'paint_row_area_sqm': [posted_area],
    'paint_row_coats': ['1'],
    'paint_row_base': ['WHITE'],
    'paint_row_line_pk': [''],
}

c = Client()
logged_in = c.login(username=username, password=password)
print('logged_in=', logged_in)
resp = c.post(url, data, follow=True)
print('POST status_code:', resp.status_code)

# Now GET the builder page and inspect the rendered Area input value
builder_url = reverse('quotation:quotation_builder', kwargs={'pk': q.pk}) + '?leaflet=interior_walls'
get_resp = c.get(builder_url)
print('GET builder status_code:', get_resp.status_code)
content = get_resp.content.decode('utf-8', errors='replace')

# Find the top-level area input (first occurrence)
m = re.search(r'name="area_sqm"[^>]*value="([^"]*)"', content)
if m:
    found = m.group(1)
    print('Found area input value:', found)
    print('Matches posted?', found == posted_area)
else:
    print('No area input value found in builder HTML')

# Also check collapsed summary area display
m2 = re.search(r'Area:</div>\s*<div class="col-auto">\s*([^<]+)\s*m&sup2;', content)
if m2:
    summary_val = m2.group(1).strip()
    print('Found summary area display:', summary_val)
    print('Matches posted?', summary_val == posted_area)
else:
    print('No summary area display found')

print('Done.')
