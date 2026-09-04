from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model

from .models import Quotation, QuotationSection, QuotationLineItem
from paints.models import Paint


class Pack5C36RegressionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ruser", email="r@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")

    def test_multiple_paint_row_areas_preserved_and_priced_independently(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        # Create two paints in catalogue
        p1 = Paint.objects.create(name="Test Paint A", is_active=True, spread_rate_per_litre=Decimal('10'), priced_volume_litres=Decimal('5'), price_excl_vat=Decimal('100'), price_incl_vat=Decimal('115'), base_type='WHITE', pricing_method='AREA_COATING')
        p2 = Paint.objects.create(name="Test Paint B", is_active=True, spread_rate_per_litre=Decimal('8'), priced_volume_litres=Decimal('5'), price_excl_vat=Decimal('80'), price_incl_vat=Decimal('92'), base_type='WHITE', pricing_method='AREA_COATING')

        # Simulate two paint rows with independent areas
        li1 = QuotationLineItem.objects.create(quotation=self.q, section=s, item_type=QuotationLineItem.ItemType.PAINT, paint=p1, coats=2, area_sqm=Decimal('120'), price_excl_vat=p1.price_excl_vat, price_incl_vat=p1.price_incl_vat, metadata={"finish":"smooth_matte"})
        li2 = QuotationLineItem.objects.create(quotation=self.q, section=s, item_type=QuotationLineItem.ItemType.PAINT, paint=p2, coats=1, area_sqm=Decimal('45'), price_excl_vat=p2.price_excl_vat, price_incl_vat=p2.price_incl_vat, metadata={"finish":"smooth_sheen"})

        # Apply pricing
        from quotation.pricing import apply_paint_pricing_to_line_item
        apply_paint_pricing_to_line_item(li1)
        apply_paint_pricing_to_line_item(li2)

        # Each line should have non-zero totals and different quantities
        self.assertGreater(li1.total_excl_vat, Decimal('0'))
        self.assertGreater(li2.total_excl_vat, Decimal('0'))
        self.assertNotEqual(li1.quantity, li2.quantity)

    def test_finish_and_paint_isolation_between_sections(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=2)

        # Different finishes are row-level metadata; pricing is driven by the
        # selected paint product, not the finish label alone. Use distinct
        # catalogue products to prove the rows remain isolated and that
        # pricing follows the actual product selection rather than shared state.
        matte_paint = Paint.objects.create(
            name="Matte Iso Paint",
            is_active=True,
            spread_rate_per_litre=Decimal('10'),
            priced_volume_litres=Decimal('5'),
            price_excl_vat=Decimal('50'),
            price_incl_vat=Decimal('57.5'),
            base_type='WHITE',
            pricing_method='AREA_COATING',
        )
        sheen_paint = Paint.objects.create(
            name="Sheen Iso Paint",
            is_active=True,
            spread_rate_per_litre=Decimal('10'),
            priced_volume_litres=Decimal('5'),
            price_excl_vat=Decimal('80'),
            price_incl_vat=Decimal('92.00'),
            base_type='WHITE',
            pricing_method='AREA_COATING',
        )

        li1 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=s1,
            item_type=QuotationLineItem.ItemType.PAINT,
            paint=matte_paint,
            coats=1,
            area_sqm=Decimal('10'),
            price_excl_vat=matte_paint.price_excl_vat,
            price_incl_vat=matte_paint.price_incl_vat,
            metadata={"finish": "smooth_matte"},
        )
        li2 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=s2,
            item_type=QuotationLineItem.ItemType.PAINT,
            paint=sheen_paint,
            coats=1,
            area_sqm=Decimal('20'),
            price_excl_vat=sheen_paint.price_excl_vat,
            price_incl_vat=sheen_paint.price_incl_vat,
            metadata={"finish": "smooth_sheen"},
        )

        from quotation.pricing import apply_paint_pricing_to_line_item
        apply_paint_pricing_to_line_item(li1)
        apply_paint_pricing_to_line_item(li2)

        self.assertEqual(li1.metadata.get('finish'), 'smooth_matte')
        self.assertEqual(li2.metadata.get('finish'), 'smooth_sheen')
        self.assertNotEqual(li1.paint_id, li2.paint_id)
        self.assertNotEqual(li1.total_excl_vat, li2.total_excl_vat)
        self.assertEqual(li1.total_excl_vat, Decimal('50.00'))
        self.assertEqual(li2.total_excl_vat, Decimal('80.00'))

    def test_summary_totals_aggregate_by_type(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        p = Paint.objects.create(name="Sum Paint", is_active=True, spread_rate_per_litre=Decimal('10'), priced_volume_litres=Decimal('5'), price_excl_vat=Decimal('50'), price_incl_vat=Decimal('57.5'), base_type='WHITE', pricing_method='AREA_COATING')

        # paint
        li = QuotationLineItem.objects.create(quotation=self.q, section=s, item_type=QuotationLineItem.ItemType.PAINT, paint=p, coats=1, area_sqm=Decimal('10'), price_excl_vat=p.price_excl_vat, price_incl_vat=p.price_incl_vat, metadata={})
        from quotation.pricing import apply_paint_pricing_to_line_item
        apply_paint_pricing_to_line_item(li)

        # primer
        pr = QuotationLineItem.objects.create(quotation=self.q, section=s, item_type=QuotationLineItem.ItemType.PRIMER, description="Primer", coats=1, area_sqm=Decimal('5'), metadata={})
        # mark totals directly
        pr.total_excl_vat = Decimal('30.00')
        pr.total_incl_vat = Decimal('34.50')
        pr.save()

        from quotation.services import get_quotation_summary
        summary = get_quotation_summary(self.q)
        monetary = summary.get('monetary', {})
        self.assertIn('paint_total_excl_vat', monetary)
        self.assertIn('primer_total_excl_vat', monetary)
