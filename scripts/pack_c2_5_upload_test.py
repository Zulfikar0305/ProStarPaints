#!/usr/bin/env python3
import os
import sys

# Ensure Django settings are configured
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django

# Ensure project root is on sys.path so `config` imports resolve
proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from quotation.models import Quotation, QuotationSection, QuotationSectionImage

User = get_user_model()

# Prefer audituser if present
user = User.objects.filter(username='audituser').first()
if not user:
    user = User.objects.filter(is_superuser=True).first()
if not user:
    # create fallback user
    user = User.objects.create_user('temp_c2_5_user', 'temp@example.com', 'testpass')

client = Client()
client.force_login(user)

q = Quotation.objects.filter(pk=28).first()
if not q:
    print('No quotation with pk=28 found')
    sys.exit(1)

section = QuotationSection.objects.filter(quotation=q, pk=88).first()
if not section:
    print('No section with pk=88 found')
    sys.exit(1)

url = reverse('quotation:interior_walls_save', kwargs={'pk': q.pk, 'section_pk': section.pk})

post_data = {
    'wall_type': 'brick',
    'area_sqm': '10',
    'moisture_level': '5',
    'notes': 'PACK C2.5 upload test'
}

# Prepare files
base = os.getcwd()
paths = [os.path.join(base, 'tmp_uploads', 'a1.png'),
         os.path.join(base, 'tmp_uploads', 'a2.png'),
         os.path.join(base, 'tmp_uploads', 'a3.png')]
files = []
for p in paths:
    if not os.path.exists(p):
        print(f'Missing fixture: {p}')
        sys.exit(1)
    with open(p, 'rb') as fh:
        data = fh.read()
    files.append(('section_images', SimpleUploadedFile(os.path.basename(p), data, content_type='image/png')))

print('Posting to', url)
# Use explicit HTTP_HOST to avoid DisallowedHost in test client
resp = client.post(url, post_data, files=files, follow=True, HTTP_HOST='127.0.0.1')
print('Client POST response status:', resp.status_code)

# After POST, list DB state
saved_images = list(QuotationSectionImage.objects.filter(section=section).order_by('sort_order'))
print('DB saved images count after POST:', len(saved_images))
for img in saved_images:
    print('-', img.image.name)

print('Done')
