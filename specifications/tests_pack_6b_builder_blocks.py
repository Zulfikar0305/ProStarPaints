from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from quotation.models import Quotation, QuotationSection, QuotationLineItem, QuotationSectionImage
from quotation.pdf_templates import PDF_TEMPLATES
from paints.models import Paint
from specifications.forms import KnowledgeEntryForm
from specifications.models import SpecificationTemplate, KnowledgeEntry, SurfaceDefault, ManualSpecificationDraft, ManualSpecificationItem
from specifications.services import ManualSpecificationBuilderService, seed_default_specification_knowledge
from specifications.services.export_service import ExportService
from specifications.services.knowledge_service import KnowledgeService
from specifications.services.resolver import SpecificationResolver
from specifications.services.preview_service import PreviewService
from specifications.services.template_service import TemplateService
from quotation.config import ALL_GENERIC_SECTION_CONFIGS
from quotation.services import ALL_SUBSECTIONS


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
        override_key = str(section.get('section_pk', section['section_key']))
        self.assertIn('order', overrides['sections'][override_key])
        self.assertIn('visible', overrides['sections'][override_key])
        self.assertIn('title_overrides', overrides['sections'][override_key])

        applied = self.service.apply_draft_overrides(base, overrides)
        applied_section = applied['sections'][0]
        hidden_block = next(b for b in applied_section['blocks'] if b['resolved_id'] == first['resolved_id'])
        self.assertFalse(hidden_block['visible'])
        self.assertEqual(hidden_block['title'], 'Surface Preparation Requirements')
        self.assertEqual(hidden_block['content'], 'Draft override content')
        self.assertEqual([b['resolved_id'] for b in applied_section['blocks']], overrides['sections'][override_key]['order'])

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
        override_key = str(section.get('section_pk', section['section_key']))
        self.assertIn('content_overrides', overrides['sections'][override_key])
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

    def test_manual_item_overrides_are_persisted_per_section(self):
        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Item Override Draft')
        section_key = self.quotation.sections.first().subsection_key
        manual_overrides = {
            section_key: {
                'preparation_requirements': 'Custom prep override for this item.',
                'application_requirements': 'Custom application override for this item.',
                'images': ['data:image/png;base64,AAA', 'data:image/png;base64,BBB'],
            }
        }

        saved = self.service.save_draft(draft, {
            'resolver': draft.data['resolver'],
            'manual_overrides': manual_overrides,
        })

        self.assertEqual(saved.data['manual_overrides'][section_key]['preparation_requirements'], 'Custom prep override for this item.')
        self.assertEqual(saved.data['manual_overrides'][section_key]['application_requirements'], 'Custom application override for this item.')
        self.assertEqual(saved.data['manual_overrides'][section_key]['images'][1], 'data:image/png;base64,BBB')

    def test_manual_specification_item_is_the_authoritative_persistence_layer(self):
        section = self.quotation.sections.first()
        saved = self.service.save_manual_item(
            self.quotation,
            section,
            preparation_requirements='Manual prep requirement for Q47.',
            application_requirements='Manual application requirement for Q47.',
            created_by=self.user,
        )

        self.assertEqual(saved.quotation, self.quotation)
        self.assertEqual(saved.section, section)
        self.assertEqual(saved.preparation_requirements, 'Manual prep requirement for Q47.')
        self.assertEqual(saved.application_requirements, 'Manual application requirement for Q47.')

        manual_overrides = self.service.manual_overrides_for_quotation(self.quotation)
        self.assertEqual(manual_overrides[str(section.pk)]['preparation_requirements'], 'Manual prep requirement for Q47.')
        self.assertEqual(manual_overrides[str(section.pk)]['application_requirements'], 'Manual application requirement for Q47.')

        reverted = self.service.revert_manual_item(self.quotation, section)
        self.assertTrue(ManualSpecificationItem.objects.filter(quotation=self.quotation, section=section).exists())
        self.assertEqual(reverted.preparation_requirements, reverted.original_preparation_requirements)
        self.assertEqual(reverted.application_requirements, reverted.original_application_requirements)

    def test_builder_uses_section_pk_for_manual_override_keys(self):
        first = self.quotation.sections.first()
        second = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='interior_walls',
            display_name='Interior Walls',
            selection_order=2,
        )

        self.assertEqual(self.service._section_key(first), str(first.pk))
        self.assertEqual(self.service._section_key(second), str(second.pk))
        self.assertNotEqual(self.service._section_key(first), self.service._section_key(second))

    def test_manual_resolver_match_uses_selection_order_not_shared_subsection_bucket(self):
        wall_one = self.quotation.sections.first()
        wall_two = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='interior_walls',
            display_name='Interior Walls 2',
            selection_order=2,
        )
        ceiling_one = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='ceilings',
            display_name='Ceilings',
            selection_order=1,
        )
        ceiling_two = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='ceilings',
            display_name='Ceilings 2',
            selection_order=2,
        )

        for section, metadata in {
            wall_one: {'wall_type_label': 'Brick'},
            wall_two: {'wall_type_label': 'Drywall / Plasterboard'},
            ceiling_one: {'type_labels': ['Concrete socket'], 'types': ['concrete_socket']},
            ceiling_two: {'type_labels': ['Gypsum boards'], 'types': ['gypsum_boards']},
        }.items():
            QuotationLineItem.objects.create(
                quotation=self.quotation,
                section=section,
                item_type=QuotationLineItem.ItemType.NOTE,
                description='section note',
                metadata=metadata,
            )

        fake_sections = [
            {
                'section_name': 'Interior Walls 2',
                'section_key': 'interior_walls',
                'subsection_key': 'interior_walls',
                'selection_order': 2,
                'images': [],
            },
            {
                'section_name': 'Interior Walls',
                'section_key': 'interior_walls',
                'subsection_key': 'interior_walls',
                'selection_order': 1,
                'images': [],
            },
            {
                'section_name': 'Ceilings 2',
                'section_key': 'ceilings',
                'subsection_key': 'ceilings',
                'selection_order': 2,
                'images': [],
            },
            {
                'section_name': 'Ceilings',
                'section_key': 'ceilings',
                'subsection_key': 'ceilings',
                'selection_order': 1,
                'images': [],
            },
        ]

        captured = {}

        def fake_render_to_string(template_name, context):
            captured['context'] = context
            return '<html>rendered</html>'

        with patch('quotation.pdf_service.build_pdf_context', return_value={'sections': fake_sections}), \
             patch('django.template.loader.render_to_string', side_effect=fake_render_to_string):
            self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Repeated Section Mapping Draft')

        resolved_sections = self.service.resolver.resolve(self.quotation)['sections']
        sections_by_identity = {
            (section.get('section_key'), int(section.get('selection_order'))): section
            for section in captured['context']['sections']
            if isinstance(section, dict) and section.get('section_key') and section.get('selection_order') is not None
        }
        resolved_by_identity = {
            (section.get('section_key'), int(section.get('selection_order'))): section
            for section in resolved_sections
            if section.get('section_key') and section.get('selection_order') is not None
        }

        self.assertEqual(sections_by_identity[('interior_walls', 1)].get('section_name'), 'Interior Walls')
        self.assertEqual(sections_by_identity[('interior_walls', 2)].get('section_name'), 'Interior Walls 2')
        self.assertEqual(sections_by_identity[('ceilings', 1)].get('section_name'), 'Ceilings')
        self.assertEqual(sections_by_identity[('ceilings', 2)].get('section_name'), 'Ceilings 2')
        self.assertEqual(sections_by_identity[('interior_walls', 1)].get('resolved_id'), resolved_by_identity[('interior_walls', 1)].get('resolved_id'))
        self.assertEqual(sections_by_identity[('interior_walls', 2)].get('resolved_id'), resolved_by_identity[('interior_walls', 2)].get('resolved_id'))
        self.assertEqual(sections_by_identity[('ceilings', 1)].get('resolved_id'), resolved_by_identity[('ceilings', 1)].get('resolved_id'))
        self.assertEqual(sections_by_identity[('ceilings', 2)].get('resolved_id'), resolved_by_identity[('ceilings', 2)].get('resolved_id'))

    def test_manual_pdf_context_keeps_images_isolated_per_section_instance(self):
        from django.template.loader import render_to_string

        section_a = self.quotation.sections.first()
        section_b = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='interior_walls_2',
            display_name='Interior Walls 2',
            selection_order=2,
        )
        section_c = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='ceilings',
            display_name='Ceilings',
            selection_order=3,
        )
        section_d = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key='ceilings_2',
            display_name='Ceilings 2',
            selection_order=4,
        )

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
            b"\x00\x01\x01\x01\x00\x18\xdd\x03\xc5\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        expected_urls = {}
        for section, names in {
            section_a: ['a', 'b'],
            section_b: ['c'],
            section_c: ['d', 'e'],
            section_d: [],
        }.items():
            section_urls = []
            for idx, name in enumerate(names):
                image = QuotationSectionImage.objects.create(
                    section=section,
                    image=SimpleUploadedFile(f"{section.subsection_key}_{name}.png", png_bytes, content_type='image/png'),
                    uploaded_by=self.user,
                    sort_order=idx + 1,
                )
                section_urls.append(image.image.url)
            expected_urls[section.pk] = section_urls

        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Preview Image Draft')
        ctx = PreviewService().preview_context_for_draft(draft)
        by_pk = {
            int(section.get('section_pk')): section
            for section in (ctx.get('sections') or [])
            if isinstance(section, dict) and section.get('section_pk') is not None
        }

        self.assertEqual(len(by_pk[section_a.pk].get('images')), 2)
        self.assertEqual(len(by_pk[section_b.pk].get('images')), 1)
        self.assertEqual(len(by_pk[section_c.pk].get('images')), 2)
        self.assertEqual(len(by_pk[section_d.pk].get('images')), 0)

        rendered = render_to_string('quotation/pdf/manual_specification.html', ctx)
        for urls in expected_urls.values():
            for url in urls:
                self.assertIn(url, rendered)

    def test_manual_preview_reuses_full_automatic_section_payload(self):
        from quotation.pdf_service import build_pdf_context

        repeated = [
            QuotationSection.objects.create(
                quotation=self.quotation,
                subsection_key='interior_walls',
                display_name='Interior Walls 2',
                selection_order=2,
            ),
            QuotationSection.objects.create(
                quotation=self.quotation,
                subsection_key='ceilings',
                display_name='Ceilings',
                selection_order=1,
            ),
            QuotationSection.objects.create(
                quotation=self.quotation,
                subsection_key='ceilings',
                display_name='Ceilings 2',
                selection_order=2,
            ),
        ]
        for section, metadata in {
            repeated[0]: {'wall_type_label': 'Drywall / Plasterboard'},
            repeated[1]: {'type_labels': ['Concrete socket'], 'types': ['concrete_socket']},
            repeated[2]: {'type_labels': ['Gypsum boards'], 'types': ['gypsum_boards']},
        }.items():
            QuotationLineItem.objects.create(
                quotation=self.quotation,
                section=section,
                item_type=QuotationLineItem.ItemType.NOTE,
                description='section note',
                metadata=metadata,
            )

        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Automatic Payload Draft')
        auto_ctx = build_pdf_context(self.quotation, use_resolver=False)
        preview_ctx = PreviewService().preview_context_for_draft(draft)

        self.assertTrue(auto_ctx['sections'])
        self.assertTrue(preview_ctx['sections'])
        self.assertEqual(len(preview_ctx['sections']), len(auto_ctx['sections']))

        for auto_section, manual_section in zip(auto_ctx['sections'], preview_ctx['sections']):
            auto_section_obj = auto_section.get('section') or {}
            manual_section_obj = manual_section.get('section') or {}
            auto_display_name = getattr(auto_section_obj, 'display_name', None) if not isinstance(auto_section_obj, dict) else auto_section_obj.get('display_name')
            manual_display_name = getattr(manual_section_obj, 'display_name', None) if not isinstance(manual_section_obj, dict) else manual_section_obj.get('display_name')
            auto_subsection_key = getattr(auto_section_obj, 'subsection_key', None) if not isinstance(auto_section_obj, dict) else auto_section_obj.get('subsection_key')
            manual_subsection_key = getattr(manual_section_obj, 'subsection_key', None) if not isinstance(manual_section_obj, dict) else manual_section_obj.get('subsection_key')
            auto_selection_order = getattr(auto_section_obj, 'selection_order', None) if not isinstance(auto_section_obj, dict) else auto_section_obj.get('selection_order')
            manual_selection_order = getattr(manual_section_obj, 'selection_order', None) if not isinstance(manual_section_obj, dict) else manual_section_obj.get('selection_order')

            self.assertEqual(auto_display_name, manual_display_name)
            self.assertEqual(auto_subsection_key, manual_subsection_key)
            self.assertEqual(auto_selection_order, manual_selection_order)
            self.assertEqual(auto_section.get('surface_info'), manual_section.get('surface_info'))
            self.assertEqual(auto_section.get('coating_system'), manual_section.get('coating_system'))
            self.assertEqual(auto_section.get('material_summary'), manual_section.get('material_summary'))
            self.assertEqual(auto_section.get('technical'), manual_section.get('technical'))
            self.assertEqual(auto_section.get('prep_instructions'), manual_section.get('prep_instructions'))
            self.assertEqual(auto_section.get('application_requirements'), manual_section.get('application_requirements'))

    def test_manual_item_overrides_are_applied_to_preview_context(self):
        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Preview Override Draft')
        section_key = self.quotation.sections.first().subsection_key
        draft = self.service.save_draft(draft, {
            'resolver': draft.data['resolver'],
            'manual_overrides': {
                section_key: {
                    'preparation_requirements': 'User override prep text.',
                    'application_requirements': 'User override app text.',
                    'images': ['data:image/png;base64,OVERRIDDEN'],
                }
            },
        })

        ctx = PreviewService().preview_context_for_draft(draft)
        section = next(s for s in ctx['sections'] if s.get('section_key') == section_key)
        self.assertEqual(section.get('manual_preparation_requirements'), 'User override prep text.')
        self.assertEqual(section.get('manual_application_requirements'), 'User override app text.')
        self.assertEqual(section.get('images')[0].get('url'), 'data:image/png;base64,OVERRIDDEN')

    def test_manual_pdf_template_prefers_saved_prep_and_app_overrides(self):
        from django.template.loader import render_to_string

        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Render Override Draft')
        section_key = self.quotation.sections.first().subsection_key
        resolver_section = draft.data['resolver']['sections'][0]
        surface_default = resolver_section.get('surface_default') or {}
        automatic_prep = surface_default.get('preparation_requirements')
        if not automatic_prep:
            prep_list = resolver_section.get('prep_instructions') or []
            automatic_prep = prep_list[0] if isinstance(prep_list, list) and prep_list else ''
        automatic_app = resolver_section.get('application_requirements') or ''

        draft = self.service.save_draft(draft, {
            'resolver': draft.data['resolver'],
            'manual_overrides': {
                section_key: {
                    'preparation_requirements': 'Manual prep override for this item.',
                    'application_requirements': 'Manual app override for this item.',
                }
            },
        })

        ctx = PreviewService().preview_context_for_draft(draft)
        rendered = render_to_string('quotation/pdf/manual_specification.html', ctx)

        self.assertIn('Manual prep override for this item.', rendered)
        self.assertIn('Manual app override for this item.', rendered)
        if automatic_prep:
            self.assertNotIn(str(automatic_prep), rendered)
        if automatic_app:
            self.assertNotIn(str(automatic_app), rendered)

    def test_manual_pdf_export_converts_section_images_to_data_uris(self):
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
            b"\x00\x01\x01\x01\x00\x18\xdd\x03\xc5\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        image = QuotationSectionImage.objects.create(
            section=self.section,
            image=SimpleUploadedFile('manual_pdf_section.png', png_bytes, content_type='image/png'),
            uploaded_by=self.user,
            sort_order=1,
        )

        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Manual PDF Image Draft')
        html = ExportService().render_html_for_draft(draft, 'manual_specification')

        self.assertIn('data:image/png;base64,', html)
        self.assertNotIn('/media/quotation/images/', html)
        self.assertNotIn(image.image.url, html)

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

    def test_all_generic_exterior_sections_are_configured(self):
        self.assertIn('exterior_doors_trims_skirtings', ALL_GENERIC_SECTION_CONFIGS)
        cfg = ALL_GENERIC_SECTION_CONFIGS['exterior_doors_trims_skirtings']
        self.assertEqual(cfg.substrate_type, 'EXTERIOR')
        self.assertIn('hardwood', {k for k, _ in cfg.types})
        self.assertIn('smooth_matte', {k for k, _ in cfg.finishes})

    def test_selection_context_distinguishes_brick_vs_drywall_and_finish(self):
        KnowledgeEntry.objects.filter(title__in=['Brick matte primer system', 'Drywall sheen system']).delete()
        brick = KnowledgeEntry.objects.create(
            title='Brick matte primer system',
            body='Use brick-appropriate masonry prep with a matte finish.',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=20,
            metadata={
                'section_key': 'exterior_doors_trims_skirtings',
                'substrate_type': 'EXTERIOR',
                'types': ['brick'],
                'surface_conditions': ['new'],
                'finishes': ['smooth_matte'],
            },
        )
        drywall = KnowledgeEntry.objects.create(
            title='Drywall sheen system',
            body='Use a sheen finish where the substrate is drywall/plasterboard.',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=20,
            metadata={
                'section_key': 'exterior_doors_trims_skirtings',
                'substrate_type': 'EXTERIOR',
                'types': ['drywall'],
                'surface_conditions': ['previously_painted'],
                'finishes': ['smooth_sheen'],
            },
        )

        brick_context = {
            'section_key': 'exterior_doors_trims_skirtings',
            'substrate_type': 'EXTERIOR',
            'types': ['brick'],
            'surface_conditions': ['new'],
            'finishes': ['smooth_matte'],
            'moisture': 8,
        }
        drywall_context = {
            'section_key': 'exterior_doors_trims_skirtings',
            'substrate_type': 'EXTERIOR',
            'types': ['drywall'],
            'surface_conditions': ['previously_painted'],
            'finishes': ['smooth_sheen'],
            'moisture': 12,
        }

        brick_matches = KnowledgeService.find_matches_for_section(None, brick_context)
        drywall_matches = KnowledgeService.find_matches_for_section(None, drywall_context)

        self.assertTrue(any(m.pk == brick.pk for m in brick_matches))
        self.assertTrue(any(m.pk == drywall.pk for m in drywall_matches))
        self.assertNotEqual(
            [m.title for m in brick_matches if m.pk == brick.pk],
            [m.title for m in drywall_matches if m.pk == drywall.pk],
        )

    def test_app_startup_seeds_default_knowledge_when_empty(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()

        from specifications.apps import ensure_default_specification_knowledge

        ensure_default_specification_knowledge()

        self.assertTrue(KnowledgeEntry.objects.filter(is_active=True).exists())
        self.assertTrue(
            KnowledgeEntry.objects.filter(is_active=True, metadata__section_key='exterior_walls').exists()
        )

    def test_seed_default_specification_knowledge_populates_all_generic_sections(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        covered = set(
            KnowledgeEntry.objects.filter(is_active=True, metadata__section_key__isnull=False)
            .values_list('metadata__section_key', flat=True)
            .distinct()
        )

        self.assertTrue(covered)
        self.assertSetEqual(covered, set(ALL_GENERIC_SECTION_CONFIGS) | {'interior_walls'})

    def test_every_configured_section_resolves_a_meaningful_default_match(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        contexts = {
            'interior_walls': {
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'types': ['brick'],
                'surface_conditions': ['cracks'],
                'finishes': ['smooth_matte'],
                'product_groups': ['pure_matte'],
                'moisture': 9,
            },
        }

        for key, cfg in ALL_GENERIC_SECTION_CONFIGS.items():
            if key in contexts:
                continue
            first_type = cfg.types[0][0] if cfg.types else 'generic'
            first_finish = cfg.finishes[0][0] if cfg.finishes else 'smooth_matte'
            first_condition = cfg.surface_conditions[0][0] if cfg.surface_conditions else 'new'
            if first_finish == 'smooth_matte':
                product_group = 'pure_matte'
            elif first_finish == 'smooth_sheen':
                product_group = 'pro_sheen'
            elif first_finish == 'fine_texture':
                product_group = 'texture_pro_fine'
            elif first_finish == 'coarse_texture':
                product_group = 'texture_pro_medium_coarse'
            elif first_finish == 'deco_plast':
                product_group = 'deco_plast_1mm'
            else:
                product_group = 'pure_matte'
            contexts[key] = {
                'section_key': key,
                'substrate_type': cfg.substrate_type,
                'types': [first_type],
                'surface_conditions': [first_condition],
                'finishes': [first_finish],
                'product_groups': [product_group],
                'moisture': 8,
            }

        for key, context in contexts.items():
            matches = KnowledgeService.find_matches_for_section(None, context)
            self.assertTrue(matches, f'No default matches for section {key} with context {context}')
            self.assertTrue(any(m.title.lower() for m in matches), f'No usable title for section {key}')

    def test_seeded_entries_distinguish_materials_and_finish_preferences(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        brick_context = {
            'section_key': 'exterior_walls',
            'substrate_type': 'EXTERIOR',
            'types': ['brick'],
            'surface_conditions': ['new'],
            'finishes': ['smooth_matte'],
            'product_groups': ['pure_matte'],
            'moisture': 8,
        }
        drywall_context = {
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': ['drywall'],
            'surface_conditions': ['previously_painted'],
            'finishes': ['smooth_sheen'],
            'product_groups': ['pro_sheen'],
            'moisture': 12,
        }

        brick_matches = KnowledgeService.find_matches_for_section(None, brick_context)
        drywall_matches = KnowledgeService.find_matches_for_section(None, drywall_context)

        self.assertTrue(any('brick' in m.reason.lower() for m in brick_matches))
        self.assertTrue(any('drywall' in m.reason.lower() for m in drywall_matches))
        self.assertNotEqual(
            {m.title for m in brick_matches if 'brick' in m.reason.lower()},
            {m.title for m in drywall_matches if 'drywall' in m.reason.lower()},
        )

    def test_all_15_live_sections_resolve_meaningful_default_matches(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        fallback_product_groups = {
            'smooth_matte': 'pure_matte',
            'smooth_sheen': 'pro_sheen',
            'deco_plast': 'deco_plast_1mm',
            'fine_texture': 'texture_pro_fine',
            'coarse_texture': 'texture_pro_medium_coarse',
        }
        failures = []

        for section_key in sorted(ALL_SUBSECTIONS):
            if section_key == 'interior_walls':
                type_value = 'brick'
                finish_value = 'smooth_matte'
                condition_value = 'cracks'
                product_group = 'pure_matte'
                substrate_type = 'INTERIOR'
            else:
                cfg = ALL_GENERIC_SECTION_CONFIGS[section_key]
                type_value = cfg.types[0][0]
                finish_value = cfg.finishes[0][0]
                condition_value = cfg.surface_conditions[0][0] if cfg.surface_conditions else 'new'
                product_group = fallback_product_groups.get(finish_value, 'pure_matte')
                substrate_type = cfg.substrate_type

            context = {
                'section_key': section_key,
                'substrate_type': substrate_type,
                'types': [type_value],
                'surface_conditions': [condition_value],
                'finishes': [finish_value],
                'product_groups': [product_group],
                'moisture': 8,
            }

            matches = KnowledgeService.find_matches_for_section(None, context)
            if not matches:
                failures.append(f'{section_key} -> {context}')
                continue
            if not any(m.title for m in matches):
                failures.append(f'{section_key} -> no meaningful title')

        self.assertFalse(failures, f'No default matches found for: {failures}')

    def test_interior_walls_seed_distinguishes_brick_drywall_and_crack_conditions(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        brick_context = {
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': ['brick'],
            'surface_conditions': ['cracks', 'previously_painted'],
            'finishes': ['smooth_matte'],
            'product_groups': ['pure_matte'],
            'moisture': 9,
        }
        drywall_context = {
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': ['drywall'],
            'surface_conditions': ['cracks', 'previously_painted'],
            'finishes': ['smooth_sheen'],
            'product_groups': ['pro_sheen'],
            'moisture': 11,
        }

        brick_matches = KnowledgeService.find_matches_for_section(None, brick_context)
        drywall_matches = KnowledgeService.find_matches_for_section(None, drywall_context)

        brick_titles = {m.title.lower() for m in brick_matches}
        drywall_titles = {m.title.lower() for m in drywall_matches}

        self.assertTrue(any('brick' in title for title in brick_titles))
        self.assertTrue(any('drywall' in title for title in drywall_titles))
        self.assertTrue(any('crack' in title or 'repair' in title for title in brick_titles | drywall_titles))
        self.assertNotEqual(brick_titles, drywall_titles)

    def test_roof_selection_distinguishes_steel_and_concrete(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        steel_context = {
            'section_key': 'roof',
            'substrate_type': 'EXTERIOR',
            'types': ['steel'],
            'surface_conditions': ['prev_painted_good'],
            'finishes': ['smooth_matte'],
            'product_groups': ['pure_matte'],
            'moisture': 9,
        }
        concrete_context = {
            'section_key': 'roof',
            'substrate_type': 'EXTERIOR',
            'types': ['concrete'],
            'surface_conditions': ['prev_painted_good'],
            'finishes': ['smooth_matte'],
            'product_groups': ['pure_matte'],
            'moisture': 10,
        }

        steel_matches = KnowledgeService.find_matches_for_section(None, steel_context)
        concrete_matches = KnowledgeService.find_matches_for_section(None, concrete_context)

        self.assertTrue(any('steel' in m.title.lower() for m in steel_matches))
        self.assertTrue(any('concrete' in m.title.lower() for m in concrete_matches))
        self.assertFalse(any('steel' in m.title.lower() and 'concrete' not in m.title.lower() for m in concrete_matches))
        self.assertFalse(any('concrete' in m.title.lower() and 'steel' not in m.title.lower() for m in steel_matches))

    def test_gutter_selection_distinguishes_metal_and_pvc(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        metal_context = {
            'section_key': 'gutter',
            'substrate_type': 'EXTERIOR',
            'types': ['metal'],
            'surface_conditions': ['prev_painted_good'],
            'finishes': ['smooth_matte'],
            'product_groups': ['pure_matte'],
            'moisture': 9,
        }
        pvc_context = {
            'section_key': 'gutter',
            'substrate_type': 'EXTERIOR',
            'types': ['pvc'],
            'surface_conditions': ['prev_painted_good'],
            'finishes': ['smooth_matte'],
            'product_groups': ['pure_matte'],
            'moisture': 9,
        }

        metal_matches = KnowledgeService.find_matches_for_section(None, metal_context)
        pvc_matches = KnowledgeService.find_matches_for_section(None, pvc_context)

        self.assertTrue(any('metal' in m.title.lower() for m in metal_matches))
        self.assertTrue(any('pvc' in m.title.lower() for m in pvc_matches))
        self.assertFalse(any('pvc' in m.title.lower() for m in metal_matches))
        self.assertFalse(any('metal' in m.title.lower() for m in pvc_matches))

    def test_current_builder_surface_condition_aliases_match_seeded_knowledge(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        matches = KnowledgeService.find_matches_for_section(None, {
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': ['brick'],
            'surface_conditions': ['prev_painted_good'],
            'finishes': ['smooth_matte'],
            'moisture': 8,
        })

        titles = [m.title for m in matches]
        self.assertTrue(any('brick' in title.lower() for title in titles))
        self.assertFalse(any('drywall' in title.lower() for title in titles))

    def test_specific_material_rule_precedes_generic_section_rule(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()

        KnowledgeEntry.objects.create(
            title='PACK2C GENERIC INTERIOR WALLS TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=20,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning'],
                'application_method': 'Generic application',
            },
        )
        KnowledgeEntry.objects.create(
            title='PACK2C BRICK SPECIFIC PRECEDENCE TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=100,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'types': ['brick'],
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning', 'sanding', 'filling'],
                'preparation_requirements': ['cleaning', 'sanding', 'filling'],
                'application_method': 'Brick application method',
                'technical_notes': 'Brick-specific tech guidance',
            },
        )
        KnowledgeEntry.objects.create(
            title='PACK2C DRYWALL SPECIFIC PRECEDENCE TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=90,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'types': ['drywall'],
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning', 'patching'],
                'application_method': 'Drywall application method',
            },
        )

        matches = KnowledgeService.find_matches_for_section(None, {
            'section_key': 'interior_walls',
            'types': ['brick'],
            'surface_conditions': ['cracks'],
            'moisture': 9,
        })

        titles = [m.title for m in matches]
        self.assertIn('PACK2C BRICK SPECIFIC PRECEDENCE TEST', titles)
        self.assertNotIn('PACK2C GENERIC INTERIOR WALLS TEST', titles)
        self.assertNotIn('PACK2C DRYWALL SPECIFIC PRECEDENCE TEST', titles)

    def test_drywall_specific_rule_precedes_generic_section_rule(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()

        KnowledgeEntry.objects.create(
            title='PACK2C GENERIC INTERIOR WALLS TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=20,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning'],
                'application_method': 'Generic application',
            },
        )
        KnowledgeEntry.objects.create(
            title='PACK2C BRICK SPECIFIC PRECEDENCE TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=100,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'types': ['brick'],
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning', 'sanding', 'filling'],
                'preparation_requirements': ['cleaning', 'sanding', 'filling'],
                'application_method': 'Brick application method',
            },
        )
        KnowledgeEntry.objects.create(
            title='PACK2C DRYWALL SPECIFIC PRECEDENCE TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=110,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'types': ['drywall'],
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning', 'patching'],
                'application_method': 'Drywall application method',
            },
        )

        matches = KnowledgeService.find_matches_for_section(None, {
            'section_key': 'interior_walls',
            'types': ['drywall'],
            'surface_conditions': ['cracks'],
            'moisture': 8,
        })

        titles = [m.title for m in matches]
        self.assertIn('PACK2C DRYWALL SPECIFIC PRECEDENCE TEST', titles)
        self.assertNotIn('PACK2C GENERIC INTERIOR WALLS TEST', titles)
        self.assertNotIn('PACK2C BRICK SPECIFIC PRECEDENCE TEST', titles)

    def test_roof_steel_specific_rule_precedes_concrete_generic_rule(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()

        KnowledgeEntry.objects.create(
            title='PACK2C GENERIC ROOF TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=20,
            metadata={
                'section_key': 'roof',
                'substrate_type': 'EXTERIOR',
                'surface_conditions': ['prev_painted_good'],
                'preparations': ['cleaning'],
                'application_method': 'Generic roof application',
            },
        )
        KnowledgeEntry.objects.create(
            title='PACK2C CONCRETE ROOF PRECEDENCE TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=90,
            metadata={
                'section_key': 'roof',
                'substrate_type': 'EXTERIOR',
                'types': ['concrete'],
                'surface_conditions': ['prev_painted_good'],
                'preparations': ['cleaning', 'efflor_removal'],
                'application_method': 'Concrete roof application',
            },
        )
        KnowledgeEntry.objects.create(
            title='PACK2C STEEL ROOF PRECEDENCE TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=100,
            metadata={
                'section_key': 'roof',
                'substrate_type': 'EXTERIOR',
                'types': ['steel'],
                'surface_conditions': ['prev_painted_good'],
                'preparations': ['cleaning', 'rust_treatment'],
                'application_method': 'Steel roof application',
            },
        )

        matches = KnowledgeService.find_matches_for_section(None, {
            'section_key': 'roof',
            'types': ['steel'],
            'surface_conditions': ['prev_painted_good'],
            'moisture': 9,
        })

        titles = [m.title for m in matches]
        self.assertIn('PACK2C STEEL ROOF PRECEDENCE TEST', titles)
        self.assertNotIn('PACK2C GENERIC ROOF TEST', titles)
        self.assertNotIn('PACK2C CONCRETE ROOF PRECEDENCE TEST', titles)

    def test_generic_rule_remains_for_context_when_no_specific_rule_exists(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()

        KnowledgeEntry.objects.create(
            title='PACK2C GENERIC SECTION FALLBACK TEST',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=10,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning'],
                'application_method': 'Fallback application',
            },
        )

        matches = KnowledgeService.find_matches_for_section(None, {
            'section_key': 'interior_walls',
            'types': ['timber'],
            'surface_conditions': ['cracks'],
            'moisture': 9,
        })

        titles = [m.title for m in matches]
        self.assertIn('PACK2C GENERIC SECTION FALLBACK TEST', titles)

    def test_resolver_uses_legacy_interior_wall_type_metadata_for_match_selection(self):
        KnowledgeEntry.objects.filter(is_active=True).delete()
        seed_default_specification_knowledge()

        quote = Quotation.objects.create(
            created_by=self.user,
            customer_name='Legacy Type Test',
            project_name='Legacy Type Test',
            project_location='Johannesburg',
        )
        section = QuotationSection.objects.create(
            quotation=quote,
            subsection_key='interior_walls',
            display_name='Interior Walls',
            selection_order=1,
        )
        QuotationLineItem.objects.create(
            quotation=quote,
            section=section,
            item_type=QuotationLineItem.ItemType.NOTE,
            description='Interior Walls — Drywall / Plasterboard',
            area_sqm=Decimal('18.00'),
            metadata={
                'wall_type': 'drywall',
                'wall_type_label': 'Drywall / Plasterboard',
                'surface_conditions': ['previously_painted'],
                'moisture_level': 8,
                'finishes': ['smooth_matte'],
            },
        )
        QuotationLineItem.objects.create(
            quotation=quote,
            section=section,
            item_type=QuotationLineItem.ItemType.PAINT,
            description='Apply primer and finish',
            paint=self.paint,
            coats=2,
            area_sqm=Decimal('18.00'),
            metadata={'finish': 'smooth_matte'},
        )

        resolved = SpecificationResolver().resolve(quote)
        matches = resolved['sections'][0]['knowledge_matches']

        self.assertTrue(matches)
        self.assertTrue(any(
            'drywall' in str(match.get('title', '')).lower()
            or 'drywall' in str(match.get('reason', '')).lower()
            for match in matches
        ))

    def test_structured_knowledge_form_persists_selection_targeting(self):
        form = KnowledgeEntryForm(data={
            'title': 'Interior Walls Brick Preparation',
            'body': 'Brick walls need repair and a suitable masonry primer before final coating.',
            'category': '',
            'kind': KnowledgeEntry.KIND_CLAUSE,
            'is_default': 'on',
            'is_active': 'on',
            'sort_order': '20',
            'priority': '30',
            'tags': 'seed_default, authoring, interior_walls',
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': 'brick',
            'surface_conditions': 'prev_painted_good, cracks',
            'finishes': 'smooth_matte',
            'preparations': 'cleaning, filling',
            'primers': 'gp_universal',
            'waterproofing': 'hydro_shield',
            'application': 'interior',
            'metadata': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.metadata['section_key'], 'interior_walls')
        self.assertEqual(entry.metadata['types'], ['brick'])
        self.assertEqual(entry.metadata['surface_conditions'], ['prev_painted_good', 'cracks'])
        self.assertEqual(entry.metadata['finishes'], ['smooth_matte'])
        self.assertIn('Interior Walls', entry.selection_summary)
        self.assertIn('Brick', entry.selection_summary)

    def test_surface_default_persists_exact_surface_target(self):
        surface_default = SurfaceDefault.objects.create(
            main_section='INTERIOR',
            subsection='interior_walls',
            surface='brick',
            preparation_requirements='Clean and repair.\nPrime before coating.',
            surface_rules='Brick masonry surfaces require repair and a masonry primer.',
            is_active=True,
        )

        self.assertEqual(surface_default.main_section, 'INTERIOR')
        self.assertEqual(surface_default.subsection, 'interior_walls')
        self.assertEqual(surface_default.surface, 'brick')
        self.assertEqual(surface_default.selection_summary, 'Interior → Interior Walls → Brick')

    def test_surface_default_edit_does_not_alter_other_surfaces(self):
        first = SurfaceDefault.objects.create(
            main_section='INTERIOR',
            subsection='ceilings',
            surface='gypsum_boards',
            preparation_requirements='Prepare boards.',
            surface_rules='Drywall surfaces.',
            is_active=True,
        )
        second = SurfaceDefault.objects.create(
            main_section='INTERIOR',
            subsection='ceilings',
            surface='concrete_socket',
            preparation_requirements='Prepare concrete.',
            surface_rules='Concrete ceiling requires masonry primer.',
            is_active=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.surface, 'gypsum_boards')
        self.assertEqual(second.surface, 'concrete_socket')
        self.assertNotEqual(first.surface, second.surface)

    def test_relevant_selection_persists_exact_checked_values(self):
        form = KnowledgeEntryForm(data={
            'title': 'Interior Walls Brick Only',
            'body': 'Only brick guidance.',
            'category': '',
            'kind': KnowledgeEntry.KIND_CLAUSE,
            'is_default': 'on',
            'is_active': 'on',
            'sort_order': '5',
            'priority': '10',
            'tags': 'brick',
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': 'brick',
            'surface_conditions': 'prev_painted_good',
            'finishes': 'smooth_matte',
            'application': 'interior',
            'metadata': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.metadata['types'], ['brick'])

        reopened = KnowledgeEntryForm(instance=entry)
        self.assertEqual(reopened.fields['types'].initial, ['brick'])

    def test_relevant_selection_updates_when_deselected_on_edit(self):
        entry = KnowledgeEntry.objects.create(
            title='Interior Walls Multi Materials',
            body='Test body',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            metadata={
                'section_key': 'interior_walls',
                'substrate_type': 'INTERIOR',
                'types': ['brick', 'drywall'],
                'surface_conditions': ['prev_painted_good'],
                'finishes': ['smooth_matte'],
                'application': 'interior',
            },
        )

        form = KnowledgeEntryForm(instance=entry, data={
            'title': 'Interior Walls Multi Materials',
            'body': 'Test body',
            'category': '',
            'kind': KnowledgeEntry.KIND_CLAUSE,
            'is_default': 'off',
            'is_active': 'on',
            'sort_order': '5',
            'priority': '10',
            'tags': 'updated',
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': 'brick',
            'surface_conditions': 'prev_painted_good',
            'finishes': 'smooth_matte',
            'application': 'interior',
            'metadata': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.metadata['types'], ['brick'])

        reopened = KnowledgeEntryForm(instance=updated)
        self.assertEqual(reopened.fields['types'].initial, ['brick'])

    def test_form_filters_type_choices_to_selected_subsection(self):
        form = KnowledgeEntryForm()

        roof_choices = dict(form._type_choices_for_section('roof'))
        self.assertIn('steel', roof_choices)
        self.assertIn('concrete', roof_choices)
        self.assertNotIn('pvc', roof_choices)
        self.assertNotIn('brick', roof_choices)

        interior_wall_choices = dict(form._type_choices_for_section('interior_walls'))
        self.assertIn('brick', interior_wall_choices)
        self.assertIn('drywall', interior_wall_choices)
        self.assertNotIn('steel', interior_wall_choices)

    def test_structured_selection_form_persists_preparation_and_guidance(self):
        form = KnowledgeEntryForm(data={
            'title': 'Interior Walls Brick Preparation',
            'body': 'Use a repair-first system before coating.',
            'category': '',
            'kind': KnowledgeEntry.KIND_CLAUSE,
            'is_default': 'on',
            'is_active': 'on',
            'sort_order': '15',
            'priority': '50',
            'tags': 'brick, prep',
            'section_key': 'interior_walls',
            'substrate_type': 'INTERIOR',
            'types': 'brick',
            'surface_conditions': 'previously_painted, cracks',
            'finishes': 'smooth_matte',
            'preparations': 'cleaning, sanding, filling',
            'preparation_requirements': 'cleaning, sanding, filling',
            'additional_preparation_notes': 'Ensure the substrate is sound and dry before coating.',
            'application_method': 'Brush and roll',
            'coating_system_notes': 'Use a masonry-compatible primer as the first coat.',
            'technical_notes': 'Keep moisture below the project threshold before final coating.',
            'drying_recoat_guidance': 'Allow full cure before the next coat.',
            'primers': 'gp_universal',
            'waterproofing': 'hydro_shield',
            'moisture_min': '8',
            'moisture_max': '12',
            'application': 'interior',
            'metadata': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.metadata['preparation_requirements'], ['cleaning', 'sanding', 'filling'])
        self.assertEqual(entry.metadata['preparations'], ['cleaning', 'sanding', 'filling'])
        self.assertEqual(entry.metadata['additional_preparation_notes'], 'Ensure the substrate is sound and dry before coating.')
        self.assertEqual(entry.metadata['application_method'], 'Brush and roll')
        self.assertEqual(entry.metadata['coating_system_notes'], 'Use a masonry-compatible primer as the first coat.')
        self.assertEqual(entry.metadata['technical_notes'], 'Keep moisture below the project threshold before final coating.')
        self.assertEqual(entry.metadata['drying_recoat_guidance'], 'Allow full cure before the next coat.')
        self.assertEqual(entry.metadata['moisture_min'], '8')
        self.assertEqual(entry.metadata['moisture_max'], '12')

    def test_resolver_exposes_structured_knowledge_in_match_body(self):
        entry = KnowledgeEntry.objects.create(
            title='Brick preparation guidance',
            body='General brick guidance.',
            kind=KnowledgeEntry.KIND_CLAUSE,
            is_active=True,
            priority=25,
            metadata={
                'section_key': 'interior_walls',
                'types': ['brick'],
                'surface_conditions': ['cracks'],
                'preparations': ['cleaning', 'sanding', 'filling'],
                'preparation_requirements': ['cleaning', 'sanding', 'filling'],
                'additional_preparation_notes': 'Ensure the substrate is sound and dry.',
                'application_method': 'Brush and roll',
                'coating_system_notes': 'Use a masonry-compatible primer as the first coat.',
                'technical_notes': 'Moisture must be below the project threshold before finish coat.',
                'drying_recoat_guidance': 'Allow full cure before the next coat.',
                'primers': ['gp_universal'],
                'waterproofing': ['hydro_shield'],
                'moisture_min': '8',
                'moisture_max': '12',
            },
        )

        matches = KnowledgeService.find_matches_for_section(None, {
            'section_key': 'interior_walls',
            'types': ['brick'],
            'surface_conditions': ['cracks'],
            'moisture': 9,
        })

        matched = next(m for m in matches if m.pk == entry.pk)
        self.assertIn('Preparation', matched.body)
        self.assertIn('Cleaning', matched.body)
        self.assertIn('Primer', matched.body)
        self.assertIn('Brush and roll', matched.body)
        self.assertIn('Coating System', matched.body)
        self.assertIn('Drying / Recoat', matched.body)
        self.assertIn('Technical Information', matched.body)

    def test_preview_service_prefers_live_resolver_over_stale_rendered_html(self):
        draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Live Preview')
        draft.data["resolver"] = {
            "report_controls": {"show_pricing": True},
            "sections": [{
                "section_name": "Interior Walls",
                "section_key": "interior_walls",
                "clauses": [],
                "product_descriptions": [],
                "images": [],
                "knowledge_matches": [{
                    "pk": 99,
                    "title": "Brick repair guidance",
                    "body": "Clean and prime first.",
                    "priority": 10,
                    "score": 5,
                    "reason": "brick",
                    "matched_conditions": {"types": ["brick"]},
                }],
                "blocks": [],
            }],
        }
        draft.data["rendered_html"] = {"manual_specification": "<html><body>stale preview shell</body></html>"}
        draft.save()

        ctx = PreviewService().preview_context_for_draft(draft)

        self.assertNotIn("rendered_html", ctx)
        self.assertEqual(ctx["sections"][0]["section_name"], "Interior Walls")
        self.assertEqual(ctx["sections"][0]["knowledge_matches"][0]["title"], "Brick repair guidance")

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

    def test_manual_builder_uses_latest_quotation_draft_regardless_of_creator(self):
        User = get_user_model()
        other_user = User.objects.create_user(username='other_builder', email='other@example.test', password='pass')

        latest_quote_draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Latest quote draft')
        stale_user_draft = self.service.create_draft_from_resolver(self.quotation, created_by=other_user, title='Stale other-user draft')

        ManualSpecificationDraft.objects.filter(pk=latest_quote_draft.pk).update(updated_at=timezone.now())
        ManualSpecificationDraft.objects.filter(pk=stale_user_draft.pk).update(updated_at=timezone.now() - timedelta(days=1))

        self.assertEqual(
            self.service.latest_draft_for_user(self.quotation, other_user).pk,
            latest_quote_draft.pk,
        )

    def test_manual_builder_prefers_live_quote_draft_over_newer_stale_fake_draft(self):
        live_draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Live Draft')
        live_draft.data = {
            'resolver': self.service.build_serialisable_automatic_context(self.quotation),
            'manual_overrides': {
                '117': {
                    'preparation_requirements': 'Real prep override',
                    'application_requirements': 'Real app override',
                }
            },
            'draft_overrides': {'pricing_visible': True, 'sections': {}},
        }
        live_draft.save()

        stale_fake_draft = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Stale Fake Draft')
        stale_fake_draft.data = {
            'resolver': {'sections': [{'section_name': 'Test Section', 'section_key': 'test_section', 'subsection_key': 'test_section', 'selection_order': 1, 'blocks': []}]},
            'manual_overrides': {'Test Section': {'preparation_requirements': 'Stale prep', 'application_requirements': 'Stale app'}},
            'draft_overrides': {'pricing_visible': True, 'sections': {}},
        }
        stale_fake_draft.save()

        ManualSpecificationDraft.objects.filter(pk=live_draft.pk).update(updated_at=timezone.now() - timedelta(minutes=5))
        ManualSpecificationDraft.objects.filter(pk=stale_fake_draft.pk).update(updated_at=timezone.now())

        chosen = self.service.latest_draft_for_user(self.quotation, self.user)

        self.assertEqual(chosen.pk, live_draft.pk)
        self.assertEqual(chosen.data['manual_overrides']['117']['preparation_requirements'], 'Real prep override')
        self.assertEqual(chosen.data['manual_overrides']['117']['application_requirements'], 'Real app override')

    def test_manual_builder_rebuilds_from_live_resolver_when_stale_draft_is_empty(self):
        stale = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Stale Draft')
        stale.data = {'resolver': {'sections': []}, 'draft_overrides': {'pricing_visible': True, 'sections': {}}}
        stale.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse('specifications:builder_quotation', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'interior_walls')

    def test_manual_builder_rebuilds_from_live_resolver_when_draft_has_fake_sections(self):
        stale = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Fake Section Draft')
        stale.data = {
            'resolver': {'sections': [{'section_name': 'Test Section', 'section_key': 'test_section', 'subsection_key': 'test_section', 'selection_order': 1, 'blocks': []}]},
            'manual_overrides': {'Test Section': {'preparation_requirements': 'Fake stale prep', 'application_requirements': 'Fake stale app'}},
            'draft_overrides': {'pricing_visible': True, 'sections': {}},
        }
        stale.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse('specifications:builder_quotation', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Interior Walls')
        self.assertNotContains(response, 'Test Section')

    def test_manual_builder_page_exposes_item_and_export_workflow_actions(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('specifications:builder_quotation', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Preview Draft')
        self.assertContains(response, 'Open PDF Options')
        self.assertContains(response, 'Generate Manual Specification PDF')
        self.assertContains(response, 'Manual Specification Builder')
        self.assertContains(response, 'Save Item')
        self.assertContains(response, 'Revert')

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

    def test_manual_builder_uses_current_item_textareas_for_manual_edits(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('specifications:builder_quotation', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('data-field="preparation_requirements"', html)
        self.assertIn('data-field="application_requirements"', html)
        self.assertIn('Save Item', html)
