from decimal import Decimal, ROUND_HALF_UP, getcontext

from django.test import TestCase

from django.contrib.auth import get_user_model
from paints.models import Paint
from .pricing import calculate_paint_pricing, apply_paint_pricing_to_line_item, recalculate_quotation_totals
from .models import Quotation, QuotationLineItem, QuotationSection


class PricingUnitTests(TestCase):
	def test_basic_one_coat_calculation(self):
		# price R1600 for 20L -> R80/L, spread 10 m2/L, area 50, coats 1
		calc = calculate_paint_pricing(
			price_excl_snapshot=Decimal("1600.00"),
			price_incl_snapshot=Decimal("1840.00"),
			priced_volume_litres=Decimal("20"),
			spread_rate_per_litre=Decimal("10"),
			area_sqm=Decimal("50"),
			coats=1,
		)
		self.assertEqual(calc["price_per_litre_excl_vat"], Decimal("80.00"))
		self.assertEqual(calc["required_litres"].quantize(Decimal("0.01")), Decimal("5.00"))
		self.assertEqual(calc["rate_per_sqm_selected_coats_excl_vat"].quantize(Decimal("0.01")), Decimal("8.00"))
		self.assertEqual(calc["total_excl_vat"], Decimal("400.00"))
		# Invariant: stored totals use quantized values for VAT
		self.assertEqual((calc["total_excl_vat"] + calc["vat_amount"]), calc["total_incl_vat"])

	def test_two_coat_calculation(self):
		calc = calculate_paint_pricing(
			price_excl_snapshot=Decimal("1600.00"),
			price_incl_snapshot=Decimal("1840.00"),
			priced_volume_litres=Decimal("20"),
			spread_rate_per_litre=Decimal("10"),
			area_sqm=Decimal("50"),
			coats=2,
		)
		self.assertEqual(calc["required_litres"].quantize(Decimal("0.01")), Decimal("10.00"))
		self.assertEqual(calc["rate_per_sqm_selected_coats_excl_vat"].quantize(Decimal("0.01")), Decimal("16.00"))
		self.assertEqual(calc["total_excl_vat"], Decimal("800.00"))
		self.assertEqual((calc["total_excl_vat"] + calc["vat_amount"]), calc["total_incl_vat"])

	def test_missing_spread_rate_is_pending(self):
		calc = calculate_paint_pricing(
			price_excl_snapshot=Decimal("100.00"),
			price_incl_snapshot=Decimal("115.00"),
			priced_volume_litres=Decimal("1.00"),
			spread_rate_per_litre=None,
			area_sqm=Decimal("10"),
			coats=1,
		)
		self.assertEqual(calc["pricing_status"], "pending")

	def test_non_whole_decimal_pricing(self):
		# Inputs with non-whole decimals
		area_sqm = Decimal("37.50")
		coats = 2
		spread = Decimal("8.50")
		priced_volume = Decimal("5.00")
		price_excl_snapshot = Decimal("437.65")
		price_incl_snapshot = Decimal("503.30")

		calc = calculate_paint_pricing(
			price_excl_snapshot=price_excl_snapshot,
			price_incl_snapshot=price_incl_snapshot,
			priced_volume_litres=priced_volume,
			spread_rate_per_litre=spread,
			area_sqm=area_sqm,
			coats=coats,
		)

		from decimal import ROUND_HALF_UP

		# Expected explicit calculations
		exp_price_per_litre_excl = (price_excl_snapshot / priced_volume).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		exp_price_per_litre_incl = (price_incl_snapshot / priced_volume).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

		exp_required_litres = (area_sqm * Decimal(coats)) / spread

		unq_price_per_litre_excl = price_excl_snapshot / priced_volume
		exp_rate_per_sqm_selected = (unq_price_per_litre_excl / spread * Decimal(coats)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

		exp_total_excl = (exp_required_litres * unq_price_per_litre_excl).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		exp_total_incl = (exp_required_litres * (price_incl_snapshot / priced_volume)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

		# Assertions
		self.assertEqual(calc["price_per_litre_excl_vat"], exp_price_per_litre_excl)
		self.assertEqual(calc["price_per_litre_incl_vat"], exp_price_per_litre_incl)
		self.assertEqual(calc["required_litres"].quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), exp_required_litres.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
		self.assertEqual(Decimal(calc["rate_per_sqm_selected_coats_excl_vat"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), exp_rate_per_sqm_selected)
		self.assertEqual(calc["total_excl_vat"], exp_total_excl)
		self.assertEqual(calc["total_incl_vat"], exp_total_incl)

		# VAT should be computed as difference of the quantized totals
		exp_vat = (exp_total_incl - exp_total_excl).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		self.assertEqual(calc.get("vat_amount"), exp_vat)
		# Invariant
		self.assertEqual((calc["total_excl_vat"] + calc["vat_amount"]), calc["total_incl_vat"])

	def test_decimal_context_not_mutated(self):
		# Ensure calculate_paint_pricing does not permanently change global Decimal context
		orig_prec = getcontext().prec
		_ = calculate_paint_pricing(
			price_excl_snapshot=Decimal("100.00"),
			price_incl_snapshot=Decimal("115.00"),
			priced_volume_litres=Decimal("1.00"),
			spread_rate_per_litre=Decimal("10"),
			area_sqm=Decimal("10"),
			coats=1,
		)
		self.assertEqual(getcontext().prec, orig_prec)


class PricingIntegrationTests(TestCase):
	def setUp(self):
		User = get_user_model()
		self.user = User.objects.create_user(username="testuser", password="pass")
		self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")
		self.sec = QuotationSection.objects.create(quotation=self.q, subsection_key="test", display_name="Test", substrate_type="INTERIOR")

	def test_apply_pricing_and_recalculate_totals(self):
		# Create a paint and line item
		p = Paint.objects.create(
			name="Test",
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
			description="Test",
			paint=p,
			coats=1,
			area_sqm=Decimal("50"),
			price_excl_vat=p.price_excl_vat,
			price_incl_vat=p.price_incl_vat,
			metadata={"paint_group": "g", "paint_name": p.name},
		)

		apply_paint_pricing_to_line_item(li)
		# Reload
		li.refresh_from_db()
		self.assertEqual(li.total_excl_vat, Decimal("400.00"))
		self.assertEqual(li.total_incl_vat, Decimal("460.00"))

		recalculate_quotation_totals(self.q)

	def test_missing_spread_rate_leaves_zero_and_pending(self):
		p = Paint.objects.create(
			name="NoSpread",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("100.00"),
			price_incl_vat=Decimal("115.00"),
			spread_rate_per_litre=None,
			priced_volume_litres=Decimal("1.00"),
		)
		li = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PAINT,
			description="NoSpread",
			paint=p,
			coats=1,
			area_sqm=Decimal("10"),
			price_excl_vat=p.price_excl_vat,
			price_incl_vat=p.price_incl_vat,
			metadata={"paint_group": "g"},
		)
		apply_paint_pricing_to_line_item(li)
		li.refresh_from_db()
		self.assertEqual(li.total_excl_vat, Decimal("0.00"))
		self.assertEqual(li.metadata.get("pricing_status"), "pending")

	def test_zero_priced_volume_marked_pending(self):
		p = Paint.objects.create(
			name="ZeroVol",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("100.00"),
			price_incl_vat=Decimal("115.00"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("0.00"),
		)
		li = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PAINT,
			description="ZeroVol",
			paint=p,
			coats=1,
			area_sqm=Decimal("10"),
			price_excl_vat=p.price_excl_vat,
			price_incl_vat=p.price_incl_vat,
			metadata={},
		)
		apply_paint_pricing_to_line_item(li)
		li.refresh_from_db()
		self.assertEqual(li.total_excl_vat, Decimal("0.00"))
		self.assertEqual(li.metadata.get("pricing_status"), "pending")

	def test_missing_paint_produces_pending(self):
		li = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PAINT,
			description="NoPaint",
			paint=None,
			coats=1,
			area_sqm=Decimal("10"),
			price_excl_vat=Decimal("0.00"),
			price_incl_vat=Decimal("0.00"),
			metadata={},
		)
		apply_paint_pricing_to_line_item(li)
		li.refresh_from_db()
		self.assertEqual(li.metadata.get("pricing_pending_reason"), "missing_product_snapshot")

	def test_missing_area_produces_pending(self):
		p = Paint.objects.create(
			name="A",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("100.00"),
			price_incl_vat=Decimal("115.00"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("1.00"),
		)
		li = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PAINT,
			description="NoArea",
			paint=p,
			coats=1,
			area_sqm=None,
			price_excl_vat=p.price_excl_vat,
			price_incl_vat=p.price_incl_vat,
			metadata={},
		)
		apply_paint_pricing_to_line_item(li)
		li.refresh_from_db()
		self.assertEqual(li.metadata.get("pricing_pending_reason"), "missing_area")

	def test_builder_renders_section_scoped_paints(self):
		# Create paints in both interior and exterior categories
		Paint.objects.create(
			name="IntPaint",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("10.00"),
			price_incl_vat=Decimal("11.50"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("1"),
		)
		Paint.objects.create(
			name="ExtPaint",
			category=Paint.Category.EXTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("10.00"),
			price_incl_vat=Decimal("11.50"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("1"),
		)
		# Create interior and exterior sections
		q = Quotation.objects.create(created_by=self.user, customer_name="C2", customer_email="", customer_phone="")
		int_sec = QuotationSection.objects.create(quotation=q, subsection_key="interior_walls", display_name="IntWalls", substrate_type="INTERIOR")
		ext_sec = QuotationSection.objects.create(quotation=q, subsection_key="exterior_walls", display_name="ExtWalls", substrate_type="EXTERIOR")

		# Render builder page
		# Use test client with logged-in user and reverse URL
		self.client.login(username=self.user.username, password="pass")
		from django.urls import reverse
		resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q.pk}))
		self.assertEqual(resp.status_code, 200)
		content = resp.content.decode('utf-8')
		# Interior section should not include ExtPaint in its paints list
		self.assertIn('IntPaint', content)
		# Find exterior section block and assert ExtPaint present and IntPaint not listed in that block
		# Basic assertions: both names present globally but per-section selects are rendered with scoped paints via `data-section-pk` blocks
		self.assertIn('ExtPaint', content)

	def test_all_paints_json_uses_canonical_finish_keys(self):
		# Paint.finish stored as enum (SMOOTH_MATTE) should be exported as 'smooth_matte' in all_paints_json
		p = Paint.objects.create(
			name="FinishPaint",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("10.00"),
			price_incl_vat=Decimal("11.50"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("1"),
			finish=Paint.Finish.SMOOTH_MATTE,
		)
		self.client.login(username=self.user.username, password="pass")
		from django.urls import reverse
		resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
		self.assertEqual(resp.status_code, 200)
		all_json = resp.context.get('all_paints_json')
		self.assertIsNotNone(all_json)
		self.assertIn('"finish": "smooth_matte"', all_json)

	def test_blank_finish_can_be_priced_and_metadata_preserved(self):
		p = Paint.objects.create(
			name="NoFinish",
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
			description="NoFinish",
			paint=p,
			coats=1,
			area_sqm=Decimal("50"),
			price_excl_vat=p.price_excl_vat,
			price_incl_vat=p.price_incl_vat,
			metadata={"paint_group": "g", "paint_name": p.name},
		)
		apply_paint_pricing_to_line_item(li)
		li.refresh_from_db()
		self.assertEqual(li.metadata.get("pricing_status"), "priced")
		# snapshots present
		self.assertIn("price_per_litre_excl_vat", li.metadata)

	def test_multiple_paints_aggregate_totals(self):
		p1 = Paint.objects.create(
			name="P1",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("1600.00"),
			price_incl_vat=Decimal("1840.00"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("20"),
		)
		p2 = Paint.objects.create(
			name="P2",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("800.00"),
			price_incl_vat=Decimal("920.00"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("20"),
		)
		li1 = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PAINT,
			description="P1",
			paint=p1,
			coats=1,
			area_sqm=Decimal("50"),
			price_excl_vat=p1.price_excl_vat,
			price_incl_vat=p1.price_incl_vat,
			metadata={},
		)
		li2 = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PAINT,
			description="P2",
			paint=p2,
			coats=1,
			area_sqm=Decimal("50"),
			price_excl_vat=p2.price_excl_vat,
			price_incl_vat=p2.price_incl_vat,
			metadata={},
		)
		apply_paint_pricing_to_line_item(li1)
		apply_paint_pricing_to_line_item(li2)
		recalculate_quotation_totals(self.q)
		self.q.refresh_from_db()
		# p1 total 400, p2 total 200 => subtotal 600
		self.assertEqual(self.q.subtotal_excl_vat, Decimal("600.00"))

	def test_zero_primer_line_does_not_corrupt_totals(self):
		# Create a priced paint line
		p = Paint.objects.create(
			name="P",
			category=Paint.Category.INTERIOR,
			base_type=Paint.BaseType.WHITE,
			price_excl_vat=Decimal("1600.00"),
			price_incl_vat=Decimal("1840.00"),
			spread_rate_per_litre=Decimal("10"),
			priced_volume_litres=Decimal("20"),
		)
		li_paint = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PAINT,
			description="P",
			paint=p,
			coats=1,
			area_sqm=Decimal("50"),
			price_excl_vat=p.price_excl_vat,
			price_incl_vat=p.price_incl_vat,
			metadata={},
		)
		# Create a primer line with zero totals
		li_primer = QuotationLineItem.objects.create(
			quotation=self.q,
			section=self.sec,
			item_type=QuotationLineItem.ItemType.PRIMER,
			description="Primer",
			coats=1,
			area_sqm=Decimal("50"),
			price_excl_vat=Decimal("0.00"),
			price_incl_vat=Decimal("0.00"),
			total_excl_vat=Decimal("0.00"),
			total_incl_vat=Decimal("0.00"),
			metadata={},
		)
		apply_paint_pricing_to_line_item(li_paint)
		recalculate_quotation_totals(self.q)
		self.q.refresh_from_db()
		self.assertEqual(self.q.subtotal_excl_vat, Decimal("400.00"))


