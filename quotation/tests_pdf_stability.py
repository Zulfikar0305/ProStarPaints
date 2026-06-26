from django.test import TestCase
from django.contrib.auth import get_user_model
from quotation.models import Quotation, QuotationPdfExport
from quotation.pdf_service import render_quotation_pdf

import builtins
from unittest import mock


class PdfStabilityTests(TestCase):
    def test_render_handles_missing_weasyprint_gracefully(self):
        User = get_user_model()
        user = User.objects.create(username="pdf_stability_user")
        q = Quotation.objects.create(created_by=user, customer_name="PDF Stability")

        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            # Simulate ImportError only for the top-level 'weasyprint' module
            if name == 'weasyprint' or (name and name.split('.')[0] == 'weasyprint'):
                raise ImportError('Simulated missing weasyprint')
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch('builtins.__import__', side_effect=fake_import):
            export = render_quotation_pdf(q, template_key='professional', generated_by=user, request=None)
            self.assertIsInstance(export, QuotationPdfExport)
            self.assertEqual(export.status, QuotationPdfExport.Status.FAILED)
            self.assertTrue(export.error_message)
