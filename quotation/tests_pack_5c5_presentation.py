from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Quotation, QuotationSection, QuotationLineItem
from paints.models import Paint
from .pdf_service import build_pdf_context

class Pack5C5_PresentationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='present', email='p@example.test', password='p')
        self.q = Quotation.objects.create(created_by=self.user, customer_name='PresentationCo')
        self.s = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='Present Sec', selection_order=1)
        self.paint = Paint.objects.create(
            name='Present Paint', is_active=True, spread_rate_per_litre=8.0, priced_volume_litres=1.0,
            price_excl_vat=40.0, price_incl_vat=46.0, base_type='WHITE', pricing_method=Paint.PricingMethod.AREA_COATING
        )
        self.li = QuotationLineItem.objects.create(
            quotation=self.q, section=self.s, item_type=QuotationLineItem.ItemType.PAINT,
            paint=self.paint, coats=2, area_sqm=10.0, price_excl_vat=self.paint.price_excl_vat, price_incl_vat=self.paint.price_incl_vat,
            metadata={'required_litres':'2.50','recommended_containers':'1'}
        )

    def test_build_context_includes_presentation_keys(self):
        ctx = build_pdf_context(self.q)
        self.assertIn('sections', ctx)
        sec = ctx['sections'][0]
        # Presentation expects these engine-provided lists
        self.assertIn('prep_instructions', sec)
        self.assertIn('coating_system', sec)
        self.assertIn('material_summary', sec)

    def test_material_summary_populated(self):
        ctx = build_pdf_context(self.q)
        sec = ctx['sections'][0]
        ms = sec.get('material_summary')
        self.assertTrue(ms)
        m = ms[0]
        self.assertIn('product', m)
        self.assertIn('required_litres', m)