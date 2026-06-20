from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from paints.models import Paint
from .models import Quotation, QuotationSection, QuotationLineItem
from .pricing import apply_paint_pricing_to_line_item, recalculate_quotation_totals
from .config import PRIMER_OPTIONS, WATERPROOFING_OPTIONS, OTHER_PREP_OPTIONS


class Pack5C3PricingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="p5c3", password="pass")
        self.client.login(username="p5c3", password="pass")

        # Create a quotation and section
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")
        self.sec = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="Ceilings", substrate_type="INTERIOR")

        # Representative products for mapping
        # Primer
        self.primer = Paint.objects.create(
            name="4/1 Plaster Primerseal",
            category=Paint.Category.PRIMER,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            finish=Paint.Finish.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.AREA_COATING,
            spread_rate_per_litre=Decimal("8.00"),
            priced_volume_litres=Decimal("1.00"),
            standard_coats=1,
            price_excl_vat=Decimal("5.00"),
            price_incl_vat=Decimal("5.75"),
        )

        # Waterproofing
        self.wp = Paint.objects.create(
            name="Hydro Shield",
            category=Paint.Category.WATERPROOFING,
            base_type=Paint.BaseType.NOT_APPLICABLE,
            finish=Paint.Finish.NOT_APPLICABLE,
            pricing_method=Paint.PricingMethod.AREA_COATING,
            spread_rate_per_litre=Decimal("6.00"),
            priced_volume_litres=Decimal("1.00"),
            standard_coats=1,
            price_excl_vat=Decimal("10.00"),
            price_incl_vat=Decimal("11.50"),
        )

        # Prep: filling -> cracks (fixed pack)
        self.crack = Paint.objects.create(
            name="Crack Filler",
            category=Paint.Category.CRACKS,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.KILOGRAM,
            package_size=Decimal("2.00"),
            price_excl_vat=Decimal("20.00"),
            price_incl_vat=Decimal("23.00"),
        )

        # Prep: mould_treatment -> mould (fixed pack)
        self.mould = Paint.objects.create(
            name="Mould Treatment",
            category=Paint.Category.MOULD,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.LITRE,
            package_size=Decimal("1.00"),
            price_excl_vat=Decimal("3.00"),
            price_incl_vat=Decimal("3.45"),
        )

        # Prep: efflor_removal -> efflorescence (note-only)
        self.eff = Paint.objects.create(
            name="Efflorescence Remediation",
            category=Paint.Category.EFFLORESCENCE,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            price_excl_vat=Decimal("0.00"),
            price_incl_vat=Decimal("0.00"),
            predetermined_note="Efflorescence treatment",
        )

        # Prep: cleaning -> cleaning (fixed pack)
        self.clean = Paint.objects.create(
            name="Surface Cleaner",
            category=Paint.Category.CLEANING,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.LITRE,
            package_size=Decimal("1.00"),
            price_excl_vat=Decimal("2.00"),
            price_incl_vat=Decimal("2.30"),
        )

        # Prep: sanding -> sanding (per metre)
        self.sand = Paint.objects.create(
            name="Sanding Paper 80 grit",
            category=Paint.Category.SANDING,
            pricing_method=Paint.PricingMethod.PER_METRE,
            package_unit=Paint.PackageUnit.METRE,
            variant_label="80 grit",
            price_excl_vat=Decimal("0.50"),
            price_incl_vat=Decimal("0.58"),
        )

        # Prep: remove_paint -> old paint removal (note-only)
        self.remove = Paint.objects.create(
            name="Old Paint Removal",
            category=Paint.Category.OLD_PAINT_REMOVAL,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            price_excl_vat=Decimal("0.00"),
            price_incl_vat=Decimal("0.00"),
            predetermined_note="Strip and remove old paint",
        )

    def test_primer_pricing_applies(self):
        # Create primer line via view-like API (simulate save behavior)
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PRIMER,
            description=self.primer.name,
            paint=self.primer,
            coats=1,
            area_sqm=Decimal("10.00"),
            price_excl_vat=self.primer.price_excl_vat,
            price_incl_vat=self.primer.price_incl_vat,
            metadata={"key": 'plaster_primerseal'},
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "priced")
        self.assertGreater(li.total_excl_vat, Decimal("0.00"))

    def test_waterproofing_pricing_applies(self):
        li = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.WATERPROOFING,
            description=self.wp.name,
            paint=self.wp,
            coats=1,
            area_sqm=Decimal("5.00"),
            price_excl_vat=self.wp.price_excl_vat,
            price_incl_vat=self.wp.price_incl_vat,
            metadata={"key": 'hydro_shield'},
        )
        apply_paint_pricing_to_line_item(li)
        li.refresh_from_db()
        self.assertEqual(li.metadata.get("pricing_status"), "priced")
        self.assertGreater(li.total_excl_vat, Decimal("0.00"))

    def test_prep_work_options_priced(self):
        # filling -> Crack filler (fixed pack)
        li1 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description=self.crack.name,
            paint=self.crack,
            metadata={"key": 'filling', "package_count": 2},
            price_excl_vat=self.crack.price_excl_vat,
            price_incl_vat=self.crack.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li1)
        li1.refresh_from_db()
        self.assertEqual(li1.metadata.get("pricing_status"), "priced")
        self.assertGreater(li1.total_excl_vat, Decimal("0.00"))

        # mould_treatment -> mould (fixed pack)
        li2 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description=self.mould.name,
            paint=self.mould,
            metadata={"key": 'mould_treatment', "package_count": 1},
            price_excl_vat=self.mould.price_excl_vat,
            price_incl_vat=self.mould.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li2)
        li2.refresh_from_db()
        self.assertEqual(li2.metadata.get("pricing_status"), "priced")

        # efflor_removal -> note-only
        li3 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description=self.eff.name,
            paint=self.eff,
            metadata={"key": 'efflor_removal'},
            price_excl_vat=self.eff.price_excl_vat,
            price_incl_vat=self.eff.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li3)
        li3.refresh_from_db()
        self.assertEqual(li3.metadata.get("pricing_status"), "priced")

        # cleaning -> fixed pack
        li4 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description=self.clean.name,
            paint=self.clean,
            metadata={"key": 'cleaning', "package_count": 1},
            price_excl_vat=self.clean.price_excl_vat,
            price_incl_vat=self.clean.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li4)
        li4.refresh_from_db()
        self.assertEqual(li4.metadata.get("pricing_status"), "priced")

        # sanding -> per metre
        li5 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description=self.sand.name,
            paint=self.sand,
            metadata={"key": 'sanding', "roll_count": 3},
            price_excl_vat=self.sand.price_excl_vat,
            price_incl_vat=self.sand.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li5)
        li5.refresh_from_db()
        self.assertEqual(li5.metadata.get("pricing_status"), "priced")

        # remove_paint -> note-only
        li6 = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description=self.remove.name,
            paint=self.remove,
            metadata={"key": 'remove_paint'},
            price_excl_vat=self.remove.price_excl_vat,
            price_incl_vat=self.remove.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li6)
        li6.refresh_from_db()
        self.assertEqual(li6.metadata.get("pricing_status"), "priced")

    def test_mixed_quotation_totals_and_vat(self):
        # Paint row (area-based)
        paint = Paint.objects.create(
            name="Interior X",
            category=Paint.Category.INTERIOR,
            pricing_method=Paint.PricingMethod.AREA_COATING,
            spread_rate_per_litre=Decimal("10.00"),
            priced_volume_litres=Decimal("1.00"),
            price_excl_vat=Decimal("50.00"),
            price_incl_vat=Decimal("57.50"),
            finish=Paint.Finish.SMOOTH_MATTE,
            base_type=Paint.BaseType.WHITE,
        )
        li_p = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PAINT,
            description=paint.name,
            paint=paint,
            coats=1,
            area_sqm=Decimal("20.00"),
            price_excl_vat=paint.price_excl_vat,
            price_incl_vat=paint.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li_p)

        # Primer
        li_pr = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PRIMER,
            description=self.primer.name,
            paint=self.primer,
            coats=1,
            area_sqm=Decimal("20.00"),
            price_excl_vat=self.primer.price_excl_vat,
            price_incl_vat=self.primer.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li_pr)

        # Waterproof
        li_wp = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.WATERPROOFING,
            description=self.wp.name,
            paint=self.wp,
            coats=1,
            area_sqm=Decimal("20.00"),
            price_excl_vat=self.wp.price_excl_vat,
            price_incl_vat=self.wp.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li_wp)

        # Prep cleaning (1 pack)
        li_clean = QuotationLineItem.objects.create(
            quotation=self.q,
            section=self.sec,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description=self.clean.name,
            paint=self.clean,
            metadata={"package_count": 1},
            price_excl_vat=self.clean.price_excl_vat,
            price_incl_vat=self.clean.price_incl_vat,
        )
        apply_paint_pricing_to_line_item(li_clean)

        # Recalculate totals
        recalculate_quotation_totals(self.q)
        self.q.refresh_from_db()

        # Validate subtotal, VAT, grand total invariant
        self.assertGreaterEqual(self.q.subtotal_excl_vat, Decimal("0.00"))
        self.assertGreaterEqual(self.q.vat_amount, Decimal("0.00"))
        self.assertEqual(self.q.total_incl_vat, (self.q.subtotal_excl_vat + self.q.vat_amount))

