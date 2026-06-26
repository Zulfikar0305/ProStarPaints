import os, sys, django
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from quotation.models import QuotationPdfExport

exports = QuotationPdfExport.objects.order_by('-created_at')[:10]
for e in exports:
    print('id=', e.pk, 'quotation=', e.quotation.reference, 'template=', e.template_key, 'status=', e.status, 'file=', e.file.name if e.file else None)
    if e.error_message:
        print('  error:', e.error_message[:500])
