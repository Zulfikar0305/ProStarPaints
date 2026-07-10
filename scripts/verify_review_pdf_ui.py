#!/usr/bin/env python3
import os, sys
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
from quotation.models import Quotation

User = get_user_model()
username = 'verify_ui_user'
password = 'pass1234'
user, created = User.objects.get_or_create(username=username, defaults={'email': 'verify_ui@example.com'})
if created or not user.has_usable_password():
    user.set_password(password)
    user.save()

c = Client()
logged_in = c.login(username=username, password=password)
print('logged_in=', logged_in)

q = Quotation.objects.create(created_by=user, customer_name='Verify UI Customer')
# Persist explicit totals (simulate pricing done)
q.subtotal_excl_vat = Decimal('123.45')
q.vat_amount = Decimal('18.52')
q.total_incl_vat = Decimal('141.97')
q.save()

# Fetch review page
review_url = reverse('quotation:quotation_review', kwargs={'pk': q.pk})
resp = c.get(review_url)
print('GET review status_code:', resp.status_code)
content = resp.content.decode('utf-8', errors='replace')
found_sub = 'R 123.45' in content
found_tot = 'R 141.97' in content
print('Found subtotal on review?', found_sub)
print('Found total on review?', found_tot)

# Fetch PDF template select page
tpl_url = reverse('quotation:pdf_select', kwargs={'pk': q.pk})
resp2 = c.get(tpl_url)
print('GET pdf_select status_code:', resp2.status_code)
content2 = resp2.content.decode('utf-8', errors='replace')
# Ensure pricing warning removed
warning_present = 'Pricing will display as TBC' in content2 or 'TBC' in content2
# Ensure template descriptions mention persisted pricing
mention = 'persisted quotation totals' in content2 or 'persisted quotation' in content2
print('Pricing warning present on pdf select?', warning_present)
print('Template descriptions mention persisted pricing?', mention)

print('Done.')
