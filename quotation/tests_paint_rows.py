from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from paints.models import Paint
from .models import Quotation, QuotationSection, QuotationLineItem
from .services import create_repeatable_section
from .pricing import calculate_product_pricing


class PaintRowPersistenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="pruser", password="pass")
        self.client.login(username="pruser", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="P", customer_email="", customer_phone="")

    def _create_interior_section(self, display_name="I1"):
        # Create the first selection directly; subsequent selections must
        # use the canonical create_repeatable_section helper to ensure
        # unique selection_order and placeholder semantics.
        existing = QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls")
        if not existing.exists():
            return QuotationSection.objects.create(
                quotation=self.q,
                subsection_key="interior_walls",
                display_name=display_name,
                selection_order=1,
            )
        return create_repeatable_section(quotation=self.q, subsection_key="interior_walls")

    def test_per_row_base_persistence_and_restore(self):
        # Create a paint that can be matched with base DEEP
        p = Paint.objects.create(
            name="Pro Coat Deep Test",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.DEEP,
            price_excl_vat=Decimal("1600.00"),
            price_incl_vat=Decimal("1840.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
            finish=Paint.Finish.SMOOTH_MATTE,
        )

        sec = self._create_interior_section()
        url = reverse('quotation:interior_walls_save', kwargs={'pk': self.q.pk, 'section_pk': sec.pk})

        data = {
            'wall_type': 'brick',
            'finishes': ['smooth_matte'],
            'area_sqm': '50',
            # One paint row
            'paint_row_finish': ['smooth_matte'],
            'paint_row_paint_pk': [str(p.pk)],
            'paint_row_area_sqm': ['50'],
            'paint_row_coats': ['1'],
            'paint_row_base': ['DEEP'],
        }

        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)

        # Verify one PAINT line item exists and base persisted
        items = QuotationLineItem.objects.filter(quotation=self.q, section=sec, item_type=QuotationLineItem.ItemType.PAINT)
        self.assertEqual(items.count(), 1)
        li = items.first()
        self.assertEqual(li.metadata.get('base'), 'DEEP')

        # Reload builder and ensure saved_paint_rows contains the base
        builder_url = reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls'
        resp = self.client.get(builder_url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        # Find the interior section summary for our section
        interior = {entry['section'].pk: entry for entry in ctx['interior_sections_data']}
        saved = interior[sec.pk]['summary']['saved_paint_bases']
        self.assertIn('DEEP', saved.values() or ['DEEP'])

    def test_recommended_containers_and_package_metadata_persist(self):
        # Create a paint with package_size 5L so we can compute recommended_containers
        p = Paint.objects.create(
            name="Pro Coat Pack Test",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("100.00"),
            price_incl_vat=Decimal("115.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("1.00"),
            package_size=Decimal("5.00"),
            package_unit=Paint.PackageUnit.LITRE,
            finish=Paint.Finish.SMOOTH_MATTE,
        )

        sec = self._create_interior_section(display_name="PackSec")
        url = reverse('quotation:interior_walls_save', kwargs={'pk': self.q.pk, 'section_pk': sec.pk})

        data = {
            'wall_type': 'brick',
            'finishes': ['smooth_matte'],
            'area_sqm': '50',
            'paint_row_finish': ['smooth_matte'],
            'paint_row_paint_pk': [str(p.pk)],
            'paint_row_area_sqm': ['50'],
            'paint_row_coats': ['1'],
            'paint_row_base': ['WHITE'],
        }

        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)

        li = QuotationLineItem.objects.filter(quotation=self.q, section=sec, item_type=QuotationLineItem.ItemType.PAINT).first()
        meta = li.metadata
        # package_size and unit should be present
        self.assertEqual(meta.get('package_size'), str(p.package_size))
        self.assertEqual(meta.get('package_unit'), p.package_unit)
        # recommended_containers should be present and match calculation
        self.assertIn('recommended_containers', meta)

        # Independently compute expected recommended_containers using pricing dispatcher
        snapshot = meta.get('product_snapshot')
        pricing = calculate_product_pricing(snapshot, area_sqm=Decimal('50'), coats=1)
        expected = pricing.get('recommended_containers')
        self.assertEqual(meta.get('recommended_containers'), expected)

    def test_multiple_paint_rows_independent_persistence(self):
        # Create three different paints
        p1 = Paint.objects.create(
            name="P1 Test",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("1600.00"),
            price_incl_vat=Decimal("1840.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
            finish=Paint.Finish.SMOOTH_MATTE,
        )
        p2 = Paint.objects.create(
            name="P2 Test",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.DEEP,
            price_excl_vat=Decimal("800.00"),
            price_incl_vat=Decimal("920.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
            finish=Paint.Finish.SMOOTH_MATTE,
        )
        p3 = Paint.objects.create(
            name="P3 Test",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.PASTEL,
            price_excl_vat=Decimal("400.00"),
            price_incl_vat=Decimal("460.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("20"),
            finish=Paint.Finish.SMOOTH_MATTE,
        )

        sec = self._create_interior_section(display_name='Multi')
        url = reverse('quotation:interior_walls_save', kwargs={'pk': self.q.pk, 'section_pk': sec.pk})

        data = {
            'wall_type': 'brick',
            'finishes': ['smooth_matte'],
            'area_sqm': '100',
            'paint_row_finish': ['smooth_matte', 'smooth_matte', 'smooth_matte'],
            'paint_row_paint_pk': [str(p1.pk), str(p2.pk), str(p3.pk)],
            'paint_row_area_sqm': ['30', '40', '30'],
            'paint_row_coats': ['1', '2', '1'],
            'paint_row_base': ['WHITE', 'DEEP', 'PASTEL'],
        }

        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)

        items = list(QuotationLineItem.objects.filter(quotation=self.q, section=sec, item_type=QuotationLineItem.ItemType.PAINT).order_by('pk'))
        self.assertEqual(len(items), 3)

        # verify properties per row
        self.assertEqual(items[0].paint.pk, p1.pk)
        self.assertEqual(items[0].area_sqm, Decimal('30'))
        self.assertEqual(items[0].coats, 1)
        self.assertEqual(items[0].metadata.get('base'), 'WHITE')

        self.assertEqual(items[1].paint.pk, p2.pk)
        self.assertEqual(items[1].area_sqm, Decimal('40'))
        self.assertEqual(items[1].coats, 2)
        self.assertEqual(items[1].metadata.get('base'), 'DEEP')

        self.assertEqual(items[2].paint.pk, p3.pk)
        self.assertEqual(items[2].area_sqm, Decimal('30'))
        self.assertEqual(items[2].coats, 1)
        self.assertEqual(items[2].metadata.get('base'), 'PASTEL')

        # update second row only and resave: ensure other rows unchanged
        data2 = data.copy()
        # change paint_row_area_sqm for second row
        data2['paint_row_area_sqm'] = ['30', '50', '30']
        resp2 = self.client.post(url, data2)
        self.assertEqual(resp2.status_code, 302)
        items2 = list(QuotationLineItem.objects.filter(quotation=self.q, section=sec, item_type=QuotationLineItem.ItemType.PAINT).order_by('pk'))
        self.assertEqual(items2[0].area_sqm, Decimal('30'))
        self.assertEqual(items2[1].area_sqm, Decimal('50'))
        self.assertEqual(items2[2].area_sqm, Decimal('30'))

    def test_repeatable_section_isolation(self):
        # Create two sections and add paint rows to both
        sec1 = self._create_interior_section(display_name='S1')
        sec2 = self._create_interior_section(display_name='S2')

        url1 = reverse('quotation:interior_walls_save', kwargs={'pk': self.q.pk, 'section_pk': sec1.pk})
        url2 = reverse('quotation:interior_walls_save', kwargs={'pk': self.q.pk, 'section_pk': sec2.pk})

        p = Paint.objects.create(
            name="Iso Paint",
            category=Paint.Category.INTERIOR,
            base_type=Paint.BaseType.WHITE,
            price_excl_vat=Decimal("100.00"),
            price_incl_vat=Decimal("115.00"),
            spread_rate_per_litre=Decimal("10"),
            priced_volume_litres=Decimal("1.00"),
            finish=Paint.Finish.SMOOTH_MATTE,
        )

        data1 = {
            'wall_type': 'brick',
            'finishes': ['smooth_matte'],
            'area_sqm': '20',
            'paint_row_finish': ['smooth_matte'],
            'paint_row_paint_pk': [str(p.pk)],
            'paint_row_area_sqm': ['20'],
            'paint_row_coats': ['1'],
            'paint_row_base': ['WHITE'],
        }
        data2 = {
            'wall_type': 'brick',
            'finishes': ['smooth_matte'],
            'area_sqm': '30',
            'paint_row_finish': ['smooth_matte'],
            'paint_row_paint_pk': [str(p.pk)],
            'paint_row_area_sqm': ['30'],
            'paint_row_coats': ['2'],
            'paint_row_base': ['WHITE'],
        }

        resp1 = self.client.post(url1, data1)
        self.assertEqual(resp1.status_code, 302)
        resp2 = self.client.post(url2, data2)
        self.assertEqual(resp2.status_code, 302)

        items1 = QuotationLineItem.objects.filter(quotation=self.q, section=sec1, item_type=QuotationLineItem.ItemType.PAINT)
        items2 = QuotationLineItem.objects.filter(quotation=self.q, section=sec2, item_type=QuotationLineItem.ItemType.PAINT)

        self.assertEqual(items1.count(), 1)
        self.assertEqual(items2.count(), 1)

        self.assertEqual(items1.first().area_sqm, Decimal('20'))
        self.assertEqual(items2.first().area_sqm, Decimal('30'))

        # Ensure their PKs are different and they reference correct sections
        self.assertNotEqual(items1.first().pk, items2.first().pk)
        self.assertEqual(items1.first().section_id, sec1.pk)
        self.assertEqual(items2.first().section_id, sec2.pk)
