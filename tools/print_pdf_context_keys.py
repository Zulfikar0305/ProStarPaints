import os, sys, django
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from quotation.pdf_service import build_pdf_context
from quotation.models import Quotation
q = Quotation.objects.order_by('-pk').first()
ctx = build_pdf_context(q)
print('context keys:', sorted(list(ctx.keys())))
secs = ctx.get('sections', [])
if secs:
    print('first section keys:', sorted(list(secs[0].keys())))
    print('images in first section:', type(secs[0].get('images')), 'count=', len(secs[0].get('images')))
    if secs[0].get('images'):
        print('first image startswith data:image/', secs[0]['images'][0].startswith('data:image/'))
else:
    print('no sections')
