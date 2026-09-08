from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from system_tools.branding import get_branding
from system_tools.models import BrandingSetting


class BrandingPdfAssetsTests(TestCase):
    def test_branding_exposes_optional_pdf_header_and_footer_image_data_uris(self):
        branding = BrandingSetting.load()
        branding.pdf_header_image.save(
            "header.png",
            SimpleUploadedFile("header.png", b"header-image-bytes", content_type="image/png"),
            save=False,
        )
        branding.pdf_footer_image.save(
            "footer.png",
            SimpleUploadedFile("footer.png", b"footer-image-bytes", content_type="image/png"),
            save=False,
        )
        branding.save()

        result = get_branding()

        self.assertIn("pdf_header_image_data_uri", result)
        self.assertIn("pdf_footer_image_data_uri", result)
        self.assertTrue(result["pdf_header_image_data_uri"].startswith("data:image/png;base64,"))
        self.assertTrue(result["pdf_footer_image_data_uri"].startswith("data:image/png;base64,"))
