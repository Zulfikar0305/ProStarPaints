import os
import base64
import django
import sys

# Ensure project root (parent of tools/) is on sys.path so `config` can be imported
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from quotation.models import Quotation, QuotationSection, QuotationSectionImage, QuotationLineItem
from quotation.pdf_service import render_quotation_pdf

User = get_user_model()
user, created = User.objects.get_or_create(username='pdftester', defaults={'email':'pdftester@example.com'})
if created:
    user.set_password('pass')
    user.save()

# Create quotation and a configured section
q = Quotation.objects.create(created_by=user, customer_name='PDF Test Customer')
sec = QuotationSection.objects.create(
    quotation=q,
    subsection_key='interior_walls',
    display_name='Interior Walls',
    sort_order=1,
    selection_order=1,
    is_placeholder=False,
)

# Add a NOTE line so the section is considered configured
QuotationLineItem.objects.create(
    quotation=q,
    section=sec,
    item_type=QuotationLineItem.ItemType.NOTE,
    description='Test section note',
    metadata={},
)

# Minimal 1x1 PNG (base64) to attach
PNG_1X1_B64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVQYGWNgYAAAAAMAASsJTYQAAAAASUVORK5CYII='
)
png = base64.b64decode(PNG_1X1_B64)

# Save image via the QuotationSectionImage.image.save helper
qsi = QuotationSectionImage(section=sec, uploaded_by=user)
qsi.image.save('pdf_test_section.png', ContentFile(png))
qsi.save()

# Render PDF
export = render_quotation_pdf(quotation=q, template_key='detailed_spec', generated_by=user, request=None)
print('export_id=', export.pk)
print('status=', export.status)
print('file=', export.file.name if export.file else None)

# Print some context sanity
ctx = None
try:
    from quotation.pdf_service import build_pdf_context
    ctx = build_pdf_context(q)
    sec_ctx = next((s for s in ctx.get('sections', []) if s.get('section').pk == sec.pk), None)
    if sec_ctx:
        print('section images count in context=', len(sec_ctx.get('images', [])))
        if sec_ctx.get('images'):
            print('first image startswith data:image=', sec_ctx.get('images')[0].startswith('data:image/'))
except Exception as e:
    print('build_pdf_context failed:', e)

print('Done')
