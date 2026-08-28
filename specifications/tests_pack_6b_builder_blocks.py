from copy import deepcopy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from quotation.models import Quotation, QuotationSection, QuotationLineItem
from quotation.pdf_templates import PDF_TEMPLATES
from paints.models import Paint
from specifications.models import SpecificationTemplate
from specifications.services import ManualSpecificationBuilderService
from specifications.services.export_service import ExportService
from specifications.services.preview_service import PreviewService
from specifications.services.template_service import TemplateService


class Pack6BBuilderBlockOverrideTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='builder_user', email='builder@example.test', password='pass')
        self.quotation = Quotation.objects.create(
            created_by=self.user,
            customer_name='Acme',
            project_name='Warehouse',
            project_location='Johannesburg',
        )
        self.section = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='interior_walls',
            display_name='Interior Walls',
            selection_order=1,
        )
        self.paint = Paint.objects.create(
            name='Block Test Paint',
            is_active=True,
            description='A durable finish for tests.',
            spread_rate_per_litre=Decimal('8.00'),
            priced_volume_litres=Decimal('1.00'),
            price_excl_vat=Decimal('50.00'),
            price_incl_vat=Decimal('57.50'),
            base_type='WHITE',
            pricing_method=Paint.PricingMethod.AREA_COATING,
            package_size=Decimal('5.00'),
            package_unit='L',
        )
        self.paint_item = QuotationLineItem.objects.create(
            quotation=self.quotation,
            section=self.section,
            item_type=QuotationLineItem.ItemType.PAINT,
            description='Apply test system',
            paint=self.paint,
            coats=2,
            area_sqm=Decimal('12.00'),
            price_excl_vat=Decimal('50.00'),
            price_incl_vat=Decimal('57.50'),
            metadata={},
        )
        self.service = ManualSpecificationBuilderService()

    def test_builder_loads_canonical_blocks(self):
        spec = self.service.prepare_spec(self.quotation)
        self.assertIn('sections', spec)
        self.assertTrue(spec['sections'])
        section = spec['sections'][0]
        self.assertIn('blocks', section)
        self.assertTrue(section['blocks'])
        for block in section['blocks']:
            self.assertIn('block_type', block)
            self.assertIn('visible', block)
            self.assertIn('editable', block)
            self.assertIn('resolved_id', block)

    def test_visibility_order_and_editable_override_persist(self):
        base = self.service.prepare_spec(self.quotation)
        edited = deepcopy(base)
        section = edited['sections'][0]
        blocks = section['blocks']
        first = blocks[0]
        second = blocks[1] if len(blocks) > 1 else blocks[0]

        first['visible'] = False
        blocks.reverse()

        editable = next(block for block in blocks if block.get('editable'))
        editable['title'] = 'Surface Preparation Requirements'
        editable['content'] = 'Draft override content'

        overrides = self.service.extract_draft_overrides(base, edited)
        self.assertIn('sections', overrides)
        self.assertIn('order', overrides['sections'][section['section_key']])
        self.assertIn('visible', overrides['sections'][section['section_key']])
        self.assertIn('title_overrides', overrides['sections'][section['section_key']])

        applied = self.service.apply_draft_overrides(base, overrides)
        applied_section = applied['sections'][0]
        hidden_block = next(b for b in applied_section['blocks'] if b['resolved_id'] == first['resolved_id'])
        self.assertFalse(hidden_block['visible'])
        self.assertEqual(hidden_block['title'], 'Surface Preparation Requirements')
        self.assertEqual(hidden_block['content'], 'Draft override content')
        self.assertEqual([b['resolved_id'] for b in applied_section['blocks']], overrides['sections'][section['section_key']]['order'])

    def test_non_editable_source_data_remains_unchanged(self):
        base = self.service.prepare_spec(self.quotation)
        edited = deepcopy(base)
        section = edited['sections'][0]
        for block in section['blocks']:
            if block.get('editable') is False:
                block['content'] = 'DO NOT mutate source'
                block['title'] = 'Mutated title'
                break

        overrides = self.service.extract_draft_overrides(base, edited)
        self.assertIn('content_overrides', overrides['sections'][section['section_key']])
        self.assertNotEqual(base['sections'][0]['blocks'][0]['title'], 'Mutated title')
        self.assertNotEqual(base['sections'][0]['blocks'][0]['content'], 'DO NOT mutate source')

    def test_draft_save_and_reload_restores_overrides(self):
        base = self.service.prepare_spec(self.quotation)
        edited = deepcopy(base)
        edited['pricing_visible'] = False
        section = edited['sections'][0]
        block = next(block for block in section['blocks'] if block.get('editable'))
        block['content'] = 'Revised recommendation'
        block['title'] = 'Revised title'

        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Test Draft')
        draft = self.service.save_draft(draft, edited)

        self.assertIn('draft_overrides', draft.data)
        self.assertFalse(draft.data['draft_overrides'].get('pricing_visible', True))
        reloaded = self.service.apply_draft_overrides(draft.data['resolver'], draft.data['draft_overrides'])
        self.assertFalse(reloaded['pricing_visible'])
        reloaded_block = next(block for block in reloaded['sections'][0]['blocks'] if block.get('resolved_id') == block['resolved_id'])
        self.assertEqual(reloaded_block['title'], 'Revised title')

    def test_pricing_visibility_stays_as_draft_only(self):
        base = self.service.prepare_spec(self.quotation)
        self.assertTrue(base.get('pricing_visible', True))
        edited = deepcopy(base)
        edited['pricing_visible'] = False

        overrides = self.service.extract_draft_overrides(base, edited)
        self.assertFalse(overrides['pricing_visible'])

        applied = self.service.apply_draft_overrides(base, overrides)
        self.assertFalse(applied.get('pricing_visible', True))
        self.assertTrue(base.get('pricing_visible', True))

    def test_legacy_arrays_keep_working(self):
        spec = self.service.prepare_spec(self.quotation)
        first = spec['sections'][0]
        self.assertIn('clauses', first)
        self.assertIn('product_descriptions', first)
        self.assertIn('images', first)
        self.assertIn('knowledge_matches', first)

    def test_template_service_normalises_report_controls(self):
        template = SpecificationTemplate.objects.create(
            name='Report Controls',
            key='report_controls_test',
            config={
                'report_controls': {
                    'show_photos': False,
                    'show_pricing': False,
                    'show_tds': False,
                }
            },
            is_active=True,
            created_by=self.user,
        )

        data = TemplateService.as_dict(template)
        self.assertIn('report_controls', data)
        self.assertFalse(data['report_controls']['show_photos'])
        self.assertFalse(data['report_controls']['show_pricing'])
        self.assertFalse(data['report_controls']['show_tds'])
        self.assertTrue(data['report_controls']['show_coating_system'])
        self.assertTrue(data['report_controls']['show_notes'])

    def test_automatic_spec_template_is_the_default_report_source(self):
        auto = SpecificationTemplate.objects.create(
            name='Automatic Specification',
            key='automatic_specification',
            config={
                'report_controls': {
                    'show_photos': False,
                    'show_pricing': False,
                    'show_notes': False,
                }
            },
            is_active=True,
            created_by=self.user,
        )
        SpecificationTemplate.objects.create(
            name='Legacy Template',
            key='legacy_template',
            config={'report_controls': {'show_photos': True, 'show_pricing': True, 'show_notes': True}},
            is_active=True,
            created_by=self.user,
        )

        default_template = TemplateService.get_active_template()
        self.assertIsNotNone(default_template)
        self.assertEqual(default_template.pk, auto.pk)
        self.assertEqual(default_template.key, 'automatic_specification')
        self.assertFalse(default_template.config['report_controls']['show_photos'])
        self.assertFalse(default_template.config['report_controls']['show_pricing'])
        self.assertFalse(default_template.config['report_controls']['show_notes'])

    def test_manual_specification_is_registered_as_distinct_option(self):
        self.assertIn('manual_specification', PDF_TEMPLATES)
        self.assertIn('detailed_spec', PDF_TEMPLATES)
        self.assertNotEqual(PDF_TEMPLATES['manual_specification']['template_path'], PDF_TEMPLATES['detailed_spec']['template_path'])
        self.assertEqual(PDF_TEMPLATES['manual_specification']['name'], 'Manual Specification')

    def test_report_controls_are_inherited_and_overridden(self):
        base = self.service.prepare_spec(self.quotation)
        base['report_controls'] = {
            'show_photos': True,
            'show_moisture_reading': True,
            'show_preparation_requirements': True,
            'show_coating_system': True,
            'show_tds': True,
            'show_product_table': True,
            'show_pricing': True,
            'show_warranty': True,
            'show_recommendations': True,
            'show_notes': True,
        }

        edited = self.service.prepare_spec(self.quotation)
        edited['report_controls'] = dict(base['report_controls'])
        edited['report_controls']['show_pricing'] = False
        edited['report_controls']['show_notes'] = False

        overrides = self.service.extract_draft_overrides(base, edited)
        self.assertIn('report_controls', overrides)
        self.assertFalse(overrides['report_controls']['show_pricing'])
        self.assertFalse(overrides['report_controls']['show_notes'])

        applied = self.service.apply_draft_overrides(base, overrides)
        self.assertFalse(applied['report_controls']['show_pricing'])
        self.assertFalse(applied['report_controls']['show_notes'])
        self.assertTrue(base['report_controls']['show_pricing'])

    def test_preview_and_pdf_use_same_manual_draft_state(self):
        from django.template.loader import render_to_string

        base = self.service.prepare_spec(self.quotation)
        edited = deepcopy(base)
        edited['pricing_visible'] = False
        edited['report_controls'] = {
            'show_photos': False,
            'show_pricing': False,
            'show_notes': False,
            'show_recommendations': True,
            'show_warranty': True,
            'show_preparation_requirements': True,
            'show_coating_system': True,
            'show_tds': True,
            'show_product_table': True,
            'show_moisture_reading': True,
        }
        section = edited['sections'][0]
        block = section['blocks'][0]
        block['title'] = 'Manual heading override'
        block['content'] = 'Manual content override'
        block['visible'] = False
        section['section_name'] = 'Changed section title'

        overrides = self.service.extract_draft_overrides(base, edited)
        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Parity Draft')
        draft = self.service.save_draft(draft, {
            'resolver': base,
            'draft_overrides': overrides,
            'report_controls': edited['report_controls'],
            'sections_metadata': [],
        })

        preview_ctx = PreviewService().preview_context_for_draft(draft)
        preview_html = render_to_string('quotation/pdf/detailed_spec.html', preview_ctx)
        pdf_html = ExportService().render_html_for_draft(draft, 'detailed_spec')

        self.assertEqual(preview_html, pdf_html)
        self.assertFalse(preview_ctx['report_controls']['show_pricing'])
        self.assertFalse(preview_ctx['report_controls']['show_photos'])
        self.assertFalse(preview_ctx['report_options']['pricing_enabled'])
        self.assertEqual(preview_ctx['sections'][0]['section_name'], 'Changed section title')

    def test_manual_builder_page_exposes_preview_and_export_workflow_actions(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('specifications:builder_quotation', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Preview Draft')
        self.assertContains(response, 'Open PDF Options')
        self.assertContains(response, 'Generate Manual Specification PDF')
        self.assertContains(response, 'Manual Specification Builder')

    def test_manual_preview_uses_visibility_and_content_overrides_for_product_image_blocks(self):
        base = self.service.prepare_spec(self.quotation)
        edited = deepcopy(base)
        section = edited['sections'][0]
        product_block = next(block for block in section['blocks'] if block.get('block_type') == 'product_description')
        image_block = next(block for block in section['blocks'] if block.get('block_type') == 'image')
        product_block['visible'] = False
        product_block['title'] = 'Custom Product Name'
        product_block['content'] = 'Custom product description'
        image_block['visible'] = False

        overrides = self.service.extract_draft_overrides(base, edited)
        applied = self.service.apply_draft_overrides(base, overrides)
        applied_section = applied['sections'][0]

        self.assertFalse(any(
            item.get('product_name') == 'Custom Product Name'
            for item in (applied_section.get('product_descriptions') or [])
        ))
        self.assertEqual(applied_section.get('images', []), [])

    def test_manual_builder_pdf_generation_route_uses_saved_draft(self):
        self.client.force_login(self.user)
        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Route Draft')
        draft = self.service.save_draft(draft, self.service.prepare_spec(self.quotation))

        response = self.client.get(reverse('specifications:builder_quotation_export', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 302)
        export_id = response.url.rsplit('/', 2)[-2]
        self.assertTrue(export_id.isdigit())

    def test_manual_builder_javascript_collects_both_input_and_textarea_content(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('specifications:builder_quotation', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('input[data-kind="content"], textarea[data-kind="content"]', html)
