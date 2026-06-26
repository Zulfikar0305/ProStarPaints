from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Quotation, QuotationSection, QuotationLineItem
from django.core.files.uploadedfile import SimpleUploadedFile


class ConcurrencyAndPaintRowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="concur", password="pass")
        self.client.force_login(self.user)
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C")
        self.section = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=1, selection_order=1)

    def test_duplicate_row_prevention_via_single_post(self):
        # Simulate a single POST which includes both per-row and legacy group inputs
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.q.pk, "section_pk": self.section.pk})
        # per-row fields (one row)
        data = {
            "wall_type": "brick",
            "paint_row_finish": ["smooth_matte"],
            "paint_row_paint_pk": [""],
            "paint_row_area_sqm": ["10"],
            "paint_row_coats": ["1"],
            # legacy group inputs that might conflict if both branches executed
            "paint_selected_pure_matte": "on",
            "paint_coats_pure_matte": "1",
        }
        resp = self.client.post(url, data, follow=True)
        self.assertEqual(resp.status_code, 200)
        # Expect paint line count: 1 (per-row preferred)
        paints = QuotationLineItem.objects.filter(section=self.section, item_type=QuotationLineItem.ItemType.PAINT)
        self.assertEqual(paints.count(), 1)

    def test_primer_and_waterproofing_area_persistence(self):
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.q.pk, "section_pk": self.section.pk})
        data = {
            "wall_type": "brick",
            "primers": ["plaster_primerseal"],
            "waterproofing": ["hydro_shield"],
            "area_sqm": "25.5",
        }
        resp = self.client.post(url, data, follow=True)
        self.assertEqual(resp.status_code, 200)
        primers = QuotationLineItem.objects.filter(section=self.section, item_type=QuotationLineItem.ItemType.PRIMER)
        wps = QuotationLineItem.objects.filter(section=self.section, item_type=QuotationLineItem.ItemType.WATERPROOFING)
        self.assertEqual(primers.count(), 1)
        self.assertEqual(wps.count(), 1)
        self.assertEqual(str(primers.first().area_sqm), '25.50')
        self.assertEqual(str(wps.first().area_sqm), '25.50')

    def test_repeatable_section_isolation(self):
        other = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", sort_order=2, selection_order=2)
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.q.pk, "section_pk": self.section.pk})
        img = SimpleUploadedFile("iso.png", b"\x89PNG\r\n\x1a\ndata", content_type="image/png")
        resp = self.client.post(url, {"wall_type": "brick", "section_images": img}, follow=True)
        self.assertEqual(resp.status_code, 200)
        from .models import QuotationSectionImage
        self.assertEqual(QuotationSectionImage.objects.filter(section=self.section).count(), 1)
        self.assertEqual(QuotationSectionImage.objects.filter(section=other).count(), 0)
