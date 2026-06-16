from decimal import Decimal, ROUND_HALF_UP, getcontext

from django.test import TestCase
from django.contrib.auth import get_user_model

from paints.models import Paint
from .models import Quotation, QuotationLineItem, QuotationSection
from .pricing import (
    calculate_product_pricing,
    calculate_paint_pricing,
    apply_paint_pricing_to_line_item,
    recalculate_quotation_totals,
)


class PricingVerificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="verifier", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")
        self.sec = QuotationSection.objects.create(quotation=self.q, subsection_key="test", display_name="Test", substrate_type="INTERIOR")

    # ------------------------- Group A: Common contract -------------------------
    def _assert_common_contract(self, res, priced_expected=False):
        # mandatory keys
        keys = {
            "pricing_method",
            "pricing_status",
            "pricing_pending_reason",
            "quantity",
            "unit",
            "total_excl_vat",
            "total_incl_vat",
            "vat_amount",
            "metadata",
        }
        self.assertTrue(keys.issubset(set(res.keys())))

        # money types are Decimal
        for k in ("total_excl_vat", "total_incl_vat", "vat_amount"):
            self.assertIsInstance(res.get(k), Decimal)

        # quantization for money values
        for k in ("total_excl_vat", "total_incl_vat", "vat_amount"):
            self.assertEqual(res.get(k), res.get(k).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        # VAT invariant when priced
        if res.get("pricing_status") == "priced":
            self.assertEqual(res.get("total_excl_vat") + res.get("vat_amount"), res.get("total_incl_vat"))

    def test_dispatcher_and_paint_common_contract_and_decimal_context(self):
        # record global decimal context
        before_prec = getcontext().prec

        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("1600.00"),
            "price_incl_vat": Decimal("1840.00"),
            "priced_volume_litres": Decimal("20"),
            "spread_rate_per_litre": Decimal("10"),
            "category": "INTERIOR",
        }
        snap_copy = dict(snap)

        res = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=1)
        self._assert_common_contract(res, priced_expected=True)

        # ensure snapshot not mutated and decimal context unchanged
        self.assertEqual(snap, snap_copy)
        self.assertEqual(getcontext().prec, before_prec)

        # also exercise area leaf calculator directly
        calc = calculate_paint_pricing(
            price_excl_snapshot=Decimal("1600.00"),
            price_incl_snapshot=Decimal("1840.00"),
            priced_volume_litres=Decimal("20"),
            spread_rate_per_litre=Decimal("10"),
            area_sqm=Decimal("50"),
            coats=1,
        )
        self._assert_common_contract(calc, priced_expected=True)

    # ---------------------- Group B: AREA_COATING standard cases ----------------
    def test_area_coating_standard_and_multicoat(self):
        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("1600.00"),
            "price_incl_vat": Decimal("1840.00"),
            "priced_volume_litres": Decimal("20"),
            "spread_rate_per_litre": Decimal("10"),
            "category": "INTERIOR",
        }

        # 1 coat
        res1 = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=1)
        self.assertEqual(res1["quantity"].quantize(Decimal("0.01")), Decimal("5.00"))
        self.assertEqual(res1["total_excl_vat"], Decimal("400.00"))
        self.assertEqual(res1["total_incl_vat"], Decimal("460.00"))
        self.assertEqual(res1["vat_amount"], Decimal("60.00"))
        self.assertEqual(res1["metadata"]["rate_per_sqm_per_coat_excl_vat"], Decimal("8"))

        # 2 coats
        res2 = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=2)
        self.assertEqual(res2["quantity"].quantize(Decimal("0.01")), Decimal("10.00"))
        self.assertEqual(res2["metadata"]["rate_per_sqm_selected_coats_excl_vat"], Decimal("16"))

        # 3 coats
        res3 = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=3)
        self.assertEqual(res3["quantity"].quantize(Decimal("0.01")), Decimal("15.00"))

    def test_area_coating_decimal_rounding_and_vat_from_rounded(self):
        # Create repeating-decimal style inputs to force rounding behaviour
        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("0.333333"),
            "price_incl_vat": Decimal("0.366666"),
            "priced_volume_litres": Decimal("1"),
            "spread_rate_per_litre": Decimal("1"),
            "category": "INTERIOR",
        }
        res = calculate_product_pricing(snap, area_sqm=Decimal("1"), coats=1)
        # total_excl raw = 0.333333 -> quantized 0.33
        self.assertEqual(res["total_excl_vat"], Decimal("0.33"))
        # total_incl raw = 0.366666 -> quantized 0.37
        self.assertEqual(res["total_incl_vat"], Decimal("0.37"))
        # vat computed as difference of quantized totals
        self.assertEqual(res["vat_amount"], Decimal("0.04"))

    def test_area_coating_invalid_inputs_produce_pending(self):
        snap = {"pricing_method": "AREA_COATING"}
        # missing prices
        res = calculate_product_pricing(snap, area_sqm=Decimal("10"), coats=1)
        self.assertEqual(res["pricing_pending_reason"], "missing_price_snapshot")

        # zero priced volume
        snap2 = dict(snap)
        snap2.update({"price_excl_vat": Decimal("1.00"), "price_incl_vat": Decimal("1.15"), "priced_volume_litres": Decimal("0.00"), "spread_rate_per_litre": Decimal("1.0"), "category": "INTERIOR"})
        res2 = calculate_product_pricing(snap2, area_sqm=Decimal("1"), coats=1)
        self.assertEqual(res2["pricing_pending_reason"], "missing_priced_volume")

        # missing spread rate
        snap3 = dict(snap2)
        snap3["priced_volume_litres"] = Decimal("1.00")
        snap3["spread_rate_per_litre"] = None
        res3 = calculate_product_pricing(snap3, area_sqm=Decimal("1"), coats=1)
        self.assertEqual(res3["pricing_pending_reason"], "missing_spread_rate")

        # missing area
        res4 = calculate_product_pricing(snap2, area_sqm=None, coats=1)
        self.assertEqual(res4["pricing_pending_reason"], "missing_area")

        # invalid coats for ordinary area product
        res5 = calculate_product_pricing(snap2, area_sqm=Decimal("1"), coats=0)
        self.assertEqual(res5["pricing_pending_reason"], "invalid_coats")
        res6 = calculate_product_pricing(snap2, area_sqm=Decimal("1"), coats=1.5)
        self.assertEqual(res6["pricing_pending_reason"], "invalid_coats")

    def test_area_coating_primer_and_waterproofing_one_coat_rules(self):
        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": Decimal("115.00"),
            "priced_volume_litres": Decimal("10"),
            "spread_rate_per_litre": Decimal("5"),
            "category": "PRIMER",
        }
        # omitted coats -> treated as 1
        res = calculate_product_pricing(snap, area_sqm=Decimal("10"), coats=None)
        self.assertEqual(res["pricing_status"], "priced")
        # explicit 1 allowed
        res2 = calculate_product_pricing(snap, area_sqm=Decimal("10"), coats=1)
        self.assertEqual(res2["pricing_status"], "priced")
        # explicit 2 not allowed
        res3 = calculate_product_pricing(snap, area_sqm=Decimal("10"), coats=2)
        self.assertEqual(res3["pricing_pending_reason"], "invalid_coats")

    # ------------------------- Group C: FIXED_PACK -------------------------
    def test_fixed_pack_basic_and_boundaries(self):
        snap = {
            "pricing_method": "FIXED_PACK",
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": Decimal("115.00"),
            "package_size": Decimal("2.00"),
            "package_unit": "kg",
            "variant_label": "V",
        }
        # package_count variants
        for n in (1, 2, 3):
            res = calculate_product_pricing(snap, package_count=n)
            self.assertEqual(res["pricing_status"], "priced")
            self.assertEqual(res["quantity"], Decimal(n))
            self.assertEqual(res["unit"], "pack")
            self.assertEqual(res["total_excl_vat"], Decimal("100.00") * Decimal(n))
            self.assertEqual(res["total_incl_vat"], Decimal("115.00") * Decimal(n))

        # missing count
        res2 = calculate_product_pricing(snap)
        self.assertEqual(res2["pricing_pending_reason"], "missing_package_count")
        # fractional -> invalid
        res3 = calculate_product_pricing(snap, package_count=1.5)
        self.assertEqual(res3["pricing_pending_reason"], "invalid_package_count")
        # zero -> invalid
        res4 = calculate_product_pricing(snap, package_count=0)
        self.assertEqual(res4["pricing_pending_reason"], "invalid_package_count")

    # ------------------------- Group D: PER_METRE -------------------------
    def test_per_metre_basic_and_boundaries(self):
        snap = {
            "pricing_method": "PER_METRE",
            "price_excl_vat": Decimal("20.00"),
            "price_incl_vat": Decimal("23.00"),
            "package_unit": "m",
            "variant_label": "80 grit",
        }
        for n in (1, 2, 4):
            res = calculate_product_pricing(snap, roll_count=n)
            self.assertEqual(res["pricing_status"], "priced")
            self.assertEqual(res["quantity"], Decimal(n))
            self.assertEqual(res["unit"], "m")
            self.assertEqual(res["total_excl_vat"], Decimal("20.00") * Decimal(n))

        # missing -> pending
        res2 = calculate_product_pricing(snap)
        self.assertEqual(res2["pricing_pending_reason"], "missing_roll_count")
        # fractional -> invalid
        res3 = calculate_product_pricing(snap, roll_count=1.5)
        self.assertEqual(res3["pricing_pending_reason"], "invalid_roll_count")

    # ------------------------- Group E: NOTE_ONLY -------------------------
    def test_note_only_valid_and_invalid_notes(self):
        snap = {"pricing_method": "NOTE_ONLY", "predetermined_note": "Do special"}
        res = calculate_product_pricing(snap)
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["total_excl_vat"], Decimal("0.00"))
        self.assertEqual(res["quantity"], None)
        self.assertEqual(res["unit"], "")

        snap_bad = {"pricing_method": "NOTE_ONLY", "predetermined_note": "   "}
        res2 = calculate_product_pricing(snap_bad)
        self.assertEqual(res2["pricing_pending_reason"], "missing_predetermined_note")

    # ------------------------- Group F: Snapshot immutability -----------------
    def test_snapshot_immutability_for_all_methods(self):
        # AREA_COATING
        p_area = Paint.objects.create(
            name="VArea",
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
            description="VArea",
            paint=p_area,
            coats=1,
            area_sqm=Decimal("50"),
            price_excl_vat=p_area.price_excl_vat,
            price_incl_vat=p_area.price_incl_vat,
            metadata={},
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        orig_snapshot = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat

        # Mutate paint and line prices
        p_area.price_excl_vat = Decimal("1.00")
        p_area.price_incl_vat = Decimal("1.15")
        p_area.save()
        li.price_excl_vat = Decimal("2.00")
        li.price_incl_vat = Decimal("2.30")
        li.save(update_fields=["price_excl_vat", "price_incl_vat"])

        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        # snapshot & totals unchanged
        self.assertEqual(li.metadata.get("product_snapshot"), orig_snapshot)
        self.assertEqual(li.total_excl_vat, orig_total)

        # FIXED_PACK
        p_pack = Paint.objects.create(
            name="VPack",
            category=Paint.Category.MOULD,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            price_excl_vat=Decimal("10.00"),
            price_incl_vat=Decimal("11.50"),
            package_size=Decimal("1.00"),
            package_unit=Paint.PackageUnit.LITRE,
        )
        lip = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="VPack",
            paint=p_pack,
            metadata={"package_count": 2},
            price_excl_vat=p_pack.price_excl_vat,
            price_incl_vat=p_pack.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(lip)
        lip.refresh_from_db()
        orig_snapshot_p = dict(lip.metadata.get("product_snapshot"))
        orig_total_p = lip.total_excl_vat

        p_pack.price_excl_vat = Decimal("999.99")
        p_pack.price_incl_vat = Decimal("1149.99")
        p_pack.package_size = Decimal("5.00")
        p_pack.variant_label = "changed"
        p_pack.save()
        lip.price_excl_vat = Decimal("0.01")
        lip.price_incl_vat = Decimal("0.01")
        lip.save(update_fields=["price_excl_vat", "price_incl_vat"])

        apply_paint_pricing_to_line_item(lip)
        lip.refresh_from_db()
        self.assertEqual(lip.metadata.get("product_snapshot"), orig_snapshot_p)
        self.assertEqual(lip.total_excl_vat, orig_total_p)

        # PER_METRE
        p_per = Paint.objects.create(
            name="VPer",
            category=Paint.Category.SANDING,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.PER_METRE,
            price_excl_vat=Decimal("20.00"),
            price_incl_vat=Decimal("23.00"),
            package_unit=Paint.PackageUnit.METRE,
            variant_label="80 grit",
        )
        lipm = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="VPer",
            paint=p_per,
            metadata={"roll_count": 2},
            price_excl_vat=p_per.price_excl_vat,
            price_incl_vat=p_per.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(lipm)
        lipm.refresh_from_db()
        orig_snapshot_m = dict(lipm.metadata.get("product_snapshot"))
        orig_total_m = lipm.total_excl_vat

        p_per.price_excl_vat = Decimal("1.00")
        p_per.price_incl_vat = Decimal("1.15")
        p_per.variant_label = "60 grit"
        p_per.save()
        lipm.price_excl_vat = Decimal("0.50")
        lipm.price_incl_vat = Decimal("0.50")
        lipm.save(update_fields=["price_excl_vat", "price_incl_vat"])

        apply_paint_pricing_to_line_item(lipm)
        lipm.refresh_from_db()
        self.assertEqual(lipm.metadata.get("product_snapshot"), orig_snapshot_m)
        self.assertEqual(lipm.total_excl_vat, orig_total_m)

        # NOTE_ONLY
        p_note = Paint.objects.create(
            name="VNote",
            category=Paint.Category.EFFLORESCENCE,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            price_excl_vat=Decimal("0.00"),
            price_incl_vat=Decimal("0.00"),
            predetermined_note="Be careful",
        )
        lin = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="VNote",
            paint=p_note,
            metadata={},
            price_excl_vat=p_note.price_excl_vat,
            price_incl_vat=p_note.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(lin)
        lin.refresh_from_db()
        orig_snapshot_n = dict(lin.metadata.get("product_snapshot"))
        p_note.predetermined_note = "Changed"
        p_note.save()
        lin.price_excl_vat = Decimal("9.99")
        lin.price_incl_vat = Decimal("11.49")
        lin.save(update_fields=["price_excl_vat", "price_incl_vat"])
        apply_paint_pricing_to_line_item(lin)
        lin.refresh_from_db()
        self.assertEqual(lin.metadata.get("product_snapshot"), orig_snapshot_n)

    # ------------------------- Group G: Pending transitions & recovery --------
    def test_pending_and_recovery_area_fixed_per(self):
        # AREA_COATING: price, remove area -> pending, restore -> priced
        p = Paint.objects.create(
            name="RecArea",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("100.00"),
            price_incl_vat=Decimal("115.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("10"),
        )
        li = QuotationLineItem.objects.create(
            quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT,
            description="RecArea", paint=p, coats=1, area_sqm=Decimal("10"), price_excl_vat=p.price_excl_vat, price_incl_vat=p.price_incl_vat, metadata={},
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        orig_snapshot = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat

        # remove area
        li.area_sqm = None
        li.save(update_fields=["area_sqm"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertIsNone(li.quantity)
        self.assertEqual(li.unit, "")
        self.assertEqual(li.total_excl_vat, Decimal("0.00"))
        self.assertEqual(li.metadata.get("pricing_status"), "pending")
        # stale area keys cleared
        self.assertIsNone(li.metadata.get("price_per_litre_excl_vat"))
        self.assertIsNone(li.metadata.get("required_litres"))
        # snapshot remains
        self.assertEqual(li.metadata.get("product_snapshot"), orig_snapshot)

        # restore area and reprice
        li.area_sqm = Decimal("10")
        li.save(update_fields=["area_sqm"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.total_excl_vat, orig_total)

        # FIXED_PACK pending -> recovery (simulate removal of package_count)
        p2 = Paint.objects.create(
            name="RecPack",
            category=Paint.Category.MOULD,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            price_excl_vat=Decimal("10.00"),
            price_incl_vat=Decimal("11.50"),
            package_size=Decimal("1.00"),
            package_unit=Paint.PackageUnit.LITRE,
        )
        li2 = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="RecPack", paint=p2, metadata={"package_count": 2}, price_excl_vat=p2.price_excl_vat, price_incl_vat=p2.price_incl_vat)
        apply_paint_pricing_to_line_item(li2)
        li2.refresh_from_db()
        orig_snapshot2 = dict(li2.metadata.get("product_snapshot"))
        orig_total2 = li2.total_excl_vat

        # remove package_count -> pending
        li2.metadata.pop("package_count", None)
        li2.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li2)
        li2.refresh_from_db()
        self.assertIsNone(li2.quantity)
        self.assertEqual(li2.unit, "")
        self.assertEqual(li2.total_excl_vat, Decimal("0.00"))
        self.assertEqual(li2.metadata.get("pricing_pending_reason"), "missing_package_count")
        self.assertIsNone(li2.metadata.get("price_per_package_excl_vat"))
        self.assertEqual(li2.metadata.get("product_snapshot"), orig_snapshot2)

        # restore and recover
        li2.metadata["package_count"] = 2
        li2.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li2)
        li2.refresh_from_db()
        self.assertEqual(li2.total_excl_vat, orig_total2)

        # PER_METRE pending -> recovery
        p3 = Paint.objects.create(
            name="RecPer",
            category=Paint.Category.SANDING,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.PER_METRE,
            price_excl_vat=Decimal("20.00"),
            price_incl_vat=Decimal("23.00"),
            package_unit=Paint.PackageUnit.METRE,
            variant_label="80 grit",
        )
        li3 = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="RecPer", paint=p3, metadata={"roll_count": 2}, price_excl_vat=p3.price_excl_vat, price_incl_vat=p3.price_incl_vat)
        apply_paint_pricing_to_line_item(li3)
        li3.refresh_from_db()
        orig_snapshot3 = dict(li3.metadata.get("product_snapshot"))
        orig_total3 = li3.total_excl_vat

        li3.metadata.pop("roll_count", None)
        li3.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li3)
        li3.refresh_from_db()
        self.assertIsNone(li3.quantity)
        self.assertEqual(li3.total_excl_vat, Decimal("0.00"))
        self.assertIsNone(li3.metadata.get("price_per_metre_excl_vat"))
        self.assertEqual(li3.metadata.get("product_snapshot"), orig_snapshot3)

        # recover
        li3.metadata["roll_count"] = 2
        li3.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li3)
        li3.refresh_from_db()
        self.assertEqual(li3.total_excl_vat, orig_total3)

    # ------------------------- Group H: Mixed quotation totals -----------------
    def test_mixed_quotation_totals(self):
        # AREA_COATING line
        pA = Paint.objects.create(name="MArea", category=Paint.Category.INTERIOR, base_type=Paint.BaseType.WHITE, price_excl_vat=Decimal("100.00"), price_incl_vat=Decimal("115.00"), spread_rate_per_litre=Decimal("10"), priced_volume_litres=Decimal("10"))
        la = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="LA", paint=pA, coats=1, area_sqm=Decimal("10"), price_excl_vat=pA.price_excl_vat, price_incl_vat=pA.price_incl_vat, metadata={})
        apply_paint_pricing_to_line_item(la)

        # FIXED_PACK priced
        pF = Paint.objects.create(name="MF", category=Paint.Category.MOULD, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.FIXED_PACK, price_excl_vat=Decimal("10.00"), price_incl_vat=Decimal("11.50"), package_size=Decimal("1.00"), package_unit=Paint.PackageUnit.LITRE)
        lf = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="LF", paint=pF, metadata={"package_count": 2}, price_excl_vat=pF.price_excl_vat, price_incl_vat=pF.price_incl_vat)
        apply_paint_pricing_to_line_item(lf)

        # PER_METRE priced
        pM = Paint.objects.create(name="MM", category=Paint.Category.SANDING, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.PER_METRE, price_excl_vat=Decimal("5.00"), price_incl_vat=Decimal("5.75"), package_unit=Paint.PackageUnit.METRE, variant_label="40 grit")
        lm = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="LM", paint=pM, metadata={"roll_count": 1}, price_excl_vat=pM.price_excl_vat, price_incl_vat=pM.price_incl_vat)
        apply_paint_pricing_to_line_item(lm)

        # NOTE_ONLY
        pN = Paint.objects.create(name="MN", category=Paint.Category.EFFLORESCENCE, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.NOTE_ONLY, price_excl_vat=Decimal("0.00"), price_incl_vat=Decimal("0.00"), predetermined_note="Note")
        ln = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="LN", paint=pN, metadata={}, price_excl_vat=pN.price_excl_vat, price_incl_vat=pN.price_incl_vat)
        apply_paint_pricing_to_line_item(ln)

        # Pending zero-total line (fixed pack missing count)
        pP = Paint.objects.create(name="MP", category=Paint.Category.MOULD, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.FIXED_PACK, price_excl_vat=Decimal("7.00"), price_incl_vat=Decimal("8.05"), package_size=Decimal("1.00"), package_unit=Paint.PackageUnit.LITRE)
        lp = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="LP", paint=pP, metadata={}, price_excl_vat=pP.price_excl_vat, price_incl_vat=pP.price_incl_vat)
        apply_paint_pricing_to_line_item(lp)

        recalculate_quotation_totals(self.q)
        self.q.refresh_from_db()

        # subtotal = la.total_excl + lf.total_excl + lm.total_excl + ln(total_excl=0) + lp(0)
        expected = la.total_excl_vat + lf.total_excl_vat + lm.total_excl_vat
        self.assertEqual(self.q.subtotal_excl_vat, expected)
        self.assertEqual(self.q.total_incl_vat, la.total_incl_vat + lf.total_incl_vat + lm.total_incl_vat)
        self.assertEqual(self.q.vat_amount, self.q.total_incl_vat - self.q.subtotal_excl_vat)

    # ------------------------- Group I: Caller compatibility -------------------
    def test_apply_pricing_saves_and_returns_line_item(self):
        p = Paint.objects.create(name="Compat", category=Paint.Category.INTERIOR, base_type=Paint.BaseType.WHITE, price_excl_vat=Decimal("100.00"), price_incl_vat=Decimal("115.00"), spread_rate_per_litre=Decimal("10"), priced_volume_litres=Decimal("10"))
        li = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="Compat", paint=p, coats=1, area_sqm=Decimal("10"), price_excl_vat=p.price_excl_vat, price_incl_vat=p.price_incl_vat, metadata={})
        returned = apply_paint_pricing_to_line_item(li)
        # adapter returns the line_item and persisted changes
        self.assertEqual(returned.pk, li.pk)
        li.refresh_from_db()
        self.assertIn("product_snapshot", li.metadata)

