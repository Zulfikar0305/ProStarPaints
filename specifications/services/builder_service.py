"""Services for the Manual Specification Builder.

This service is intentionally thin: it reuses the existing
`SpecificationResolver` to produce an initial structured specification
and provides helpers to create and persist user-edited drafts.
"""
from __future__ import annotations

from typing import Any, Dict

from .resolver import SpecificationResolver


class ManualSpecificationBuilderService:
    """High-level helper for preparing and persisting manual drafts."""

    def __init__(self):
        self.resolver = SpecificationResolver()

    def prepare_spec(self, quotation) -> Dict[str, Any]:
        """Return the resolver-produced specification dict for *quotation*."""
        return self.resolver.resolve(quotation)

    def create_draft_from_resolver(self, quotation, created_by=None, title: str = ""):
        """Create and return a ManualSpecificationDraft populated from resolver output.

        The draft is saved and returned. Caller may further update the draft
        via `save_draft()`.
        """
        data = self.prepare_spec(quotation)
        # Import model lazily to avoid circular imports during app registry
        from specifications.models import ManualSpecificationDraft

        draft = ManualSpecificationDraft.objects.create(
            quotation=quotation, title=title or "", data=data, created_by=created_by
        )
        return draft

    def save_draft(self, draft, data: Dict[str, Any]):
        """Persist edited draft data (replace entire JSON blob)."""
        draft.data = data
        draft.save()
        return draft

    def latest_draft_for_user(self, quotation, user):
        from specifications.models import ManualSpecificationDraft

        return (
            ManualSpecificationDraft.objects.filter(quotation=quotation, created_by=user)
            .order_by("-updated_at")
            .first()
        )
