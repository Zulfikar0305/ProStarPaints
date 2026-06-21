from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string

from quotation.models import Quotation, QuotationSection, QuotationLineItem
from paints.models import Paint
from quotation.pricing import apply_paint_pricing_to_line_item, recalculate_quotation_totals
from quotation.pdf_service import build_pdf_context


class DetailedSpecPdfPersistenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='spec_user', email='spec@example.test', password='p')
        self.q = Quotation.objects.create(created_by=self.user, customer_name='SpecC', customer_email='', customer_phone='')

    def test_persisted_pricing_displayed_in_pdf_context_and_template(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='Sec1', selection_order=1)
        paint = Paint.objects.create(
            name='Spec Paint',
            is_active=True,
            spread_rate_per_litre=Decimal('8.00'),
            priced_volume_litres=Decimal('1.00'),
            price_excl_vat=Decimal('40.00'),
            price_incl_vat=Decimal('46.00'),
            base_type='WHITE',
            pricing_method=Paint.PricingMethod.AREA_COATING,
            package_size=Decimal('5.00'),
            package_unit='L',
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=s,
            item_type=QuotationLineItem.ItemType.PAINT,
            description='Spec paint work',
            paint=paint,
            coats=2,
            area_sqm=Decimal('20.00'),
            price_excl_vat=paint.price_excl_vat,
            price_incl_vat=paint.price_incl_vat,
            metadata={},
        )

        apply_paint_pricing_to_line_item(li)
        # Persist totals on quotation for PDF to display
        recalculate_quotation_totals(self.q)

        ctx = build_pdf_context(self.q)

        # quotation totals present and match persisted
        self.assertEqual(
            ctx['quotation'].subtotal_excl_vat,
            self.q.subtotal_excl_vat,
            f"FAILED ASSERTION: quotation subtotal_excl_vat mismatch: expected {self.q.subtotal_excl_vat}, got {ctx['quotation'].subtotal_excl_vat}"
        )
        self.assertEqual(
            ctx['quotation'].vat_amount,
            self.q.vat_amount,
            f"FAILED ASSERTION: quotation vat_amount mismatch: expected {self.q.vat_amount}, got {ctx['quotation'].vat_amount}"
        )
        self.assertEqual(
            ctx['quotation'].total_incl_vat,
            self.q.total_incl_vat,
            f"FAILED ASSERTION: quotation total_incl_vat mismatch: expected {self.q.total_incl_vat}, got {ctx['quotation'].total_incl_vat}"
        )

        # section totals reflect the single line item total
        sec = ctx['sections'][0]
        self.assertEqual(
            sec['section_total_excl_vat'],
            li.total_excl_vat,
            f"FAILED ASSERTION: section_total_excl_vat mismatch: expected {li.total_excl_vat}, got {sec['section_total_excl_vat']}"
        )

        # metadata keys exist on the line item metadata
        meta = sec['line_items'][0]['item'].metadata
        self.assertIn(
            'spread_rate_per_litre',
            meta,
            "FAILED ASSERTION: expected key 'spread_rate_per_litre' missing from line item metadata."
        )
        self.assertIn(
            'required_litres',
            meta,
            "FAILED ASSERTION: expected key 'required_litres' missing from line item metadata."
        )
        self.assertIn(
            'recommended_containers',
            meta,
            "FAILED ASSERTION: expected key 'recommended_containers' missing from line item metadata."
        )

        # template rendering includes persisted line total
        rendered = render_to_string('quotation/pdf/detailed_spec.html', ctx)
        expected_amount = f'R {li.total_excl_vat:.2f}'
        self.assertIn(
            expected_amount,
            rendered,
            f"FAILED ASSERTION: expected '{expected_amount}' was not found in rendered HTML."
        )

    def test_surface_conditions_rendered_from_metadata_labels(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='Sec2', selection_order=1)
        # Create a note item with pre-populated surface_cond_labels (human-readable labels)
        note = QuotationLineItem.objects.create(
            quotation=self.q,
            section=s,
            item_type=QuotationLineItem.ItemType.NOTE,
            description='Note',
            metadata={'surface_cond_labels': ['new surface', 'peeling / flaking'], 'area_sqm': '15.00'},
        )
        # Build context and ensure description includes Surface:
        ctx = build_pdf_context(self.q)
        self.assertIn(
            'Surface:',
            ctx['sections'][0]['description'],
            "FAILED ASSERTION: expected 'Surface:' to be present in section description."
        )

        # Now create a paint item with surface_cond_labels and ensure the condition column renders it
        paint = Paint.objects.create(
            name='Cond Paint',
            is_active=True,
            spread_rate_per_litre=Decimal('7.00'),
            priced_volume_litres=Decimal('1.00'),
            price_excl_vat=Decimal('30.00'),
            price_incl_vat=Decimal('34.50'),
            base_type='WHITE',
            pricing_method=Paint.PricingMethod.AREA_COATING,
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=s,
            item_type=QuotationLineItem.ItemType.PAINT,
            paint=paint,
            coats=1,
            area_sqm=Decimal('10.00'),
            price_excl_vat=paint.price_excl_vat,
            price_incl_vat=paint.price_incl_vat,
            metadata={'surface_cond_labels': ['previously painted']},
        )
        apply_paint_pricing_to_line_item(li)
        recalculate_quotation_totals(self.q)
        ctx2 = build_pdf_context(self.q)
        rendered = render_to_string('quotation/pdf/detailed_spec.html', ctx2)

        # The PDF now renders surface conditions from the section's canonical
        # surface information (note item), not arbitrary PAINT line metadata.
        # Assert that the canonical description includes a known note label.
        self.assertIn(
            'peeling / flaking',
            ctx2['sections'][0]['description'],
            "FAILED ASSERTION: expected 'peeling / flaking' to appear in section description (canonical surface information)."
        )