from decimal import Decimal, ROUND_HALF_UP, getcontext

from django.test import TestCase
from django.contrib.auth import get_user_model

from paints.models import Paint
from .models import Quotation, QuotationLineItem, QuotationSection
from .pricing import (
    calculate_product_pricing,
    calculate_paint_pricing,
    apply_paint_pricing_to_line_item,
    recalculate_quotation_totals,
)


class PricingVerificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="verifier", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")
        self.sec = QuotationSection.objects.create(quotation=self.q, subsection_key="test", display_name="Test", substrate_type="INTERIOR")

    # ---------- Group A: Common result contract and VAT invariant ----------
    def assert_common_contract(self, res):
        keys = {
            "pricing_method",
            "pricing_status",
            "pricing_pending_reason",
            "quantity",
            "unit",
            "total_excl_vat",
            "total_incl_vat",
            "vat_amount",
            "metadata",
        }
        self.assertTrue(keys.issubset(set(res.keys())))
        # money types must be Decimal when present
        for k in ("total_excl_vat", "total_incl_vat", "vat_amount"):
            self.assertIsInstance(res.get(k), Decimal)
            # Quantized to 2 dp
            q = res.get(k).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.assertEqual(res.get(k), q)
        # VAT invariant for priced results
        if res.get("pricing_status") == "priced":
            self.assertEqual((res["total_excl_vat"] + res["vat_amount"]).quantize(Decimal("0.01")), res["total_incl_vat"])

    def test_common_contract_and_decimal_context_unchanged(self):
        # Save global context
        orig_prec = getcontext().prec
        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("1600.00"),
            "price_incl_vat": Decimal("1840.00"),
            "priced_volume_litres": Decimal("20"),
            "spread_rate_per_litre": Decimal("10"),
            "category": "INTERIOR",
        }
        snap_copy = dict(snap)
        res = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=1)
        # snapshot must not be mutated
        self.assertEqual(snap, snap_copy)
        # Decimal global context unchanged
        self.assertEqual(getcontext().prec, orig_prec)
        # Common contract
        self.assert_common_contract(res)

    # ---------- Group B: AREA_COATING ----------
    def test_area_coating_standard_calculation(self):
        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("1600.00"),
            "price_incl_vat": Decimal("1840.00"),
            "priced_volume_litres": Decimal("20"),
            "spread_rate_per_litre": Decimal("10"),
            "category": "INTERIOR",
        }
        res = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=1)
        self.assertEqual(res["pricing_status"], "priced")
        # required litres = 50 * 1 / 10 = 5
        required = res.get("quantity")
        self.assertIsNotNone(required)
        self.assertEqual(required.quantize(Decimal("0.01")), Decimal("5.00"))
        # price per litre
        self.assertEqual(res.get("metadata").get("price_per_litre_excl_vat"), Decimal("80.00"))
        self.assertEqual(res.get("metadata").get("price_per_litre_incl_vat"), Decimal("92.00"))
        # totals
        self.assertEqual(res.get("total_excl_vat"), Decimal("400.00"))
        self.assertEqual(res.get("total_incl_vat"), Decimal("460.00"))
        self.assertEqual(res.get("vat_amount"), Decimal("60.00"))

    def test_area_coating_multiple_coats(self):
        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("1600.00"),
            "price_incl_vat": Decimal("1840.00"),
            "priced_volume_litres": Decimal("20"),
            "spread_rate_per_litre": Decimal("10"),
            "category": "INTERIOR",
        }
        res2 = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=2)
        res3 = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=3)
        self.assertEqual(res2.get("quantity").quantize(Decimal("0.01")), Decimal("10.00"))
        self.assertEqual(res3.get("quantity").quantize(Decimal("0.01")), Decimal("15.00"))
        # Totals scale proportionally
        self.assertEqual(res2.get("total_excl_vat"), Decimal("800.00"))
        self.assertEqual(res3.get("total_excl_vat"), Decimal("1200.00"))

    def test_area_coating_decimal_and_rounding(self):
        # Create half-cent scenario via a price with 3 decimal places
        snap = {
            "pricing_method": "AREA_COATING",
            "price_excl_vat": Decimal("100.005"),
            "price_incl_vat": Decimal("115.005"),
            "priced_volume_litres": Decimal("1.00"),
            "spread_rate_per_litre": Decimal("1.00"),
            "category": "INTERIOR",
        }
        res = calculate_product_pricing(snap, area_sqm=Decimal("1.00"), coats=1)
        # total_excl intermediate 100.005 -> quantized HALF_UP -> 100.01
        self.assertEqual(res.get("total_excl_vat"), Decimal("100.01"))
        # VAT computed from quantized totals
        self.assertEqual(res.get("vat_amount"), (res.get("total_incl_vat") - res.get("total_excl_vat")))

    def test_area_coating_invalid_inputs_yield_pending(self):
        snap = {"pricing_method": "AREA_COATING"}
        # missing prices
        r = calculate_product_pricing(snap, area_sqm=Decimal("10"), coats=1)
        self.assertEqual(r.get("pricing_status"), "pending")
        self.assertEqual(r.get("pricing_pending_reason"), "missing_price_snapshot")

    def test_primer_waterproofing_one_coat_enforced(self):
        snap = {
            "pricing_method": "AREA_COATING",
            "category": "PRIMER",
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": Decimal("115.00"),
            "priced_volume_litres": Decimal("1.00"),
            "spread_rate_per_litre": Decimal("10.00"),
        }
        # omitted coats accepted and treated as 1
        r = calculate_product_pricing(snap, area_sqm=Decimal("10"), coats=None)
        self.assertEqual(r.get("pricing_status"), "priced")
        # explicit 2 coats rejected for primer/waterproofing
        r2 = calculate_product_pricing(snap, area_sqm=Decimal("10"), coats=2)
        self.assertEqual(r2.get("pricing_status"), "pending")
        self.assertEqual(r2.get("pricing_pending_reason"), "invalid_coats")

    # ---------- Group C: FIXED_PACK ----------
    def test_fixed_pack_counts_and_invalids(self):
        snap = {
            "pricing_method": "FIXED_PACK",
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": Decimal("115.00"),
            "package_size": Decimal("2.00"),
            "package_unit": "kg",
            "variant_label": "std",
        }
        r1 = calculate_product_pricing(snap, package_count=1)
        r2 = calculate_product_pricing(snap, package_count=3)
        self.assertEqual(r1.get("total_excl_vat"), Decimal("100.00"))
        self.assertEqual(r2.get("total_excl_vat"), Decimal("300.00"))
        self.assertEqual(r2.get("quantity"), Decimal(3))
        self.assertEqual(r2.get("unit"), "pack")
        # missing / fractional
        rm = calculate_product_pricing(snap)
        self.assertEqual(rm.get("pricing_pending_reason"), "missing_package_count")
        rf = calculate_product_pricing(snap, package_count=1.5)
        self.assertEqual(rf.get("pricing_pending_reason"), "invalid_package_count")

    # ---------- Group D: PER_METRE ----------
    def test_per_metre_counts_and_invalids(self):
        snap = {
            "pricing_method": "PER_METRE",
            "price_excl_vat": Decimal("20.00"),
            "price_incl_vat": Decimal("23.00"),
            "package_unit": "m",
            "variant_label": "80 grit",
        }
        r1 = calculate_product_pricing(snap, roll_count=1)
        r2 = calculate_product_pricing(snap, roll_count=4)
        self.assertEqual(r1.get("total_excl_vat"), Decimal("20.00"))
        self.assertEqual(r2.get("total_excl_vat"), Decimal("80.00"))
        self.assertEqual(r2.get("unit"), "m")
        rm = calculate_product_pricing(snap)
        self.assertEqual(rm.get("pricing_pending_reason"), "missing_roll_count")
        rf = calculate_product_pricing(snap, roll_count=1.5)
        self.assertEqual(rf.get("pricing_pending_reason"), "invalid_roll_count")

    # ---------- Group E: NOTE_ONLY ----------
    def test_note_only_valid_and_invalid(self):
        snap_ok = {"pricing_method": "NOTE_ONLY", "predetermined_note": "Do this"}
        r = calculate_product_pricing(snap_ok)
        self.assertEqual(r.get("pricing_status"), "priced")
        self.assertEqual(r.get("total_excl_vat"), Decimal("0.00"))
        self.assertEqual(r.get("vat_amount"), Decimal("0.00"))
        snap_bad = {"pricing_method": "NOTE_ONLY", "predetermined_note": "   "}
        rb = calculate_product_pricing(snap_bad)
        self.assertEqual(rb.get("pricing_pending_reason"), "missing_predetermined_note")

    # ---------- Group F: Snapshot immutability ----------
    def _create_and_price_line(self, paint_kwargs, li_kwargs, meta=None):
        p = Paint.objects.create(**paint_kwargs)
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="V",
            paint=p,
            price_excl_vat=p.price_excl_vat,
            price_incl_vat=p.price_incl_vat,
            metadata=meta or {},
            **li_kwargs,
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        return p, li

    def test_snapshot_immutability_area_fixed_permetre_note(self):
        # AREA_COATING
        p, li = self._create_and_price_line(
            {"name":"A","category":Paint.Category.INTERIOR,"base_type":Paint.BaseType.WHITE,"price_excl_vat":Decimal("1600.00"),"price_incl_vat":Decimal("1840.00"),"spread_rate_per_litre":Decimal("10"),"priced_volume_litres":Decimal("20"),"finish":Paint.Finish.SMOOTH_MATTE},
            {"coats":1, "area_sqm":Decimal("50")},
        )
        snap = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat
        # mutate paint and line prices
        p.price_excl_vat = Decimal("1.00")
        p.price_incl_vat = Decimal("1.15")
        p.save()
        li.price_excl_vat = Decimal("2.00")
        li.price_incl_vat = Decimal("2.30")
        li.save(update_fields=["price_excl_vat","price_incl_vat"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("product_snapshot"), snap)
        self.assertEqual(li.total_excl_vat, orig_total)

        # FIXED_PACK
        p, li = self._create_and_price_line(
            {"name":"F","category":Paint.Category.MOULD,"base_type":Paint.BaseType.NOT_APPLICABLE,"pricing_method":Paint.PricingMethod.FIXED_PACK,"price_excl_vat":Decimal("10.00"),"price_incl_vat":Decimal("11.50"),"package_size":Decimal("1.00"),"package_unit":Paint.PackageUnit.LITRE},
            {"coats":1, "area_sqm":None},
            meta={"package_count":2}
        )
        snap = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat
        p.price_excl_vat = Decimal("999.99")
        p.save()
        li.price_excl_vat = Decimal("1.00")
        li.price_incl_vat = Decimal("1.15")
        li.save(update_fields=["price_excl_vat","price_incl_vat"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("product_snapshot"), snap)
        self.assertEqual(li.total_excl_vat, orig_total)

        # PER_METRE
        p, li = self._create_and_price_line(
            {"name":"P","category":Paint.Category.SANDING,"base_type":Paint.BaseType.NOT_APPLICABLE,"pricing_method":Paint.PricingMethod.PER_METRE,"price_excl_vat":Decimal("20.00"),"price_incl_vat":Decimal("23.00"),"package_unit":Paint.PackageUnit.METRE,"variant_label":"80 grit"},
            {"coats":1, "area_sqm":None},
            meta={"roll_count":2}
        )
        snap = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat
        p.price_excl_vat = Decimal("0.50")
        p.save()
        li.price_excl_vat = Decimal("1.00")
        li.price_incl_vat = Decimal("1.15")
        li.save(update_fields=["price_excl_vat","price_incl_vat"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("product_snapshot"), snap)
        self.assertEqual(li.total_excl_vat, orig_total)

        # NOTE_ONLY
        p, li = self._create_and_price_line(
            {"name":"N","category":Paint.Category.EFFLORESCENCE,"base_type":Paint.BaseType.NOT_APPLICABLE,"pricing_method":Paint.PricingMethod.NOTE_ONLY,"price_excl_vat":Decimal("0.00"),"price_incl_vat":Decimal("0.00"),"predetermined_note":"Care"},
            {"coats":1, "area_sqm":None},
        )
        snap = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat
        p.predetermined_note = "Changed"
        p.save()
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("product_snapshot"), snap)
        self.assertEqual(li.total_excl_vat, orig_total)

    # ---------- Group G: Pending transitions and recovery ----------
    def test_area_fixed_per_recovery_cycle(self):
        # AREA_COATING: price -> remove area -> pending -> restore -> priced
        p = Paint.objects.create(
            name="AR",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("1600.00"),
            price_incl_vat=Decimal("1840.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
            finish=Paint.Finish.SMOOTH_MATTE,
        )
        li = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="AR", paint=p, coats=1, area_sqm=Decimal("50"), price_excl_vat=p.price_excl_vat, price_incl_vat=p.price_incl_vat, metadata={})
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        snap = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat
        orig_required = str(li.metadata.get("required_litres"))
        # remove area
        li.area_sqm = None
        li.save(update_fields=["area_sqm"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "pending")
        # canonical pending required_litres must be present (JSON-safe string),
        # and previous nonzero value must be replaced
        self.assertEqual(li.metadata.get("required_litres"), "0.00")
        self.assertNotEqual(li.metadata.get("required_litres"), orig_required)
        # rate-derived values should be cleared to None on pending
        self.assertIsNone(li.metadata.get("price_per_litre_excl_vat"))
        self.assertIsNone(li.metadata.get("price_per_litre_incl_vat"))
        self.assertIsNone(li.metadata.get("rate_per_sqm_per_coat_excl_vat"))
        self.assertIsNone(li.metadata.get("rate_per_sqm_selected_coats_excl_vat"))
        # line-level fields reflect pending state
        self.assertIsNone(li.quantity)
        self.assertEqual(li.unit, "")
        self.assertEqual(li.total_excl_vat, Decimal("0.00"))
        self.assertEqual(li.total_incl_vat, Decimal("0.00"))
        self.assertEqual(li.metadata.get("pricing_pending_reason"), "missing_area")
        # snapshot must remain authoritative
        self.assertEqual(li.metadata.get("product_snapshot"), snap)
        # restore area
        li.area_sqm = Decimal("50")
        li.save(update_fields=["area_sqm"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "priced")
        self.assertEqual(li.total_excl_vat, orig_total)

        # FIXED_PACK: price -> remove package_count -> pending -> restore -> priced
        p = Paint.objects.create(name="FP", category=Paint.Category.MOULD, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.FIXED_PACK, price_excl_vat=Decimal("10.00"), price_incl_vat=Decimal("11.50"), package_size=Decimal("1.00"), package_unit=Paint.PackageUnit.LITRE)
        li = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="FP", paint=p, price_excl_vat=p.price_excl_vat, price_incl_vat=p.price_incl_vat, metadata={"package_count":2})
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        snap = dict(li.metadata.get("product_snapshot"))
        orig_total = li.total_excl_vat
        li.metadata.pop("package_count", None)
        li.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "pending")
        self.assertIsNone(li.metadata.get("price_per_package_excl_vat"))
        # restore
        li.metadata["package_count"] = 2
        li.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "priced")
        self.assertEqual(li.total_excl_vat, orig_total)

        # PER_METRE: price -> remove roll_count -> pending -> restore -> priced
        p = Paint.objects.create(name="PM", category=Paint.Category.SANDING, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.PER_METRE, price_excl_vat=Decimal("20.00"), price_incl_vat=Decimal("23.00"), package_unit=Paint.PackageUnit.METRE, variant_label="80 grit")
        li = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="PM", paint=p, price_excl_vat=p.price_excl_vat, price_incl_vat=p.price_incl_vat, metadata={"roll_count":2})
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        orig_total = li.total_excl_vat
        li.metadata.pop("roll_count", None)
        li.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "pending")
        self.assertIsNone(li.metadata.get("price_per_metre_excl_vat"))
        # restore
        li.metadata["roll_count"] = 2
        li.save(update_fields=["metadata"])
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "priced")
        self.assertEqual(li.total_excl_vat, orig_total)

    # ---------- Group H: Mixed quotation totals ----------
    def test_mixed_quotation_totals(self):
        # AREA line
        pa = Paint.objects.create(name="M1", category=Paint.Category.INTERIOR, base_type=Paint.BaseType.WHITE, price_excl_vat=Decimal("1600.00"), price_incl_vat=Decimal("1840.00"), spread_rate_per_litre=Decimal("10"), priced_volume_litres=Decimal("20"), finish=Paint.Finish.SMOOTH_MATTE)
        la = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="A", paint=pa, coats=1, area_sqm=Decimal("50"), price_excl_vat=pa.price_excl_vat, price_incl_vat=pa.price_incl_vat, metadata={})
        apply_paint_pricing_to_line_item(la)
        # FIXED_PACK
        pf = Paint.objects.create(name="M2", category=Paint.Category.MOULD, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.FIXED_PACK, price_excl_vat=Decimal("10.00"), price_incl_vat=Decimal("11.50"), package_size=Decimal("1.00"), package_unit=Paint.PackageUnit.LITRE)
        lf = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="F", paint=pf, price_excl_vat=pf.price_excl_vat, price_incl_vat=pf.price_incl_vat, metadata={"package_count":2})
        apply_paint_pricing_to_line_item(lf)
        # PER_METRE
        pm = Paint.objects.create(name="M3", category=Paint.Category.SANDING, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.PER_METRE, price_excl_vat=Decimal("20.00"), price_incl_vat=Decimal("23.00"), package_unit=Paint.PackageUnit.METRE, variant_label="80 grit")
        lm = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="P", paint=pm, price_excl_vat=pm.price_excl_vat, price_incl_vat=pm.price_incl_vat, metadata={"roll_count":1})
        apply_paint_pricing_to_line_item(lm)
        # NOTE_ONLY
        pn = Paint.objects.create(name="Note", category=Paint.Category.EFFLORESCENCE, base_type=Paint.BaseType.NOT_APPLICABLE, pricing_method=Paint.PricingMethod.NOTE_ONLY, price_excl_vat=Decimal("0.00"), price_incl_vat=Decimal("0.00"), predetermined_note="Note it")
        ln = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="N", paint=pn, price_excl_vat=pn.price_excl_vat, price_incl_vat=pn.price_incl_vat, metadata={})
        apply_paint_pricing_to_line_item(ln)
        # Pending zero-total line (no snapshot)
        lp = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="PENDING", paint=None, price_excl_vat=Decimal("0.00"), price_incl_vat=Decimal("0.00"), metadata={})
        apply_paint_pricing_to_line_item(lp)

        # Recalculate
        recalculate_quotation_totals(self.q)
        self.q.refresh_from_db()
        # subtotal should equal sum of line total_excl_vat
        expected = la.total_excl_vat + lf.total_excl_vat + lm.total_excl_vat + ln.total_excl_vat + lp.total_excl_vat
        self.assertEqual(self.q.subtotal_excl_vat, expected.quantize(Decimal("0.01")))

    # ---------- Group I: Caller compatibility ----------
    def test_adapter_saves_and_returns_line_item(self):
        p = Paint.objects.create(name="C1", category=Paint.Category.INTERIOR, base_type=Paint.BaseType.WHITE, price_excl_vat=Decimal("100.00"), price_incl_vat=Decimal("115.00"), spread_rate_per_litre=Decimal("10"), priced_volume_litres=Decimal("1.00"), finish=Paint.Finish.SMOOTH_MATTE)
        li = QuotationLineItem.objects.create(quotation=self.q, section=self.sec, item_type=QuotationLineItem.ItemType.PAINT, description="C", paint=p, coats=1, area_sqm=Decimal("1"), price_excl_vat=p.price_excl_vat, price_incl_vat=p.price_incl_vat, metadata={})
        ret = apply_paint_pricing_to_line_item(li)
        self.assertIsInstance(ret, QuotationLineItem)
        li.refresh_from_db()
        self.assertIn("product_snapshot", li.metadata)
