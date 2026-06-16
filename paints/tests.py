from decimal import Decimal

from django.core.exceptions import ValidationError, FieldDoesNotExist
from django.test import TestCase

from .forms import PaintForm
from .models import Paint


class PaintModelFieldTests(TestCase):
    def _base_paint_kwargs(self):
        return {
            "name": "Test Paint",
            "category": Paint.Category.INTERIOR,
            "base_type": Paint.BaseType.WHITE,
            "finish": Paint.Finish.SMOOTH_MATTE,
            "price_excl_vat": Decimal("10.00"),
            "price_incl_vat": Decimal("11.50"),
        }

    def test_positive_spread_rate_accepted(self):
        p = Paint(**self._base_paint_kwargs(), spread_rate_per_litre=Decimal("10.00"))
        p.full_clean()  # should not raise

    def test_zero_spread_rate_rejected(self):
        p = Paint(**self._base_paint_kwargs(), spread_rate_per_litre=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_negative_spread_rate_rejected(self):
        p = Paint(**self._base_paint_kwargs(), spread_rate_per_litre=Decimal("-1.00"))
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_priced_volume_of_one_accepted(self):
        p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("1.00"), spread_rate_per_litre=Decimal("10.00"))
        p.full_clean()

    def test_priced_volume_greater_than_one_accepted(self):
        p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("4.00"), spread_rate_per_litre=Decimal("10.00"))
        p.full_clean()

    def test_zero_priced_volume_rejected(self):
        p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_negative_priced_volume_rejected(self):
        p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("-2.00"))
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_finish_and_spread_rate_may_be_blank_for_non_area_products(self):
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.CRACKS,
            "pricing_method": Paint.PricingMethod.FIXED_PACK,
            "package_unit": Paint.PackageUnit.KILOGRAM,
            "package_size": Decimal("2.00"),
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
        })
        p = Paint(**kw)
        p.full_clean()

    def test_defaults_to_area_coating_pricing_method(self):
        p = Paint.objects.create(**self._base_paint_kwargs())
        self.assertEqual(p.pricing_method, Paint.PricingMethod.AREA_COATING)

    def test_fixed_pack_cracks_can_store_package_and_unit(self):
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.CRACKS,
            "pricing_method": Paint.PricingMethod.FIXED_PACK,
            "package_size": Decimal("2.00"),
            "package_unit": Paint.PackageUnit.KILOGRAM,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
        })
        p = Paint.objects.create(**kw)
        self.assertEqual(p.category, Paint.Category.CRACKS)
        self.assertEqual(p.package_size, Decimal("2.00"))
        self.assertEqual(p.package_unit, Paint.PackageUnit.KILOGRAM)

    def test_mould_and_cleaning_fixed_packs(self):
        kwm = self._base_paint_kwargs()
        kwm.update({
            "category": Paint.Category.MOULD,
            "pricing_method": Paint.PricingMethod.FIXED_PACK,
            "package_size": Decimal("1.00"),
            "package_unit": Paint.PackageUnit.LITRE,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
        })
        kwc = self._base_paint_kwargs()
        kwc.update({
            "category": Paint.Category.CLEANING,
            "pricing_method": Paint.PricingMethod.FIXED_PACK,
            "package_size": Decimal("5.00"),
            "package_unit": Paint.PackageUnit.LITRE,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
        })
        m = Paint.objects.create(**kwm)
        c = Paint.objects.create(**kwc)
        self.assertEqual(m.package_unit, Paint.PackageUnit.LITRE)
        self.assertEqual(c.package_size, Decimal("5.00"))

    def test_sanding_per_metre_with_variant(self):
        kws = self._base_paint_kwargs()
        kws.update({
            "category": Paint.Category.SANDING,
            "pricing_method": Paint.PricingMethod.PER_METRE,
            "package_unit": Paint.PackageUnit.METRE,
            "variant_label": "80 grit",
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
        })
        s = Paint.objects.create(**kws)
        self.assertEqual(s.pricing_method, Paint.PricingMethod.PER_METRE)
        self.assertEqual(s.package_unit, Paint.PackageUnit.METRE)
        self.assertEqual(s.variant_label, "80 grit")

    def test_note_only_items_store_predetermined_note_and_zero_prices(self):
        kwe = self._base_paint_kwargs()
        kwe.update({
            "category": Paint.Category.EFFLORESCENCE,
            "pricing_method": Paint.PricingMethod.NOTE_ONLY,
            "predetermined_note": "Efflorescence treatment note",
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "price_excl_vat": Decimal("0.00"),
            "price_incl_vat": Decimal("0.00"),
        })
        kwo = self._base_paint_kwargs()
        kwo.update({
            "category": Paint.Category.OLD_PAINT_REMOVAL,
            "pricing_method": Paint.PricingMethod.NOTE_ONLY,
            "predetermined_note": "Old paint removal note",
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "price_excl_vat": Decimal("0.00"),
            "price_incl_vat": Decimal("0.00"),
        })
        e = Paint.objects.create(**kwe)
        o = Paint.objects.create(**kwo)
        self.assertIn("Efflorescence", e.predetermined_note)
        self.assertEqual(e.price_excl_vat, Decimal("0.00"))
        self.assertEqual(o.price_incl_vat, Decimal("0.00"))

    def test_package_size_zero_and_negative_rejected(self):
        p_zero = Paint(**self._base_paint_kwargs(), package_size=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            p_zero.full_clean()

        p_neg = Paint(**self._base_paint_kwargs(), package_size=Decimal("-1.00"))
        with self.assertRaises(ValidationError):
            p_neg.full_clean()

    def test_standard_coats_validation(self):
        # standard_coats is meaningful for primers; ensure validation there
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.PRIMER,
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "spread_rate_per_litre": Decimal("12.00"),
            "priced_volume_litres": Decimal("1.00"),
            "standard_coats": 1,
        })
        p = Paint(**kw)
        p.full_clean()

        kw_bad = dict(kw)
        kw_bad["standard_coats"] = 0
        p_bad = Paint(**kw_bad)
        with self.assertRaises(ValidationError):
            p_bad.full_clean()

    # --- Pack 3B1 model tests moved here ---
    def test_waterproofing_requires_area_and_one_standard_coat(self):
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.WATERPROOFING,
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "spread_rate_per_litre": Decimal("8.50"),
            "priced_volume_litres": Decimal("1.00"),
            "standard_coats": 1,
        })
        p = Paint(**kw)
        p.full_clean()

        # standard_coats other than 1 should be rejected
        kw2 = dict(kw)
        kw2["standard_coats"] = 2
        p2 = Paint(**kw2)
        with self.assertRaises(ValidationError):
            p2.full_clean()

    def test_deco_plast_finish_accepted_for_interior(self):
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.INTERIOR,
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "finish": Paint.Finish.DECO_PLAST,
            "spread_rate_per_litre": Decimal("9.00"),
            "priced_volume_litres": Decimal("1.00"),
        })
        p = Paint(**kw)
        p.full_clean()

    def test_cracks_rejects_unsupported_package_size(self):
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.CRACKS,
            "pricing_method": Paint.PricingMethod.FIXED_PACK,
            "package_size": Decimal("3.00"),
            "package_unit": Paint.PackageUnit.KILOGRAM,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
        })
        p = Paint(**kw)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_sanding_rejects_unknown_variant(self):
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.SANDING,
            "pricing_method": Paint.PricingMethod.PER_METRE,
            "package_unit": Paint.PackageUnit.METRE,
            "variant_label": "120 grit",
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
        })
        p = Paint(**kw)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_interior_exterior_package_unit_must_be_not_applicable(self):
        kw = self._base_paint_kwargs()
        kw.update({
            "category": Paint.Category.INTERIOR,
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "finish": Paint.Finish.SMOOTH_MATTE,
            "spread_rate_per_litre": Decimal("10.00"),
            "priced_volume_litres": Decimal("1.00"),
            "package_unit": Paint.PackageUnit.LITRE,
        })
        p = Paint(**kw)
        with self.assertRaises(ValidationError):
            p.full_clean()


