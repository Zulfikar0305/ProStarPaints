import os
import sys
import django
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.template.loader import render_to_string
from quotation.pdf_templates import PDF_TEMPLATES, get_template_config
from quotation.pdf_service import build_pdf_context, render_quotation_pdf, get_pdf_template
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from quotation.models import Quotation, QuotationSection, QuotationSectionImage, QuotationLineItem

User = get_user_model()
user, created = User.objects.get_or_create(username='pdftester', defaults={'email':'pdftester@example.com'})
if created:
    user.set_password('pass')
    user.save()

# Create or get a short-lived quotation with a section and tiny PNG image
q, _ = Quotation.objects.get_or_create(created_by=user, customer_name='PDF Audit Customer')
# Ensure it has at least one section
sec, _ = QuotationSection.objects.get_or_create(
    quotation=q,
    subsection_key='audit_section',
    defaults={'display_name':'Audit Section', 'sort_order':1, 'selection_order':1}
)
# ensure a NOTE line
QuotationLineItem.objects.get_or_create(
    quotation=q,
    section=sec,
    item_type=QuotationLineItem.ItemType.NOTE,
    description='Audit note',
)
# add a 1x1 png image if none
if not sec.images.exists():
    PNG_1X1_B64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVQYGWNgYAAAAAMAASsJTYQAAAAASUVORK5CYII='
    )
    png = base64 = None
    try:
        import base64 as _b64
        png = _b64.b64decode(PNG_1X1_B64)
    except Exception:
        png = b"\x89PNG\r\n\x1a\n"
    qsi = QuotationSectionImage(section=sec, uploaded_by=user)
    qsi.image.save('audit_test_section.png', ContentFile(png))
    qsi.save()

print('--- PDF Template Audit ---')
for key in list(PDF_TEMPLATES.keys()):
    print('\n--- Template:', key, '---')
    try:
        template_config = get_pdf_template(key)
    except Exception as e:
        print('get_pdf_template failed:', e)
        continue
    # Build context
    try:
        ctx = build_pdf_context(q)
        print('build_pdf_context: OK')
        # Check sections keys
        sections = ctx.get('sections', None)
        print('sections present:', sections is not None, 'count=', len(sections) if sections else 0)
        if sections:
            s0 = sections[0]
            print('first section has keys:', list(s0.keys()))
            print('line_items present:', 'line_items' in s0)
            print('images present:', 'images' in s0)
    except Exception as e:
        print('build_pdf_context raised:')
        traceback.print_exc()
        continue

    # Render template to string
    try:
        html = render_to_string(template_config['template_path'], ctx)
        print('render_to_string: OK, html length=', len(html))
    except Exception as e:
        print('render_to_string raised:')
        traceback.print_exc()
        continue

    # 1) Try render via render_quotation_pdf (captures exceptions inside)
    try:
        export = render_quotation_pdf(quotation=q, template_key=key, generated_by=user, request=None)
        print('render_quotation_pdf: status=', export.status, 'error_message=', (export.error_message or '')[:300])
    except Exception:
        print('render_quotation_pdf raised unexpectedly:')
        traceback.print_exc()

    # 2) Try importing and using weasyprint directly to see exact import/write errors
    try:
        print('Attempting direct weasyprint import/write for full traceback...')
        import weasyprint
        try:
            pdf_bytes = weasyprint.HTML(string=html, base_url=None).write_pdf()
            print('weasyprint write_pdf: OK, bytes=', len(pdf_bytes))
        except Exception:
            print('weasyprint.write_pdf raised:')
            traceback.print_exc()
    except Exception:
        print('weasyprint import failed:')
        traceback.print_exc()

print('\nAudit complete')
