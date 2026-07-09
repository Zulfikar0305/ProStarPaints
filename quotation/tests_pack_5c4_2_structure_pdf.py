from decimal import Decimal

from django.test import TestCase, RequestFactory
from django.template.loader import render_to_string

from django.contrib.auth import get_user_model

from .models import Quotation, QuotationSection, QuotationLineItem
from .pdf_service import build_pdf_context
from paints.models import Paint


class Pack5C4_2_StructureTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", email="t@example.com", password="pass")

        # Create a quotation with one section and a couple of line items
        self.quotation = Quotation.objects.create(
            created_by=self.user,
            customer_name="ACME Ltd",
            project_name="Office Refurb",
            project_location="Block A",
            subtotal_excl_vat=Decimal("1550.00"),
            vat_amount=Decimal("232.50"),
            total_incl_vat=Decimal("1782.50"),
        )

        self.section = QuotationSection.objects.create(
            quotation=self.quotation,
            subsection_key="interior_walls",
            display_name="Interior Walls 1",
            substrate_type=QuotationSection.SubstrateType.INTERIOR,
        )

        # Product used for one paint line
        self.paint = Paint.objects.create(
            name="Pro Paint",
            price_excl_vat=Decimal("100.00"),
            price_incl_vat=Decimal("115.00"),
            finish=Paint.Finish.SMOOTH_MATTE,
            base_type=Paint.BaseType.WHITE,
            spread_rate_per_litre=Decimal("8.00"),
            priced_volume_litres=Decimal("1.00"),
            package_unit=Paint.PackageUnit.LITRE,
        )

        # Paint line
        self.line_paint = QuotationLineItem.objects.create(
            quotation=self.quotation,
            section=self.section,
            item_type=QuotationLineItem.ItemType.PAINT,
            description="Apply topcoat",
            paint=self.paint,
            coats=2,
            area_sqm=Decimal("15.00"),
            price_excl_vat=Decimal("100.00"),
            price_incl_vat=Decimal("115.00"),
            total_excl_vat=Decimal("1500.00"),
            total_incl_vat=Decimal("1725.00"),
            metadata={
                "surface_cond_labels": ["Good"],
                "spread_rate_per_litre": "8.00",
                "required_litres": "2.00",
                "recommended_containers": "1",
                "package_size": "5",
                "package_unit": "L",
                "price_per_litre_excl_vat": "100.00",
            },
        )

        # Prep line
        self.line_prep = QuotationLineItem.objects.create(
            quotation=self.quotation,
            section=self.section,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description="Prepare surface: sand and clean",
            coats=1,
            total_excl_vat=Decimal("50.00"),
            total_incl_vat=Decimal("57.50"),
        )

        self.request = RequestFactory().get("/")

    def test_project_details_render_before_sections(self):
        context = build_pdf_context(self.quotation, request=self.request)
        html = render_to_string('quotation/pdf/detailed_spec.html', context)
        
        idx_summary = html.find('class="summary-bar"')
        idx_first_section = html.find('class="sec-title"')
        self.assertNotEqual(idx_summary, -1, "Expected 'class=\"summary-bar\"' to be present in rendered HTML")
        self.assertNotEqual(idx_first_section, -1, "Expected first section title 'class=\"sec-title\"' to be present in rendered HTML")
        self.assertLess(idx_summary, idx_first_section, "Expected 'class=\"summary-bar\"' to appear before the first 'class=\"sec-title\"' (project details should precede sections)")

    def test_headings_and_totals_and_section_independence(self):
        context = build_pdf_context(self.quotation, request=self.request)
        html = render_to_string('quotation/pdf/detailed_spec.html', context)

        # Headings
        # Template was reorganized: 'Surface Information' -> 'Section Overview'
        self.assertIn('Section Overview', html, "Expected heading 'Section Overview' to be present in rendered HTML")
        self.assertIn('Preparation Requirements', html, "Expected heading 'Preparation Requirements' to be present in rendered HTML")
        self.assertIn('Application Requirements', html, "Expected heading 'Application Requirements' to be present in rendered HTML")
        self.assertIn('Coating System', html, "Expected heading 'Coating System' to be present in rendered HTML")
        self.assertIn('Technical Information', html, "Expected heading 'Technical Information' to be present in rendered HTML")
        self.assertIn('Material Costing', html, "Expected heading 'Material Costing' to be present in rendered HTML")

        # Section renders independently (display name appears once as a section title)
        self.assertIn('Interior Walls 1', html, "Expected section display name 'Interior Walls 1' to be present in rendered HTML")

        # Estimate Summary (totals) appears after sections
        idx_last_section = html.rfind('class="sec-title"')
        idx_totals = html.find('class="totals-right"')
        self.assertNotEqual(idx_last_section, -1, "Expected at least one section title 'class=\"sec-title\"' to be present in rendered HTML")
        self.assertNotEqual(idx_totals, -1, "Expected totals block 'class=\"totals-right\"' to be present in rendered HTML")
        self.assertLess(idx_last_section, idx_totals, "Expected totals block 'class=\"totals-right\"' to appear after the last section title 'class=\"sec-title\"'")

        # Persisted totals unchanged in template
        self.assertIn('R 1,550.00'.replace(',', ''), html, "Expected persisted subtotal 'R 1,550.00' (commas removed) to appear in rendered HTML") or self.assertIn('R 1550.00', html, "Expected persisted subtotal 'R 1550.00' to appear in rendered HTML")
        self.assertIn('R 232.50', html, "Expected persisted VAT amount 'R 232.50' to appear in rendered HTML")
        self.assertIn('R 1782.50', html, "Expected persisted total 'R 1782.50' to appear in rendered HTML")
