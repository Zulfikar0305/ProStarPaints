from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from django.conf import settings

import pathlib

from .forms import PaintForm
from .models import Paint


class Pack3B2Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", email="admin@example.com", password="pass")
        self.client.force_login(self.admin)

        # Create representative paints for category-aware rendering
        self.interior = Paint.objects.create(
            name="Interior A",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            finish=Paint.Finish.SMOOTH_MATTE,
            pricing_method=Paint.PricingMethod.AREA_COATING,
            package_unit=Paint.PackageUnit.NOT_APPLICABLE,
            spread_rate_per_litre=Decimal("10.00"),
            priced_volume_litres=Decimal("1.00"),
            price_excl_vat=Decimal("10.00"),
            price_incl_vat=Decimal("11.50"),
        )

        self.primer = Paint.objects.create(
            name="Primer A",
            category=Paint.Category.PRIMER,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            finish=Paint.Finish.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.AREA_COATING,
            package_unit=Paint.PackageUnit.NOT_APPLICABLE,
            spread_rate_per_litre=Decimal("8.00"),
            priced_volume_litres=Decimal("1.00"),
            standard_coats=1,
            price_excl_vat=Decimal("5.00"),
            price_incl_vat=Decimal("5.75"),
        )

        self.cracks = Paint.objects.create(
            name="Crack Filler",
            category=Paint.Category.CRACKS,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.KILOGRAM,
            package_size=Decimal("2.00"),
            finish=Paint.Finish.NOT_APPLICABLE,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            price_excl_vat=Decimal("20.00"),
            price_incl_vat=Decimal("23.00"),
        )

        self.mould = Paint.objects.create(
            name="Mould Cleaner",
            category=Paint.Category.MOULD,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.LITRE,
            package_size=Decimal("1.00"),
            finish=Paint.Finish.NOT_APPLICABLE,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            price_excl_vat=Decimal("3.00"),
            price_incl_vat=Decimal("3.45"),
        )

        self.sanding = Paint.objects.create(
            name="Sanding Paper",
            category=Paint.Category.SANDING,
            pricing_method=Paint.PricingMethod.PER_METRE,
            package_unit=Paint.PackageUnit.METRE,
            variant_label="80 grit",
            finish=Paint.Finish.NOT_APPLICABLE,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            price_excl_vat=Decimal("0.50"),
            price_incl_vat=Decimal("0.58"),
        )

        self.noteonly = Paint.objects.create(
            name="Efflorescence",
            category=Paint.Category.EFFLORESCENCE,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            package_unit=Paint.PackageUnit.NOT_APPLICABLE,
            predetermined_note="Special treatment",
            finish=Paint.Finish.NOT_APPLICABLE,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            price_excl_vat=Decimal("0.00"),
            price_incl_vat=Decimal("0.00"),
        )

    def test_product_list_heading(self):
        resp = self.client.get(reverse("paints:paint_list"))
        self.assertContains(resp, "Products & Pricing")

    def test_create_page_contains_add_product(self):
        resp = self.client.get(reverse("paints:paint_create"))
        self.assertContains(resp, "Add Product")

    def test_edit_page_contains_edit_product(self):
        resp = self.client.get(reverse("paints:paint_update", kwargs={"pk": self.interior.pk}))
        self.assertContains(resp, "Edit Product")

    def test_rendered_form_does_not_contain_paint_type(self):
        resp = self.client.get(reverse("paints:paint_create"))
        self.assertNotContains(resp, "Paint Type")

    def test_product_list_shows_pricing_method_and_details(self):
        resp = self.client.get(reverse("paints:paint_list"))
        # Pricing method labels
        self.assertContains(resp, "Area-based coating")
        self.assertContains(resp, "Fixed package")
        # Interior details
        self.assertContains(resp, "Smooth Matte")
        self.assertContains(resp, "White")
        self.assertContains(resp, "10.00")
        # Primer details include one coat
        self.assertContains(resp, "1 coat")
        # Crack details (kg)
        self.assertContains(resp, "2.00 kg")
        # Mould details (L)
        self.assertContains(resp, "1.00 L")
        # Sanding details
        self.assertContains(resp, "80 grit")
        self.assertContains(resp, "per metre")
        # Note-only details
        self.assertContains(resp, "Note-only")

    def test_pricing_page_displays_category_aware_details(self):
        resp = self.client.get(reverse("paints:paint_pricing"))
        self.assertContains(resp, "Area-based coating")
        self.assertContains(resp, "Smooth Matte")
        self.assertContains(resp, "1 coat")
        self.assertContains(resp, "2.00 kg")
        self.assertContains(resp, "80 grit")
        self.assertContains(resp, "Note-only")

    def test_primer_form_normalizes_standard_coats_and_accepts_values(self):
        data = {
            "name": "Primer Form",
            "category": Paint.Category.PRIMER,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "spread_rate_per_litre": "8.00",
            "priced_volume_litres": "1.00",
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "price_excl_vat": "5.00",
            "price_incl_vat": "",
        }
        form = PaintForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        cleaned = form.cleaned_data
        self.assertEqual(cleaned.get("pricing_method"), Paint.PricingMethod.AREA_COATING)
        self.assertEqual(cleaned.get("finish"), Paint.Finish.NOT_APPLICABLE)
        self.assertEqual(cleaned.get("base_type"), Paint.BaseType.NOT_APPLICABLE)
        self.assertEqual(cleaned.get("package_unit"), Paint.PackageUnit.NOT_APPLICABLE)
        self.assertEqual(cleaned.get("standard_coats"), 1)

    def test_waterproofing_normalization_same_as_primer(self):
        data = {
            "name": "Waterproof Form",
            "category": Paint.Category.WATERPROOFING,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "spread_rate_per_litre": "8.00",
            "priced_volume_litres": "1.00",
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "price_excl_vat": "6.00",
            "price_incl_vat": "",
        }
        form = PaintForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        cleaned = form.cleaned_data
        self.assertEqual(cleaned.get("standard_coats"), 1)

    def test_note_only_submission_stores_note_and_zero_prices(self):
        data = {
            "name": "Note Product",
            "category": Paint.Category.EFFLORESCENCE,
            "pricing_method": Paint.PricingMethod.NOTE_ONLY,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "predetermined_note": "Special treatment required",
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "price_excl_vat": "0.00",
            "price_incl_vat": "0.00",
        }
        resp = self.client.post(reverse("paints:paint_create"), data)
        # Redirect on success
        self.assertEqual(resp.status_code, 302)
        obj = Paint.objects.get(name="Note Product")
        self.assertEqual(obj.pricing_method, Paint.PricingMethod.NOTE_ONLY)
        self.assertEqual(obj.price_excl_vat, Decimal("0.00"))
        self.assertEqual(obj.price_incl_vat, Decimal("0.00"))
        self.assertIn("Special treatment", obj.predetermined_note)

    def test_vat_auto_calculation_on_create(self):
        data = {
            "name": "VAT Test",
            "category": Paint.Category.INTERIOR,
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "package_unit": Paint.PackageUnit.NOT_APPLICABLE,
            "finish": Paint.Finish.SMOOTH_MATTE,
            "base_type": Paint.BaseType.WHITE,
            "spread_rate_per_litre": "10.00",
            "priced_volume_litres": "1.00",
            "price_excl_vat": "100.00",
            "price_incl_vat": "",
        }
        resp = self.client.post(reverse("paints:paint_create"), data)
        self.assertEqual(resp.status_code, 302)
        obj = Paint.objects.get(name="VAT Test")
        # Default VAT 15% -> 115.00
        self.assertEqual(obj.price_incl_vat, Decimal("115.00"))

    def test_invalid_category_combination_rejected(self):
        # Primer with litre package unit is invalid
        data = {
            "name": "Invalid Primer",
            "category": Paint.Category.PRIMER,
            "pricing_method": Paint.PricingMethod.AREA_COATING,
            "package_unit": Paint.PackageUnit.LITRE,
            "finish": Paint.Finish.NOT_APPLICABLE,
            "base_type": Paint.BaseType.NOT_APPLICABLE,
            "spread_rate_per_litre": "8.00",
            "priced_volume_litres": "1.00",
            "price_excl_vat": "5.00",
            "price_incl_vat": "",
        }
        form = PaintForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("package_unit", form.errors)

    def test_package_size_options_present_in_js(self):
        """Ensure the front-end JS exposes the expected package-size mappings."""
        # Resolve from the project's BASE_DIR to find the static assets
        js_path = pathlib.Path(settings.BASE_DIR) / 'static' / 'js' / 'product_form.js'
        self.assertTrue(js_path.exists(), f"product_form.js not found at {js_path}")
        content = js_path.read_text()
        # CRACKS should offer 2.00, 5.00, 10.00 with kg labels
        self.assertIn("['2.00','5.00','10.00']", content)
        self.assertIn("kg", content)
        # MOULD / CLEANING should offer 1.00 and 5.00 with L labels
        self.assertIn("['1.00','5.00']", content)
        self.assertIn("v+' L'", content)