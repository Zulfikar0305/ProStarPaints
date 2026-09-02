from io import BytesIO

from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model

from .config import ALL_GENERIC_SECTION_CONFIGS


class ReviewImageContextTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="imgctx", password="pass")
        self.client.force_login(self.user)

        from .models import Quotation, QuotationSection
        self.quotation = Quotation.objects.create(created_by=self.user, customer_name="Ctx Ltd")
        self.section = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key="interior_walls",
            display_name="Interior Walls",
            sort_order=1,
            selection_order=1,
        )

    def test_review_context_contains_section_images_list(self):
        # upload an image
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk})
        img = SimpleUploadedFile("rimg.png", b"\x89PNG\r\n\x1a\ndata", content_type="image/png")
        self.client.post(url, {"wall_type": "brick", "section_images": img}, follow=True)

        # Fetch review page and check context built by QuotationReviewView
        url = reverse("quotation:quotation_review", kwargs={"pk": self.quotation.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx_sections = resp.context.get("section_data")
        self.assertIsInstance(ctx_sections, list)
        sec_entry = next((s for s in ctx_sections if s.get("section").pk == self.section.pk), None)
        self.assertIsNotNone(sec_entry)
        # images in review context should be a list (of data URIs)
        self.assertTrue(isinstance(sec_entry.get("images"), list))


class GenericSectionImageLifecycleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="generic_img", password="pass")
        self.client.force_login(self.user)
        from .models import Quotation
        self.quotation = Quotation.objects.create(created_by=self.user, customer_name="Generic Builder")

    def _make_png(self, name="img.png", size=(10, 10)):
        try:
            from PIL import Image

            buf = BytesIO()
            img = Image.new("RGB", size, color=(255, 255, 255))
            img.save(buf, format="PNG")
            buf.seek(0)
            return SimpleUploadedFile(name, buf.read(), content_type="image/png")
        except Exception:
            PNG_1X1 = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00"
                b"\x18\xdd\x03\xc5\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            return SimpleUploadedFile(name, PNG_1X1, content_type="image/png")

    def test_generic_sections_persist_uploads_after_save_reload_and_delete(self):
        from .models import QuotationSection

        keys = [
            "ceilings",
            "floors",
            "doors_trims_skirtings",
            "window_frames",
            "exterior_walls",
            "exterior_doors_trims_skirtings",
            "roof",
            "soffits_fascia",
            "gutter",
            "deck_patio",
            "fencing",
            "garage_door",
            "pavings",
            "exterior_window_frames",
        ]

        for key in keys:
            section = None
            try:
                cfg = ALL_GENERIC_SECTION_CONFIGS[key]
                section = QuotationSection.objects.create(
                    quotation=self.quotation,
                    subsection_key=key,
                    display_name=cfg.display_name,
                    sort_order=1,
                    selection_order=1,
                )
                post = {
                    "types": [cfg.types[0][0]],
                    "surface_conditions": [cfg.surface_conditions[0][0]] if cfg.surface_conditions else [],
                    "finishes": [cfg.finishes[0][0]],
                    "area_sqm": "12.5",
                    "moisture_level": "8",
                    "section_images": self._make_png(f"{key}.png"),
                }
                save_url = reverse("quotation:section_save", kwargs={"pk": self.quotation.pk, "section_pk": section.pk})
                resp = self.client.post(save_url, post, follow=True)
                self.assertEqual(resp.status_code, 200, f"Save failed for {key}")
                self.assertTrue(section.images.exists(), f"Upload did not persist for {key}")

                img = section.images.first()
                builder_url = reverse("quotation:quotation_builder", kwargs={"pk": self.quotation.pk}) + f"?leaflet={key}"
                builder_resp = self.client.get(builder_url)
                self.assertEqual(builder_resp.status_code, 200, f"Builder failed for {key}")
                self.assertContains(builder_resp, img.image.url, msg_prefix=f"Builder did not render persisted image for {key}")

                delete_url = reverse("quotation:section_image_delete", kwargs={"pk": self.quotation.pk, "section_pk": section.pk, "image_pk": img.pk})
                delete_resp = self.client.post(delete_url, follow=True)
                self.assertEqual(delete_resp.status_code, 200, f"Delete failed for {key}")
                self.assertFalse(section.images.exists(), f"Image remained after delete for {key}")
            finally:
                if section is not None:
                    section.delete()


class SectionImageTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from .models import Quotation, QuotationSection

        User = get_user_model()
        self.user = User.objects.create_user(username="imgtest", password="pass")
        self.client.force_login(self.user)

        # Minimal quotation and a single interior_walls section
        self.quotation = Quotation.objects.create(
            created_by=self.user,
            customer_name="ACME Ltd",
        )
        self.section = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key="interior_walls",
            display_name="Interior Walls",
            sort_order=1,
            selection_order=1,
        )

    def _make_png(self, name="img.png", size=(10, 10)):
        """Return a SimpleUploadedFile containing a tiny PNG.

        Falls back to a static 1x1 PNG if Pillow is not available.
        """
        try:
            from PIL import Image

            buf = BytesIO()
            img = Image.new("RGB", size, color=(255, 255, 255))
            img.save(buf, format="PNG")
            buf.seek(0)
            return SimpleUploadedFile(name, buf.read(), content_type="image/png")
        except Exception:
            PNG_1X1 = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00"
                b"\x18\xdd\x03\xc5\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            return SimpleUploadedFile(name, PNG_1X1, content_type="image/png")

    def _make_text_file(self, name="bad.txt", size=100):
        return SimpleUploadedFile(name, b"x" * size, content_type="text/plain")

    def _make_big_file(self, name="big.png", size=(4 * 1024 * 1024) + 10):
        return SimpleUploadedFile(name, b"0" * size, content_type="image/png")

    def test_upload_image_creates_record_and_storage(self):
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk})
        img = self._make_png("upload1.png")
        resp = self.client.post(url, {"wall_type": "brick", "section_images": img}, follow=True)
        from .models import QuotationSectionImage

        self.assertEqual(QuotationSectionImage.objects.filter(section=self.section).count(), 1)
        inst = QuotationSectionImage.objects.filter(section=self.section).first()
        self.assertTrue(default_storage.exists(inst.image.name))

    def test_restore_images_after_reopen_builder(self):
        # Upload then GET builder and ensure section shows images in context
        self.test_upload_image_creates_record_and_storage()
        url = reverse("quotation:quotation_builder", kwargs={"pk": self.quotation.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        interior_sections = resp.context["interior_sections_data"]
        entry = next((e for e in interior_sections if e["section"].pk == self.section.pk), None)
        self.assertIsNotNone(entry)
        self.assertTrue(entry["section"].images.exists())

    def test_delete_image_removes_db_and_file(self):
        # Upload
        self.test_upload_image_creates_record_and_storage()
        from .models import QuotationSectionImage

        inst = QuotationSectionImage.objects.filter(section=self.section).first()
        del_url = reverse("quotation:section_image_delete", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk, "image_pk": inst.pk})
        resp = self.client.post(del_url, follow=True)
        self.assertFalse(QuotationSectionImage.objects.filter(pk=inst.pk).exists())
        self.assertFalse(default_storage.exists(inst.image.name))

    def test_max_three_images_enforced(self):
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk})
        from .models import QuotationSectionImage

        # Upload 4 times (single-file posts). Only 3 should persist.
        for i in range(4):
            img = self._make_png(f"i{i}.png")
            self.client.post(url, {"wall_type": "brick", "section_images": img}, follow=True)

        self.assertEqual(QuotationSectionImage.objects.filter(section=self.section).count(), 3)

    def test_invalid_file_type_rejected(self):
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk})
        bad = self._make_text_file()
        self.client.post(url, {"wall_type": "brick", "section_images": bad}, follow=True)
        from .models import QuotationSectionImage
        self.assertEqual(QuotationSectionImage.objects.filter(section=self.section).count(), 0)

    def test_oversized_file_rejected(self):
        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk})
        big = self._make_big_file()
        self.client.post(url, {"wall_type": "brick", "section_images": big}, follow=True)
        from .models import QuotationSectionImage
        self.assertEqual(QuotationSectionImage.objects.filter(section=self.section).count(), 0)

    def test_repeatable_section_isolation(self):
        from .models import QuotationSection, QuotationSectionImage

        # Create a sibling repeated section (different selection_order)
        other = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key="interior_walls",
            display_name="Interior Walls copy",
            sort_order=2,
            selection_order=2,
        )

        url = reverse("quotation:interior_walls_save", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk})
        img = self._make_png("iso.png")
        self.client.post(url, {"wall_type": "brick", "section_images": img}, follow=True)

        # Only the original section should have images
        self.assertEqual(QuotationSectionImage.objects.filter(section=self.section).count(), 1)
        self.assertEqual(QuotationSectionImage.objects.filter(section=other).count(), 0)

    def test_review_page_contains_thumbnail_urls(self):
        # Upload then GET review page and assert image URLs are included
        self.test_upload_image_creates_record_and_storage()
        inst = None
        from .models import QuotationSectionImage

        inst = QuotationSectionImage.objects.filter(section=self.section).first()
        url = reverse("quotation:quotation_review", kwargs={"pk": self.quotation.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        # The review template displays media URLs for thumbnails
        self.assertIn(inst.image.url, content)

    def test_build_pdf_context_includes_base64_images(self):
        # Upload file then call build_pdf_context to verify base64 URIs
        self.test_upload_image_creates_record_and_storage()
        from .pdf_service import build_pdf_context

        ctx = build_pdf_context(self.quotation, request=None)
        # Find our section in the built sections list
        sec = next((s for s in ctx.get("sections", []) if s.get("section").pk == self.section.pk), None)
        self.assertIsNotNone(sec)
        self.assertTrue(isinstance(sec.get("images"), list))
        self.assertTrue(len(sec.get("images")) >= 1)
        self.assertTrue(sec.get("images")[0].startswith("data:image/"))

    def test_cleanup_on_section_and_quotation_delete(self):
        from .models import QuotationSectionImage, Quotation, QuotationSection

        # Upload image
        self.test_upload_image_creates_record_and_storage()
        inst = QuotationSectionImage.objects.filter(section=self.section).first()
        name = inst.image.name

        # Delete section → images should be removed from storage
        self.section.delete()
        self.assertFalse(default_storage.exists(name))
        self.assertFalse(QuotationSectionImage.objects.filter(pk=inst.pk).exists())

        # Recreate another quotation and section for quotation delete test
        q2 = Quotation.objects.create(created_by=self.user, customer_name="ACME 2")
        s2 = QuotationSection.objects.create(
            quotation=q2,
            subsection_key="interior_walls",
            display_name="Interior Walls",
            sort_order=1,
            selection_order=1,
        )
        url = reverse("quotation:interior_walls_save", kwargs={"pk": q2.pk, "section_pk": s2.pk})
        img = self._make_png("recreate.png")
        self.client.post(url, {"wall_type": "brick", "section_images": img}, follow=True)
        inst2 = QuotationSectionImage.objects.filter(section=s2).first()
        name2 = inst2.image.name

        # Delete quotation → images should be removed
        q2.delete()
        self.assertFalse(default_storage.exists(name2))
        self.assertFalse(QuotationSectionImage.objects.filter(pk=inst2.pk).exists())

    def test_three_image_multi_upload_lifecycle_trace(self):
        """
        Reproduce a single POST uploading three images and trace lifecycle:
        1) present in request.FILES
        2) DB row created
        3) DB write persisted
        4) builder queryset returns it
        5) builder template renders thumbnail URL
        """
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.urls import reverse

        from .views import InteriorWallsSaveView
        from .models import QuotationSectionImage

        # Build three distinct PNG byte blobs so we can map saved files back
        try:
            from PIL import Image

            def make_png_bytes(size):
                buf = BytesIO()
                img = Image.new("RGB", size, color=(size[0] % 255, size[1] % 255, (size[0] * size[1]) % 255))
                img.save(buf, format="PNG")
                return buf.getvalue()
        except Exception:
            # Minimal distinct byte blobs fallback
            def make_png_bytes(size):
                return b"PNG" + bytes([size[0] % 256, size[1] % 256])

        contents = [make_png_bytes((10, 10)), make_png_bytes((11, 11)), make_png_bytes((12, 12))]
        imgs = [SimpleUploadedFile(f"multi{i}.png", contents[i], content_type="image/png") for i in range(3)]

        # Prepare a RequestFactory POST so we can inspect request.FILES directly
        factory = RequestFactory()
        path = reverse("quotation:interior_walls_save", kwargs={"pk": self.quotation.pk, "section_pk": self.section.pk})
        data = {"wall_type": "brick", "section_images": imgs}
        req = factory.post(path, data)
        req.user = self.user

        # Attach session + messages (used by the view)
        sess_mw = SessionMiddleware(lambda req: None)
        sess_mw.process_request(req)
        req.session.save()
        req._messages = FallbackStorage(req)

        # Checkpoint 1: files present in request.FILES
        files_list_before = req.FILES.getlist("section_images") if getattr(req, "FILES", None) else []
        self.assertEqual(len(files_list_before), 3, "request.FILES does not contain three uploaded files")

        # Call the view directly (same process) so we can then inspect DB + storage
        resp = InteriorWallsSaveView.as_view()(req, pk=self.quotation.pk, section_pk=self.section.pk)

        # Checkpoint 2/3: DB rows created and persisted
        db_images = list(QuotationSectionImage.objects.filter(section=self.section).order_by("sort_order", "pk"))
        self.assertEqual(len(db_images), 3, f"Expected 3 QuotationSectionImage rows, found {len(db_images)}")

        # Map saved files back to uploaded contents by comparing stored bytes
        mapped_indices = set()
        for inst in db_images:
            self.assertTrue(default_storage.exists(inst.image.name), f"Stored file missing: {inst.image.name}")
            with default_storage.open(inst.image.name, "rb") as fh:
                saved = fh.read()
            try:
                idx = contents.index(saved)
            except ValueError:
                # If exact content-match fails, fail the test — mapping is required
                self.fail(f"Saved file content for {inst.image.name} does not match any uploaded content")
            mapped_indices.add(idx)

        self.assertEqual(mapped_indices, {0, 1, 2}, f"Saved files did not map to all uploaded files: {mapped_indices}")

        # Checkpoint 4/5: Builder queryset and template render thumbnail URLs
        builder_url = reverse("quotation:quotation_builder", kwargs={"pk": self.quotation.pk})
        resp_get = self.client.get(builder_url)
        self.assertEqual(resp_get.status_code, 200)

        interior_sections = resp_get.context.get("interior_sections_data")
        entry = next((e for e in interior_sections if e["section"].pk == self.section.pk), None)
        self.assertIsNotNone(entry, "Section entry missing from builder context")
        self.assertTrue(entry["section"].images.exists())
        self.assertEqual(entry["section"].images.count(), 3)

        html = resp_get.content.decode("utf-8")
        for inst in db_images:
            self.assertIn(inst.image.url, html, f"Image URL {inst.image.url} not rendered in builder HTML")
