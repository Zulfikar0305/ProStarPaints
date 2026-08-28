from decimal import Decimal

from django.test import TestCase, RequestFactory

from django.contrib.auth import get_user_model

from .models import Quotation, QuotationSection, QuotationLineItem
from .pdf_service import build_pdf_context
from .spec_report import generate_spec_for_sections
from paints.models import Paint


class Pack5C4_3_SpecReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="specuser", email="s@example.test", password="p")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="SpecCo")

        # Section with note metadata including surface conditions and moisture
        self.s = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='Sec A', selection_order=1)
        self.note = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.s,
            item_type=QuotationLineItem.ItemType.NOTE,
            description='Section note',
            metadata={'surface_cond_labels': ['peeling / flaking', 'mould'], 'moisture_level': '12', 'wall_type_label': 'Brick'}
        )

        # Paint line
        self.paint = Paint.objects.create(
            name='Spec Paint',
            is_active=True,
            spread_rate_per_litre=Decimal('8.00'),
            priced_volume_litres=Decimal('1.00'),
            price_excl_vat=Decimal('40.00'),
            price_incl_vat=Decimal('46.00'),
            base_type='WHITE',
            pricing_method=Paint.PricingMethod.AREA_COATING,
        )
        self.li_paint = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.s,
            item_type=QuotationLineItem.ItemType.PAINT,
            paint=self.paint,
            coats=2,
            area_sqm=Decimal('20.00'),
            price_excl_vat=self.paint.price_excl_vat,
            price_incl_vat=self.paint.price_incl_vat,
            metadata={'surface_cond_labels': ['peeling / flaking'], 'required_litres': '5.00', 'recommended_containers': '1'}
        )

        # Prep work line
        self.li_prep = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.s,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description='Sand and clean',
        )

    def test_generate_spec_sections(self):
        ctx = build_pdf_context(self.q)
        sections = ctx['sections']
        # We expect enriched keys
        self.assertTrue(len(sections) == 1)
        s = sections[0]
        self.assertIn('prep_instructions', s)
        self.assertIn('application_instructions', s)
        self.assertIn('coating_system', s)
        self.assertIn('technical', s)
        self.assertIn('material_summary', s)

        # Prep instructions should include removing loose paint and mould treatment
        self.assertTrue(any('Remove loose paint' in p or 'Remove mould' in p for p in s['prep_instructions']))

    def test_no_duplicate_prep_statements(self):
        # Add another paint with same surface condition to ensure no dupes
        li2 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.s,
            item_type=QuotationLineItem.ItemType.PAINT,
            paint=self.paint,
            coats=1,
            area_sqm=Decimal('10.00'),
            price_excl_vat=self.paint.price_excl_vat,
            price_incl_vat=self.paint.price_incl_vat,
            metadata={'surface_cond_labels': ['peeling / flaking']}
        )
        ctx = build_pdf_context(self.q)
        s = ctx['sections'][0]
        # Ensure prep instructions deduplicated
        seen = set(s['prep_instructions'])
        self.assertEqual(len(seen), len(s['prep_instructions']))

    def test_material_summary_contains_items(self):
        ctx = build_pdf_context(self.q)
        s = ctx['sections'][0]
        ms = s['material_summary']
        self.assertTrue(any(m.get('product') for m in ms))

    def test_authoritative_paint_technical_fields_override_metadata(self):
        self.paint.application_method = 'Spray'
        self.paint.dft_min = Decimal('90.00')
        self.paint.dft_max = Decimal('140.00')
        self.paint.drying_time = '1-2 hours'
        self.paint.recoat_time = '3-4 hours'
        self.paint.tds_reference = 'TDS-ALG-204'
        self.paint.save()
        self.li_paint.metadata = {
            'application_method': 'Brush',
            'dft': '30',
            'drying_time': '12 hours',
            'recoat_time': '24 hours',
            'tds_reference': 'LEGACY-TDS',
        }
        self.li_paint.save(update_fields=['metadata'])

        ctx = build_pdf_context(self.q)
        info = ctx['sections'][0]['technical'][0]['info']

        self.assertEqual(info['application_method'], 'Spray')
        self.assertEqual(info['dft'], '90.00-140.00')
        self.assertEqual(info['drying_time'], '1-2 hours')
        self.assertEqual(info['recoat_time'], '3-4 hours')
        self.assertEqual(info['tds_reference'], 'TDS-ALG-204')

    def test_method_specific_values_follow_selected_application_method(self):
        self.paint.application_method = 'Spray'
        self.paint.application_methods = [
            {'method': 'Brush', 'spread_rate_per_litre': '9.00', 'dft_min': '80.00', 'dft_max': '120.00', 'drying_time': '2-3 hours', 'recoat_time': '4-6 hours', 'tds_reference': 'BRUSH-TDS'},
            {'method': 'Spray', 'spread_rate_per_litre': '6.50', 'dft_min': '60.00', 'dft_max': '90.00', 'drying_time': '1-2 hours', 'recoat_time': '3-4 hours', 'tds_reference': 'SPRAY-TDS'},
        ]
        self.paint.save()
        self.li_paint.metadata = {'application_method': 'Brush'}
        self.li_paint.save(update_fields=['metadata'])

        ctx = build_pdf_context(self.q)
        info = ctx['sections'][0]['technical'][0]['info']

        self.assertEqual(info['application_method'], 'Spray')
        self.assertEqual(str(info['spread_rate_per_litre']), '6.50')
        self.assertEqual(str(info['dft']), '60.00-90.00')
        self.assertEqual(info['drying_time'], '1-2 hours')
        self.assertEqual(info['recoat_time'], '3-4 hours')
        self.assertEqual(info['tds_reference'], 'SPRAY-TDS')

    def test_empty_optional_blocks_are_suppressed_in_rendered_pdf(self):
        from django.template.loader import render_to_string

        ctx = build_pdf_context(self.q)
        ctx['report_controls'] = {
            'show_photos': False,
            'show_moisture_reading': False,
            'show_preparation_requirements': False,
            'show_coating_system': False,
            'show_tds': False,
            'show_product_table': False,
            'show_pricing': False,
            'show_warranty': True,
            'show_recommendations': False,
            'show_notes': False,
        }
        ctx['has_warranty_content'] = False
        rendered = render_to_string('quotation/pdf/detailed_spec.html', ctx)

        self.assertNotIn('Coating System', rendered)
        self.assertNotIn('Technical Information', rendered)
        self.assertNotIn('Material Costing', rendered)
        self.assertNotIn('Warranty', rendered)
        self.assertNotIn('Section Recommendation', rendered)
        self.assertNotIn('Observed Conditions', rendered)

