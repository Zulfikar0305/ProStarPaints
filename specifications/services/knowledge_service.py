from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone

from specifications.models import KnowledgeEntry


@dataclass
class KnowledgeMatch:
    pk: int
    title: str
    body: str
    priority: int
    score: int
    reason: str
    matched_conditions: Dict[str, Any]
    created_at: Optional[Any]


class KnowledgeService:
    """Simple, deterministic knowledge matcher.

    This service evaluates active `KnowledgeEntry` records against a
    provided context (quotation + section) and returns ordered
    `KnowledgeMatch` instances describing why each entry matched.

    Matching is conservative: an entry only matches if at least one
    recognised condition in `KnowledgeEntry.metadata` matches the
    provided context. This avoids surprising behaviour when metadata
    is empty.
    """

    # recognised metadata keys and their match semantics
    RECOGNISED_KEYS = {
        "section_key",
        "product_pk",
        "product_pks",
        "product_group",
        "product_groups",
        "moisture_min",
        "moisture_max",
        "surface_condition",
        "location",
        "application",
        "tags",
    }

    @staticmethod
    def _as_list(v):
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return list(v)
        return [v]

    @classmethod
    def _match_entry(cls, entry: KnowledgeEntry, context: Dict[str, Any]) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Return (score, matched_conditions) or None if not matched."""
        meta = entry.metadata or {}
        matched = {}
        score = 0

        # If no recognised metadata keys present, do not match conservatively
        if not any(k in meta for k in cls.RECOGNISED_KEYS):
            return None

        # section_key
        sec_key = context.get("section_key")
        if "section_key" in meta:
            want = cls._as_list(meta.get("section_key"))
            if str(sec_key) in [str(w) for w in want]:
                matched["section_key"] = sec_key
                score += 2
            else:
                return None

        # product matching
        prod_pks = context.get("product_pks") or []
        if "product_pk" in meta or "product_pks" in meta:
            want = []
            if "product_pk" in meta:
                want += cls._as_list(meta.get("product_pk"))
            if "product_pks" in meta:
                want += cls._as_list(meta.get("product_pks"))
            want = [str(w) for w in want]
            intersect = [p for p in prod_pks if str(p) in want]
            if intersect:
                matched["product_pks"] = intersect
                score += 3
            else:
                return None

        # product group matching
        prod_groups = context.get("product_groups") or []
        if "product_group" in meta or "product_groups" in meta:
            want = []
            if "product_group" in meta:
                want += cls._as_list(meta.get("product_group"))
            if "product_groups" in meta:
                want += cls._as_list(meta.get("product_groups"))
            want = [str(w) for w in want]
            intersect = [g for g in prod_groups if str(g) in want]
            if intersect:
                matched["product_groups"] = intersect
                score += 3
            else:
                return None

        # moisture range
        moisture = context.get("moisture")
        if moisture is not None and ("moisture_min" in meta or "moisture_max" in meta):
            try:
                mmin = Decimal(str(meta.get("moisture_min"))) if meta.get("moisture_min") is not None else None
            except Exception:
                mmin = None
            try:
                mmax = Decimal(str(meta.get("moisture_max"))) if meta.get("moisture_max") is not None else None
            except Exception:
                mmax = None

            ok = True
            if mmin is not None and moisture < mmin:
                ok = False
            if mmax is not None and moisture > mmax:
                ok = False
            if ok:
                matched["moisture"] = str(moisture)
                score += 2
            else:
                return None

        # surface condition
        surf = context.get("surface_condition")
        if "surface_condition" in meta:
            want = cls._as_list(meta.get("surface_condition"))
            if surf is not None and str(surf) in [str(w) for w in want]:
                matched["surface_condition"] = surf
                score += 2
            else:
                return None

        # location
        loc = context.get("location")
        if "location" in meta:
            want = cls._as_list(meta.get("location"))
            if loc and any(str(w).lower() in str(loc).lower() for w in want):
                matched["location"] = loc
                score += 1
            else:
                return None

        # application
        app = context.get("application")
        if "application" in meta:
            want = cls._as_list(meta.get("application"))
            if app and str(app) in [str(w) for w in want]:
                matched["application"] = app
                score += 1
            else:
                return None

        # tags (entry-level)
        if entry.tags:
            # if metadata requested specific tags, ensure intersection
            want = cls._as_list(meta.get("tags")) if "tags" in meta else []
            if want:
                intersect = [t for t in entry.tags if str(t) in [str(w) for w in want]]
                if intersect:
                    matched["tags"] = intersect
                    score += 1
                else:
                    return None

        # At least one matched condition required
        if not matched:
            return None

        return score, matched

    @classmethod
    def find_matches_for_section(cls, quotation, section_context: Dict[str, Any]) -> List[KnowledgeMatch]:
        """Return ordered KnowledgeMatch list for a section context.

        section_context should include keys like: section_key, product_pks,
        product_groups, moisture, surface_condition, location, application.
        """
        qs = KnowledgeEntry.objects.filter(is_active=True).select_related("category")

        matches: List[KnowledgeMatch] = []
        for entry in qs:
            try:
                res = cls._match_entry(entry, section_context)
                if res:
                    score, matched_conditions = res
                    reason = ", ".join(sorted(matched_conditions.keys()))
                    km = KnowledgeMatch(
                        pk=entry.pk,
                        title=entry.title,
                        body=entry.body,
                        priority=int(entry.priority or 0),
                        score=int(score),
                        reason=reason,
                        matched_conditions=matched_conditions,
                        created_at=getattr(entry, "created_at", None),
                    )
                    matches.append(km)
            except Exception:
                # Non-fatal: skip problematic entries
                continue

        # Order by priority desc, score desc, created_at asc to be deterministic
        matches.sort(key=lambda m: (-m.priority, -m.score, m.created_at or timezone.datetime(1970,1,1)))
        return matches
