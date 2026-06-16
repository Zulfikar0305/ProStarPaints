from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model

from paints.models import Paint
from .models import Quotation, QuotationLineItem, QuotationSection
from .pricing import apply_paint_pricing_to_line_item, recalculate_quotation_totals


class PricingAdapterSnapshotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")
        self.sec = QuotationSection.objects.create(quotation=self.q, subsection_key="test", display_name="Test", substrate_type="INTERIOR")

    def test_snapshot_created_on_first_pricing_and_uses_line_prices(self):
        p = Paint.objects.create(
            name="Snap",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("1600.00"),
            price_incl_vat=Decimal("1840.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
            finish=Paint.Finish.SMOOTH_MATTE,
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="Snap",
            paint=p,
            coats=1,
            area_sqm=Decimal("50"),
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={}
        )

        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        ps = li.metadata.get("product_snapshot")
        self.assertIsNotNone(ps)
        # Prices in snapshot must come from line_item price fields (strings)
        self.assertEqual(ps.get("price_excl_vat"), str(li.price_excl_vat))
        self.assertEqual(ps.get("price_incl_vat"), str(li.price_incl_vat))
        # Snapshot should include non-price attrs from paint
        self.assertEqual(ps.get("pricing_method"), str(p.pricing_method))
        self.assertEqual(ps.get("category"), str(p.category))

    def test_historical_safety_area_coating(self):
        p = Paint.objects.create(
            name="HArea",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("1600.00"),
            price_incl_vat=Decimal("1840.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="HArea",
            paint=p,
            coats=1,
            area_sqm=Decimal("50"),
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={}
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        original_total = li.total_excl_vat
        original_snapshot = dict(li.metadata.get("product_snapshot"))

        # Mutate paint
        p.price_excl_vat = Decimal("9999.00")
        p.price_incl_vat = Decimal("11498.85")
        p.spread_rate_per_litre = Decimal("1.00")
        p.priced_volume_litres = Decimal("100.00")
        p.save()

        # Reapply pricing to same line
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        # Totals and snapshot must remain unchanged
        self.assertEqual(li.total_excl_vat, original_total)
        self.assertEqual(li.metadata.get("product_snapshot"), original_snapshot)

    def test_historical_safety_fixed_pack(self):
        p = Paint.objects.create(
            name="HPack",
            category=Paint.Category.CRACKS,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            price_excl_vat=Decimal("100.00"),
            price_incl_vat=Decimal("115.00"),
            package_size=Decimal("2.00"),
            package_unit=Paint.PackageUnit.KILOGRAM,
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="HPack",
            paint=p,
            coats=1,
            area_sqm=None,
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={"package_count": 3}
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        original_total = li.total_excl_vat
        original_snapshot = dict(li.metadata.get("product_snapshot"))

        # Mutate paint
        p.price_excl_vat = Decimal("50.00")
        p.price_incl_vat = Decimal("57.50")
        p.package_size = Decimal("5.00")
        p.variant_label = "changed"
        p.save()

        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.total_excl_vat, original_total)
        self.assertEqual(li.metadata.get("product_snapshot"), original_snapshot)

    def test_historical_safety_per_metre(self):
        p = Paint.objects.create(
            name="HPer",
            category=Paint.Category.SANDING,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.PER_METRE,
            price_excl_vat=Decimal("20.00"),
            price_incl_vat=Decimal("23.00"),
            package_unit=Paint.PackageUnit.METRE,
            variant_label="80 grit",
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="HPer",
            paint=p,
            coats=1,
            area_sqm=None,
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={"roll_count": 2}
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        original_total = li.total_excl_vat
        original_snapshot = dict(li.metadata.get("product_snapshot"))

        # Mutate paint
        p.price_excl_vat = Decimal("999.99")
        p.price_incl_vat = Decimal("1149.99")
        p.variant_label = "60 grit"
        p.save()

        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.total_excl_vat, original_total)
        self.assertEqual(li.metadata.get("product_snapshot"), original_snapshot)

    def test_historical_safety_note_only(self):
        p = Paint.objects.create(
            name="HNote",
            category=Paint.Category.EFFLORESCENCE,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            price_excl_vat=Decimal("0.00"),
            price_incl_vat=Decimal("0.00"),
            predetermined_note="Be careful",
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="HNote",
            paint=p,
            coats=1,
            area_sqm=None,
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={}
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        original_total = li.total_excl_vat
        original_snapshot = dict(li.metadata.get("product_snapshot"))

        # Mutate paint
        p.predetermined_note = "Changed note"
        p.save()

        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.total_excl_vat, original_total)
        self.assertEqual(li.metadata.get("product_snapshot"), original_snapshot)

    def test_pending_state_clearing_and_idempotency(self):
        # Fixed pack with package_count -> priced, then remove package_count -> pending
        p = Paint.objects.create(
            name="TPack",
            category=Paint.Category.MOULD,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            price_excl_vat=Decimal("10.00"),
            price_incl_vat=Decimal("11.50"),
            package_size=Decimal("1.00"),
            package_unit=Paint.PackageUnit.LITRE,
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="TPack",
            paint=p,
            coats=1,
            area_sqm=None,
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={"package_count": 2}
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.quantity, Decimal("2"))
        self.assertEqual(li.unit, "pack")
        first_tot = li.total_excl_vat

        # Reapply idempotent
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.total_excl_vat, first_tot)

        # Now remove package_count -> pending and totals cleared
        li.metadata.pop("package_count", None)
        li.save(update_fields=["metadata"])  # simulate user removing input
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertIsNone(li.quantity)
        self.assertEqual(li.unit, "")
        self.assertEqual(li.total_excl_vat, Decimal("0.00"))
        self.assertEqual(li.metadata.get("pricing_status"), "pending")

    def test_fixed_pack_pending_clears_price_per_package_but_keeps_snapshot_description(self):
        p = Paint.objects.create(
            name="TPack2",
            category=Paint.Category.MOULD,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            price_excl_vat=Decimal("10.00"),
            price_incl_vat=Decimal("11.50"),
            package_size=Decimal("1.00"),
            package_unit=Paint.PackageUnit.LITRE,
            variant_label="VL",
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="TPack2",
            paint=p,
            coats=1,
            area_sqm=None,
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={"package_count": 2}
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        # initial priced values present
        self.assertEqual(li.quantity, Decimal("2"))
        self.assertIn("price_per_package_excl_vat", li.metadata)
        self.assertIn("price_per_package_incl_vat", li.metadata)
        original_snapshot = dict(li.metadata.get("product_snapshot"))

        # remove package_count to force pending
        li.metadata.pop("package_count", None)
        li.save(update_fields=["metadata"])  # simulate user removing input
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()

        # pending assertions
        self.assertIsNone(li.quantity)
        self.assertEqual(li.unit, "")
        self.assertEqual(li.total_excl_vat, Decimal("0.00"))
        self.assertEqual(li.metadata.get("pricing_status"), "pending")
        self.assertEqual(li.metadata.get("pricing_pending_reason"), "missing_package_count")
        # rate keys must be cleared to None, while snapshot description keys remain
        self.assertIsNone(li.metadata.get("price_per_package_excl_vat"))
        self.assertIsNone(li.metadata.get("price_per_package_incl_vat"))
        self.assertEqual(li.metadata.get("product_snapshot"), original_snapshot)
        self.assertEqual(li.metadata.get("package_size"), str(original_snapshot.get("package_size")))
        self.assertEqual(li.metadata.get("package_unit"), original_snapshot.get("package_unit"))

    def test_per_metre_pending_clears_price_per_metre_but_keeps_snapshot_description(self):
        p = Paint.objects.create(
            name="TPer",
            category=Paint.Category.SANDING,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.PER_METRE,
            price_excl_vat=Decimal("20.00"),
            price_incl_vat=Decimal("23.00"),
            package_unit=Paint.PackageUnit.METRE,
            variant_label="80 grit",
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="TPer",
            paint=p,
            coats=1,
            area_sqm=None,
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={"roll_count": 2}
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.quantity, Decimal("2"))
        self.assertIn("price_per_metre_excl_vat", li.metadata)
        self.assertIn("price_per_metre_incl_vat", li.metadata)
        original_snapshot = dict(li.metadata.get("product_snapshot"))

        # remove roll_count to force pending
        li.metadata.pop("roll_count", None)
        li.save(update_fields=["metadata"])  # simulate user removing input
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()

        # pending assertions
        self.assertIsNone(li.quantity)
        self.assertEqual(li.unit, "")
        self.assertEqual(li.total_excl_vat, Decimal("0.00"))
        self.assertEqual(li.metadata.get("pricing_status"), "pending")
        self.assertEqual(li.metadata.get("pricing_pending_reason"), "missing_roll_count")
        # rate keys must be cleared to None, while snapshot description keys remain
        self.assertIsNone(li.metadata.get("price_per_metre_excl_vat"))
        self.assertIsNone(li.metadata.get("price_per_metre_incl_vat"))
        self.assertEqual(li.metadata.get("product_snapshot"), original_snapshot)
        self.assertEqual(li.metadata.get("variant_label"), original_snapshot.get("variant_label"))

    def test_recalculate_totals_includes_zero_and_note_lines(self):
        # Paint line
        p = Paint.objects.create(
            name="R1",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("1600.00"),
            price_incl_vat=Decimal("1840.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
        )
        li1 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="L1",
            paint=p,
            coats=1,
            area_sqm=Decimal("50"),
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={},
        )
        # Note-only line
        pnote = Paint.objects.create(
            name="Note",
            category=Paint.Category.EFFLORESCENCE,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            price_excl_vat=Decimal("0.00"),
            price_incl_vat=Decimal("0.00"),
            predetermined_note="Note it",
        )
        li2 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="Note",
            paint=pnote,
            coats=1,
            area_sqm=None,
            price_excl_vat=pnote.price_excl_vat,
            price_incl_vat=pnote.price_incl_vat,
            metadata={},
        )
        apply_paint_pricing_to_line_item(li1)
        apply_paint_pricing_to_line_item(li2)
        recalculate_quotation_totals(self.q)
        self.q.refresh_from_db()
        # subtotal should equal first line only
        self.assertEqual(self.q.subtotal_excl_vat, Decimal("400.00"))

    def test_existing_product_snapshot_prices_are_used_for_repricing(self):
        # Create paint and price a line to build snapshot
        p = Paint.objects.create(
            name="SArea",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("1600.00"),
            price_incl_vat=Decimal("1840.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="SArea",
            paint=p,
            coats=1,
            area_sqm=Decimal("50"),
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata={},
        )

        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        original_snapshot = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat
        orig_qty = li.quantity
        orig_unit = li.unit

        # Now mutate both the linked Paint and the line_item price fields
        p.price_excl_vat = Decimal("9999.00")
        p.price_incl_vat = Decimal("11499.00")
        p.spread_rate_per_litre = Decimal("1.00")
        p.priced_volume_litres = Decimal("100.00")
        p.save()

        # Also externally change line_item prices (adapter must not overwrite these)
        li.price_excl_vat = Decimal("1.00")
        li.price_incl_vat = Decimal("1.15")
        li.save(update_fields=["price_excl_vat", "price_incl_vat"])

        # Reapply pricing — adapter must use the stored product_snapshot values
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()

        # Snapshot must be unchanged
        self.assertEqual(li.metadata.get("product_snapshot"), original_snapshot)

        # Totals, quantity, and unit must remain the same (i.e., snapshot used)
        self.assertEqual(li.total_excl_vat, orig_total)
        self.assertEqual(li.quantity, orig_qty)
        self.assertEqual(li.unit, orig_unit)

        # The adapter must not overwrite the externally changed line_item price fields
        self.assertEqual(li.price_excl_vat, Decimal("1.00"))
        self.assertEqual(li.price_incl_vat, Decimal("1.15"))