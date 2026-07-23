from decimal import Decimal, InvalidOperation
from typing import List

from specifications.models import SpecificationRule, KnowledgeEntry


class RuleService:
    """Evaluate SpecificationRule entries and expose matched clauses.

    Initially supports Moisture rule_type only.
    """

    @staticmethod
    def _to_decimal(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @classmethod
    def matching_rules_for_moisture(cls, moisture_value) -> List[SpecificationRule]:
        v = cls._to_decimal(moisture_value)
        if v is None:
            return []

        qs = SpecificationRule.objects.filter(rule_type=SpecificationRule.RULE_MOISTURE, active=True).order_by(
            "priority", "pk"
        ).prefetch_related("clauses")

        matches: List[SpecificationRule] = []
        for r in qs:
            min_v = r.min_value
            max_v = r.max_value
            if (min_v is None or v >= min_v) and (max_v is None or v <= max_v):
                matches.append(r)

        return matches

    @classmethod
    def clauses_for_moisture(cls, moisture_value) -> List[KnowledgeEntry]:
        rules = cls.matching_rules_for_moisture(moisture_value)
        if not rules:
            return []
        # Gather distinct clauses linked to matched rules
        return list(
            KnowledgeEntry.objects.filter(spec_rules__in=rules, is_active=True).distinct().order_by("sort_order", "title")
        )
