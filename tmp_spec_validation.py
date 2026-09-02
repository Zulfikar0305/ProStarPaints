import copy, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from quotation.models import Quotation
from specifications.models import ManualSpecificationDraft, SpecificationTemplate
from specifications.services.preview_service import PreviewService
from specifications.services.export_service import ExportService
from quotation.pdf_service import build_pdf_context, render_quotation_pdf
from specifications.services.template_service import TemplateService

user = get_user_model().objects.get(username='pdftester')
q = Quotation.objects.get(pk=7)
draft = ManualSpecificationDraft.objects.filter(quotation=q, created_by=user).order_by('-updated_at').first()
print('DRAFT_ID', draft.pk if draft else None)
print('DRAFT_OVERRIDE_TITLE', ((draft.data or {}).get('draft_overrides') or {}).get('sections', {}).get('interior_walls', {}).get('title_overrides', {}).get('34965837cd26736e') if draft else None)
preview = PreviewService().preview_context_for_draft(draft)
print('PREVIEW_FIRST_SECTION_TITLE', (preview.get('sections') or [{}])[0].get('section_name'))
print('PREVIEW_FIRST_BLOCK_TITLE', ((preview.get('sections') or [{}])[0].get('blocks') or [{}])[0].get('title'))
html = ExportService().render_html_for_draft(draft, 'manual_specification') if draft else ''
print('MANUAL_HTML_HAS_EDITED_TITLE', 'Interior Walls - Draft Edited' in html)

tmpl = SpecificationTemplate.objects.filter(key='automatic_specification').order_by('-created_at').first()
if tmpl:
    old = copy.deepcopy(tmpl.config or {})
    patched = copy.deepcopy(old)
    report = dict((patched.get('report_controls') or {}))
    report['show_pricing'] = False
    patched['report_controls'] = TemplateService.normalize_report_controls(report)
    tmpl.config = patched
    tmpl.save(update_fields=['config'])
    ctx = build_pdf_context(q, request=None)
    print('AUTO_SHOW_PRICING_AFTER_TOGGLE', ctx['report_controls'].get('show_pricing'))
    tmpl.config = old
    tmpl.save(update_fields=['config'])
else:
    print('AUTO_SHOW_PRICING_AFTER_TOGGLE', 'NO_TEMPLATE')

detailed_pdf = render_quotation_pdf(q, 'detailed_spec', user, request=None)
print('DETAIL_PDF_STATUS', detailed_pdf.status)
print('DETAIL_PDF_FILE', detailed_pdf.file.name if detailed_pdf.file else None)
print('DETAIL_PDF_ERROR', detailed_pdf.error_message or 'NONE')
