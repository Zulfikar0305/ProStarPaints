"""Validate ExportService can render HTML and create a PDF export from a draft.

Creates a fresh draft (to ensure pdf_context is present), renders HTML and
attempts PDF export. Prints results.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from specifications.services import ManualSpecificationBuilderService, ExportService


def main():
    from quotation.models import Quotation
    from django.contrib.auth import get_user_model

    User = get_user_model()
    admin = User.objects.filter(is_superuser=True).first() or User.objects.first()

    q = Quotation.objects.order_by("-created_at").first()
    if not q:
        print("NO_QUOTATION_FOUND")
        return

    builder = ManualSpecificationBuilderService()
    draft = builder.create_draft_from_resolver(q, created_by=admin, title="Export Validation Draft")
    print(f"Created draft {draft.pk}")

    exporter = ExportService()
    try:
        html = exporter.render_html_for_draft(draft, "detailed_spec")
        print(f"Rendered HTML: {len(html)} bytes")
    except Exception as exc:
        print("HTML render failed:", exc)
        return

    # Attempt PDF export (may fail if WeasyPrint native libs missing)
    try:
        res = exporter.export_pdf_from_draft(draft, "detailed_spec", generated_by=admin)
        print(f"Export status: {res.status}; file: {res.file if res.file else 'none'}; message: {res.error_message}")
    except Exception as exc:
        print("PDF export failed:", exc)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(2)
