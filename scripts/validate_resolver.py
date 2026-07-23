"""Validate the SpecificationResolver against an existing Quotation.

Finds the first available Quotation and prints the resolved structure as JSON.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import json
from specifications.services import SpecificationResolver
from django.db.models import Q


def main():
    from quotation.models import Quotation

    q = Quotation.objects.order_by("-created_at").first()
    if not q:
        print("NO_QUOTATION_FOUND")
        return

    resolver = SpecificationResolver()
    spec = resolver.resolve(q)
    print(json.dumps(spec, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(2)
