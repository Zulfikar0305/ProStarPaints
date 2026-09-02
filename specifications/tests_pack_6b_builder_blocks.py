from copy import deepcopy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from quotation.models import Quotation, QuotationSection, QuotationLineItem
from quotation.pdf_templates import PDF_TEMPLATES
from paints.models import Paint
from specifications.models import SpecificationTemplate, KnowledgeEntry
from specifications.services import ManualSpecificationBuilderService, seed_default_specification_knowledge
from specifications.services.export_service import ExportService
from specifications.services.knowledge_service import KnowledgeService
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

    def test_manual_builder_rebuilds_from_live_resolver_when_stale_draft_is_empty(self):
        stale = self.service.create_draft_from_resolver(self.quotation, created_by=self.user, title='Stale Draft')
        stale.data = {'resolver': {'sections': []}, 'draft_overrides': {'pricing_visible': True, 'sections': {}}}
        stale.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse('specifications:builder_quotation', args=[self.quotation.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'interior_walls')

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
