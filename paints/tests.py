from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from .forms import PaintForm
from .models import Paint


class PaintModelFieldTests(TestCase):
	def _base_paint_kwargs(self):
		return {
			"name": "Test Paint",
			"category": Paint.Category.INTERIOR,
			"paint_type": Paint.PaintType.WATER_BASED,
			"base_type": Paint.BaseType.WHITE,
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
		p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("1.00"))
		p.full_clean()

	def test_priced_volume_greater_than_one_accepted(self):
		p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("4.00"))
		p.full_clean()

	def test_zero_priced_volume_rejected(self):
		p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("0.00"))
		with self.assertRaises(ValidationError):
			p.full_clean()

	def test_negative_priced_volume_rejected(self):
		p = Paint(**self._base_paint_kwargs(), priced_volume_litres=Decimal("-2.00"))
		with self.assertRaises(ValidationError):
			p.full_clean()

	def test_finish_and_spread_rate_may_be_blank(self):
		p = Paint(**self._base_paint_kwargs(), finish=None, spread_rate_per_litre=None)
		p.full_clean()


class PaintFormVatTests(TestCase):
	def test_paintform_vat_autocalculate_from_excl(self):
		form = PaintForm(data={
			"name": "Form Paint",
			"category": Paint.Category.INTERIOR,
			"paint_type": Paint.PaintType.WATER_BASED,
			"base_type": Paint.BaseType.WHITE,
			"price_excl_vat": Decimal("100.00"),
			"price_incl_vat": "",
			"priced_volume_litres": "1.00",
		})
		# Verify validity and show errors if present
		self.assertTrue(form.is_valid(), form.errors.as_json())
		# Read the VAT result from cleaned_data (validation already ran)
		cleaned = form.cleaned_data
		# Default VAT is 15% -> 100 * 1.15 = 115.00
		self.assertEqual(cleaned.get("price_incl_vat"), Decimal("115.00"))