class PaintFormVatTests(TestCase):
    def test_paintform_vat_autocalculate_from_excl(self):
        form = PaintForm(data={
            "name": "Form Paint",
            "category": Paint.Category.INTERIOR,
            "base_type": Paint.BaseType.WHITE,
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": "",
            "priced_volume_litres": "1.00",
            "spread_rate_per_litre": "10.00",
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "finish": Paint.Finish.SMOOTH_MATTE,
        })
        # Verify validity and show errors if present
        self.assertTrue(form.is_valid(), form.errors.as_json())
        # Read the VAT result from cleaned_data (validation already ran)
        cleaned = form.cleaned_data
        # Default VAT is 15% -> 100 * 1.15 = 115.00
        self.assertEqual(cleaned.get("price_incl_vat"), Decimal("115.00"))

    def test_blank_pricing_method_rejected(self):
        form = PaintForm(data={
            "name": "Form Paint",
            "category": Paint.Category.INTERIOR,
            "base_type": Paint.BaseType.WHITE,
            "price_excl_vat": Decimal("50.00"),
            "price_incl_vat": "",
            "priced_volume_litres": "1.00",
            "pricing_method": "",
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "finish": Paint.Finish.SMOOTH_MATTE,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("pricing_method", form.errors)

    def test_blank_package_unit_rejected(self):
        form = PaintForm(data={
            "name": "Form Paint",
            "category": Paint.Category.INTERIOR,
            "base_type": Paint.BaseType.WHITE,
            "price_excl_vat": Decimal("50.00"),
            "price_incl_vat": "",
            "priced_volume_litres": "1.00",
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "package_unit": "",
            "finish": Paint.Finish.SMOOTH_MATTE,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("package_unit", form.errors)

    def test_area_coating_not_applicable_validates(self):
        form = PaintForm(data={
            "name": "Form Paint",
            "category": Paint.Category.INTERIOR,
            "base_type": Paint.BaseType.WHITE,
            "price_excl_vat": Decimal("100.00"),
            "price_incl_vat": "",
            "priced_volume_litres": "1.00",
            "spread_rate_per_litre": "10.00",
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "finish": Paint.Finish.SMOOTH_MATTE,
        })
        self.assertTrue(form.is_valid(), form.errors.as_json())




    def test_paint_type_field_removed(self):
        with self.assertRaises(FieldDoesNotExist):
            Paint._meta.get_field("paint_type")
