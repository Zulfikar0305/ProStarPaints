import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

import fitz
from django.contrib.auth import get_user_model
from quotation.models import Quotation
from quotation.pdf_service import render_quotation_pdf

User = get_user_model()
user = User.objects.filter(username='admin').first() or User.objects.first()
q = Quotation.objects.get(pk=50)

export = render_quotation_pdf(q, 'professional', user, request=None)
path = Path(export.file.path)

print('EXPORT', export.pk, export.status, bool(export.file), path)

doc = fitz.open(path)
print('PAGE_COUNT', doc.page_count)

out_dir = Path('tmp_pdf_pages/q42_header_verify')
out_dir.mkdir(parents=True, exist_ok=True)

for idx in range(1, min(doc.page_count, 8) + 1):
    page = doc[idx - 1]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    out_path = out_dir / f'page_{idx}.png'
    pix.save(str(out_path))
    text = (page.get_text('text') or '').replace('\n', ' | ')[:180]
    print(f'PAGE_{idx}_TEXT', text)
    print('SAVED', out_path)
