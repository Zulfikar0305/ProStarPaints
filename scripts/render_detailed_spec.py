#!/usr/bin/env python3
"""
Render detailed_spec PDF for the first available Quotation and export per-page PNGs.
This script is read-only with respect to quotations and does not create QuotationPdfExport rows.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Ensure project root is on sys.path so `config` imports work when run from scripts/
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import django
django.setup()

from quotation.models import Quotation
from quotation.pdf_service import build_pdf_context
from quotation.pdf_templates import get_template_config
from django.template.loader import render_to_string

import weasyprint
import fitz  # PyMuPDF

OUT_DIR = Path('renders')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Choose quotation: allow passing a pk as first arg
pk = None
if len(sys.argv) > 1:
    try:
        pk = int(sys.argv[1])
    except Exception:
        pk = None

if pk:
    quotation = Quotation.objects.filter(pk=pk).first()
else:
    quotation = Quotation.objects.first()

if not quotation:
    print('ERROR: No quotation found in DB to render.')
    sys.exit(2)

print('Rendering quotation pk=', quotation.pk, 'reference=', quotation.reference)

# Build context (read-only)
context = build_pdf_context(quotation)
logo_present = bool(context.get('logo_data_uri'))
print('Logo embedded:', logo_present)

# Get template path
tpl_cfg = get_template_config('detailed_spec')
tpl_path = tpl_cfg['template_path']
print('Using template:', tpl_path)

# Render HTML
html_string = render_to_string(tpl_path, context)

# Output PDF
pdf_path = OUT_DIR / f'detailed_spec_q{quotation.pk}.pdf'
print('Writing PDF to', pdf_path)
try:
    weasyprint.HTML(string=html_string, base_url=None).write_pdf(str(pdf_path))
except Exception as e:
    print('PDF rendering failed:', str(e))
    sys.exit(3)

# Open PDF and render pages to PNG
doc = fitz.open(str(pdf_path))
page_count = doc.page_count
print('PDF page count:', page_count)

png_paths = []
for i in range(page_count):
    page = doc.load_page(i)
    pix = page.get_pixmap(dpi=150)
    p = OUT_DIR / f'detailed_spec_q{quotation.pk}_page_{i+1}.png'
    pix.save(str(p))
    png_paths.append(str(p))

# Extract simple text checks from first page
first_page_text = doc.load_page(0).get_text().strip()
first_page_text_snippet = first_page_text[:200].replace('\n',' ') if first_page_text else ''

print('First page text snippet:', first_page_text_snippet)
print('Generated PNGs:')
for p in png_paths:
    print(' -', p)

# Output simple section ordering and totals for verification
sections = list(quotation.sections.order_by('sort_order'))
section_ids = [s.pk for s in sections]
print('Section IDs (ordered):', section_ids)
print('Quotation subtotal_excl_vat:', getattr(quotation, 'subtotal_excl_vat', None))
print('Quotation total_incl_vat:', getattr(quotation, 'total_incl_vat', None))

print('Render completed successfully.')

sys.exit(0)
