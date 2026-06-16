from decimal import Decimal, getcontext

from django.test import SimpleTestCase

from .pricing import (
    calculate_product_pricing,
    calculate_paint_pricing,
)


class PricingDispatcherUnitTests(SimpleTestCase):
    def test_area_coating_delegates_and_preserves_keys(self):
        snap = {
            "pk": None,
            "pricing_method": "AREA_COATING",
            "category": "INTERIOR",
            "price_excl_vat": Decimal("1600.00"),
            "price_incl_vat": Decimal("1840.00"),
            "priced_volume_litres": Decimal("20"),
            "spread_rate_per_litre": Decimal("10"),
        }
        res = calculate_product_pricing(snap, area_sqm=Decimal("50"), coats=1)
        # Common keys
        for k in ("pricing_method", "pricing_status", "quantity", "unit", "total_excl_vat", "total_incl_vat", "vat_amount", "metadata"):
            self.assertIn(k, res)
        # Area-specific keys preserved in extras
        self.assertIn("price_per_litre_excl_vat", res)
        self.assertEqual(res["unit"], "L")
        self.assertEqual(res["pricing_method"], "AREA_COATING")
        # VAT invariant
        self.assertEqual(res["total_excl_vat"] + res["vat_amount"], res["total_incl_vat"])

    def test_dispatcher_does_not_mutate_snapshot_or_decimal_context(self):
        snap = {
            "pk": 1,
            "pricing_method": "PER_METRE",
            "category": "SANDING",
            "price_excl_vat": Decimal("50.00"),
            "price_incl_vat": Decimal("57.50"),
            "variant_label": "80 grit",
        }
        orig_ctx = getcontext().prec
        snap_copy = dict(snap)
        _ = calculate_product_pricing(snap, roll_count=2)
        self.assertEqual(getcontext().prec, orig_ctx)
        self.assertEqual(snap, snap_copy)

    def test_unknown_method_returns_unsupported(self):
        snap = {"pricing_method": "UNKNOWN"}
        res = calculate_product_pricing(snap)
        self.assertEqual(res["pricing_status"], "pending")
        self.assertEqual(res["pricing_pending_reason"], "unsupported_pricing_method")


class FixedPackTests(SimpleTestCase):
    def test_single_package(self):
        snap = {
            "pricing_method": "FIXED_PACK",
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": Decimal("115.00"),
            "package_size": Decimal("2.00"),
            "package_unit": "kg",
        }
        res = calculate_product_pricing(snap, package_count=3)
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["quantity"], Decimal("3"))
        self.assertEqual(res["unit"], "pack")
        self.assertEqual(res["total_excl_vat"], Decimal("300.00"))
        self.assertEqual(res["total_excl_vat"] + res["vat_amount"], res["total_incl_vat"])

    def test_missing_package_count(self):
        snap = {"pricing_method": "FIXED_PACK", "price_excl_vat": Decimal("10.00"), "price_incl_vat": Decimal("11.50")}
        res = calculate_product_pricing(snap)
        self.assertEqual(res["pricing_pending_reason"], "missing_package_count")

    def test_fractional_package_rejected(self):
        snap = {"pricing_method": "FIXED_PACK", "price_excl_vat": Decimal("10.00"), "price_incl_vat": Decimal("11.50")}
        res = calculate_product_pricing(snap, package_count=1.5)
        self.assertEqual(res["pricing_pending_reason"], "invalid_package_count")


class PerMetreTests(SimpleTestCase):
    def test_single_roll(self):
        snap = {"pricing_method": "PER_METRE", "price_excl_vat": Decimal("20.00"), "price_incl_vat": Decimal("23.00"), "variant_label": "80 grit"}
        res = calculate_product_pricing(snap, roll_count=2)
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["quantity"], Decimal("2"))
        self.assertEqual(res["unit"], "m")
        self.assertEqual(res["total_excl_vat"], Decimal("40.00"))
        self.assertEqual(res["total_excl_vat"] + res["vat_amount"], res["total_incl_vat"])

    def test_missing_roll_count(self):
        snap = {"pricing_method": "PER_METRE", "price_excl_vat": Decimal("20.00"), "price_incl_vat": Decimal("23.00"), "variant_label": "80 grit"}
        res = calculate_product_pricing(snap)
        self.assertEqual(res["pricing_pending_reason"], "missing_roll_count")

    def test_fractional_roll_rejected(self):
        snap = {"pricing_method": "PER_METRE", "price_excl_vat": Decimal("20.00"), "price_incl_vat": Decimal("23.00"), "variant_label": "80 grit"}
        res = calculate_product_pricing(snap, roll_count=1.5)
        self.assertEqual(res["pricing_pending_reason"], "invalid_roll_count")


class NoteOnlyTests(SimpleTestCase):
    def test_valid_note_priced(self):
        snap = {"pricing_method": "NOTE_ONLY", "predetermined_note": "Treat area"}
        res = calculate_product_pricing(snap)
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["total_excl_vat"], Decimal("0.00"))
        self.assertEqual(res["total_incl_vat"], Decimal("0.00"))
        self.assertEqual(res["vat_amount"], Decimal("0.00"))
        self.assertEqual(res["quantity"], None)
        self.assertEqual(res["unit"], "")

    def test_blank_note_pending(self):
        snap = {"pricing_method": "NOTE_ONLY", "predetermined_note": "   "}
        res = calculate_product_pricing(snap)
        self.assertEqual(res["pricing_pending_reason"], "missing_predetermined_note")
        