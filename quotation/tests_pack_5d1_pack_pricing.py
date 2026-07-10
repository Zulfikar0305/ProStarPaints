from decimal import Decimal

from django.test import SimpleTestCase

from .pricing import calculate_product_pricing


class Pack5D1PackPricingTests(SimpleTestCase):
    def setUp(self):
        # Common snapshot values: price is per-litre (priced_volume_litres=1)
        self.base_snap = {
            "pricing_method": "AREA_COATING",
            "category": "INTERIOR",
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": Decimal("115.00"),
            "priced_volume_litres": Decimal("1.00"),
            "package_size": Decimal("20.00"),
            "package_unit": "L",
        }

    def _run(self, required_litres: Decimal):
        snap = dict(self.base_snap)
        snap["spread_rate_per_litre"] = Decimal("1.00")
        # Area such that required litres == area (coats=1)
        area = required_litres
        res = calculate_product_pricing(snap, area_sqm=area, coats=1)
        return res

    def test_required_2_5L_charges_one_20L(self):
        res = self._run(Decimal("2.5"))
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["unit"], "pack")
        self.assertEqual(res["quantity"], Decimal("1"))
        # price per pack = 20 * 100 = 2000
        self.assertEqual(res["total_excl_vat"], Decimal("2000.00"))
        self.assertEqual(res["total_excl_vat"] + res["vat_amount"], res["total_incl_vat"])

    def test_required_19_9L_charges_one_20L(self):
        res = self._run(Decimal("19.9"))
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["unit"], "pack")
        self.assertEqual(res["quantity"], Decimal("1"))
        self.assertEqual(res["total_excl_vat"], Decimal("2000.00"))

    def test_required_20_1L_charges_two_20L(self):
        res = self._run(Decimal("20.1"))
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["unit"], "pack")
        self.assertEqual(res["quantity"], Decimal("2"))
        self.assertEqual(res["total_excl_vat"], Decimal("4000.00"))

    def test_required_39_5L_charges_two_20L(self):
        res = self._run(Decimal("39.5"))
        self.assertEqual(res["pricing_status"], "priced")
        self.assertEqual(res["unit"], "pack")
        self.assertEqual(res["quantity"], Decimal("2"))
        self.assertEqual(res["total_excl_vat"], Decimal("4000.00"))
