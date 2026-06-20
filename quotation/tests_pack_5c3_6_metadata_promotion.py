from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model

from quotation.models import Quotation, QuotationSection, QuotationLineItem
from paints.models import Paint
from quotation.pricing import apply_paint_pricing_to_line_item


class MetadataPromotionTest(TestCase):
    def test_spread_rate_promoted_from_nested_metadata(self):
        User = get_user_model()
        user = User.objects.create_user(username='mp_user', email='mp@example.test', password='p')

        q = Quotation.objects.create(created_by=user, customer_name='MP', customer_email='', customer_phone='')
        sec = QuotationSection.objects.create(quotation=q, subsection_key='interior_walls', display_name='MP Sec', selection_order=1)

        paint = Paint.objects.create(
            name='MP Paint',
            is_active=True,
            spread_rate_per_litre=Decimal('7.50'),
            priced_volume_litres=Decimal('1.00'),
            price_excl_vat=Decimal('25.00'),
            price_incl_vat=Decimal('28.75'),
            base_type='WHITE',
            pricing_method=Paint.PricingMethod.AREA_COATING,
            package_size=Decimal('5.00'),
            package_unit='L',
        )

        li = QuotationLineItem.objects.create(
            quotation=q,
            section=sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description='MP test paint',
            paint=paint,
            coats=1,
            area_sqm=Decimal('10.00'),
            price_excl_vat=paint.price_excl_vat,
            price_incl_vat=paint.price_incl_vat,
            metadata={},
        )

        # Apply pricing (should create product_snapshot and populate metadata)
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        meta = li.metadata or {}

        # Required promoted keys
        self.assertIn('product_snapshot', meta)
        self.assertIn('pricing_status', meta)
        self.assertEqual(meta.get('pricing_status'), 'priced')
        self.assertIn('spread_rate_per_litre', meta)
        # JSON-safe string conversion expected for Decimal values
        self.assertEqual(str(paint.spread_rate_per_litre), meta.get('spread_rate_per_litre'))
        self.assertIn('required_litres', meta)
        self.assertIn('recommended_containers', meta)
        # Totals on the line item must be present and positive
        self.assertGreater(li.total_excl_vat, Decimal('0'))
        self.assertGreater(li.total_incl_vat, Decimal('0'))
