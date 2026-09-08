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

out_dir = Path('tmp_pdf_pages/consistency_check')
out_dir.mkdir(parents=True, exist_ok=True)

for pk, key in [(50, 'professional'), (48, 'detailed_spec'), (51, 'compact')]:
    q = Quotation.objects.get(pk=pk)
    export = render_quotation_pdf(q, key, user, request=None)
    path = Path(export.file.path)
    doc = fitz.open(path)
    if doc.page_count == 0:
        continue
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image_path = out_dir / f'{key}_page1.png'
    pix.save(str(image_path))
    print(f'{key}: {path} | pages={doc.page_count} | saved={image_path}')
