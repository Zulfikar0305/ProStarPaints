"""Validate ManualSpecificationBuilderService can create a draft.

Creates a draft from the most recent quotation using the builder service
and prints the created draft ID.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import json
from specifications.services import ManualSpecificationBuilderService


def main():
    from quotation.models import Quotation
    from django.contrib.auth import get_user_model

    User = get_user_model()
    admin = User.objects.filter(is_superuser=True).first() or User.objects.first()

    q = Quotation.objects.order_by("-created_at").first()
    if not q:
        print("NO_QUOTATION_FOUND")
        return

    svc = ManualSpecificationBuilderService()
    draft = svc.create_draft_from_resolver(q, created_by=admin, title="Validation Draft")
    print(json.dumps({"draft_id": draft.pk, "quotation": q.reference}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(2)