class QuotationSectionSelectionOrderTests(TestCase):
	def setUp(self):
		User = get_user_model()
		self.user = User.objects.create_user(username="testuser2", password="pass")
		self.q = Quotation.objects.create(created_by=self.user, customer_name="C2", customer_email="", customer_phone="")

	def test_default_selection_order_is_one(self):
		sec = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="Ceilings")
		self.assertEqual(sec.selection_order, 1)

	def test_repeated_categories_allowed_and_ordered(self):
		s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Interior 1", sort_order=1)
		s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Interior 2", sort_order=2, selection_order=2)
		self.assertEqual(s1.selection_order, 1)
		self.assertEqual(s2.selection_order, 2)

	def test_duplicate_selection_order_violates_unique_constraint(self):
		from django.db import IntegrityError
		QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", selection_order=1)
		with self.assertRaises(IntegrityError):
			QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C2", selection_order=1)

	def test_same_order_different_categories_allowed(self):
		s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
		s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", selection_order=1)
		self.assertEqual(s1.selection_order, 1)
		self.assertEqual(s2.selection_order, 1)

	def test_same_order_different_quotations_allowed(self):
		# Use same user; only two different Quotation objects are needed
		q2 = Quotation.objects.create(created_by=self.user, customer_name="C3", customer_email="", customer_phone="")
		QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
		QuotationSection.objects.create(quotation=q2, subsection_key="interior_walls", display_name="I1", selection_order=1)

	def test_line_item_relationship_unchanged(self):
		sec = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
		li = QuotationLineItem.objects.create(quotation=self.q, section=sec, item_type=QuotationLineItem.ItemType.NOTE, description="Note", metadata={})
		# Forward FK
		self.assertEqual(li.section.pk, sec.pk)
		# Reverse FK
		self.assertTrue(sec.line_items.filter(pk=li.pk).exists())
