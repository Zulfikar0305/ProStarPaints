"""Validate Specification Preview rendering for an existing draft.

Renders the preview HTML for the most recent draft and prints a short
summary verifying that key items are present.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from specifications.services import PreviewService


def main():
    from specifications.models import ManualSpecificationDraft

    draft = ManualSpecificationDraft.objects.order_by("-updated_at").first()
    if not draft:
        print("NO_DRAFT_FOUND")
        return

    svc = PreviewService()
    ctx = svc.preview_context_for_draft(draft)

    # Render template to string
    from django.template.loader import render_to_string

    html = render_to_string("specifications/preview.html", ctx)
    print(f"RENDERED {len(html)} bytes for draft {draft.pk}")

    # Quick content checks
    checks = []
    checks.append(("quotation_reference", str(draft.quotation.reference) in html))
    secs = ctx.get("sections", [])
    if secs:
        checks.append(("first_section_present", secs[0].get("section_name", "") in html))

    for name, ok in checks:
        print(f"{name}: {'OK' if ok else 'MISSING'}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(2)
