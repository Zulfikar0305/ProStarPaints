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
        "type",
        "types",
        "substrate_type",
        "substrate",
        "surface_condition",
        "surface_conditions",
        "finish",
        "finishes",
        "preparation",
        "preparations",
        "primer",
        "primers",
        "waterproofing",
        "waterproofing_options",
        "location",
        "application",
        "applications",
        "tags",
    }

    @staticmethod
    def _as_list(v):
        if v is None:
            return []
        if isinstance(v, (list, tuple, set)):
            return list(v)
        return [v]

    @staticmethod
    def _normalise_token(value):
        return str(value).strip().lower()

    @staticmethod
    def _context_has_any(context: Dict[str, Any], keys) -> bool:
        for key in keys:
            value = context.get(key)
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                if value:
                    return True
                continue
            if isinstance(value, dict):
                if value:
                    return True
                continue
            if isinstance(value, str):
                if value.strip():
                    return True
                continue
            return True
        return False

    @classmethod
    def _match_any_value(cls, context_values, meta_keys, meta, matched_key):
        selected = []
        for source in context_values:
            selected.extend(cls._as_list(source))
        want = []
        for key in meta_keys:
            if key in meta:
                want.extend(cls._as_list(meta.get(key)))
        if not want:
            return None
        selected_norm = [cls._normalise_token(v) for v in selected if str(v).strip()]
        want_norm = {cls._normalise_token(v) for v in want if str(v).strip()}
        if not want_norm:
            return None
        intersection = [v for v in selected if cls._normalise_token(v) in want_norm]
        if not intersection:
            return None
        return {matched_key: intersection}

    @staticmethod
    def _flatten_reason_value(value):
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            items = []
            for item in value:
                items.extend(KnowledgeService._flatten_reason_value(item))
            return items
        if isinstance(value, dict):
            items = []
            for k, v in value.items():
                items.extend(KnowledgeService._flatten_reason_value(v))
            return items
        return [str(value)]

    @classmethod
    def _build_reason(cls, matched_conditions: Dict[str, Any]) -> str:
        parts: list[str] = []
        for key in sorted(matched_conditions.keys()):
            value = matched_conditions.get(key)
            for part in cls._flatten_reason_value(value):
                token = str(part).strip()
                if token:
                    parts.append(token)
        if parts:
            return ", ".join(parts)
        return ", ".join(sorted(matched_conditions.keys()))

    @classmethod
    def _match_entry(cls, entry: KnowledgeEntry, context: Dict[str, Any]) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Return (score, matched_conditions) or None if not matched."""
        meta = entry.metadata or {}
        matched = {}
        score = 0

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
            if cls._context_has_any(context, ("product_pks", "product_pk")):
                intersect = [p for p in prod_pks if str(p) in want]
                if intersect:
                    matched["product_pks"] = intersect
                    score += 3
                else:
                    return None

        prod_groups = context.get("product_groups") or []
        if "product_group" in meta or "product_groups" in meta:
            want = []
            if "product_group" in meta:
                want += cls._as_list(meta.get("product_group"))
            if "product_groups" in meta:
                want += cls._as_list(meta.get("product_groups"))
            want = [str(w) for w in want]
            if cls._context_has_any(context, ("product_groups", "product_group")):
                intersect = [g for g in prod_groups if str(g) in want]
                if intersect:
                    matched["product_groups"] = intersect
                    score += 3
                else:
                    return None

        # Type / substrate selection
        type_match = cls._match_any_value(
            [
                context.get("types"),
                context.get("type"),
                context.get("substrate_type"),
                context.get("substrate"),
            ],
            ("type", "types", "substrate_type", "substrate"),
            meta,
            "types",
        )
        if type_match is not None:
            matched.update(type_match)
            score += 2
        elif any(key in meta for key in ("type", "types", "substrate_type", "substrate")) and cls._context_has_any(context, ("type", "types", "substrate_type", "substrate")):
            return None

        # Primary condition matching
        surface_match = cls._match_any_value(
            [context.get("surface_conditions"), context.get("surface_condition")],
            ("surface_condition", "surface_conditions"),
            meta,
            "surface_conditions",
        )
        if surface_match is not None:
            matched.update(surface_match)
            score += 2
        elif any(key in meta for key in ("surface_condition", "surface_conditions")) and cls._context_has_any(context, ("surface_condition", "surface_conditions")):
            return None

        finish_match = cls._match_any_value(
            [context.get("finishes"), context.get("finish")],
            ("finish", "finishes"),
            meta,
            "finishes",
        )
        if finish_match is not None:
            matched.update(finish_match)
            score += 2
        elif any(key in meta for key in ("finish", "finishes")) and cls._context_has_any(context, ("finish", "finishes")):
            return None

        prep_match = cls._match_any_value(
            [context.get("preparations"), context.get("preparation"), context.get("prep_work"), context.get("prep")],
            ("preparation", "preparations", "prep_work", "prep"),
            meta,
            "preparations",
        )
        if prep_match is not None:
            matched.update(prep_match)
            score += 2
        elif any(key in meta for key in ("preparation", "preparations", "prep_work", "prep")) and cls._context_has_any(context, ("preparations", "preparation", "prep_work", "prep")):
            return None

        primer_match = cls._match_any_value(
            [context.get("primers"), context.get("primer")],
            ("primer", "primers"),
            meta,
            "primers",
        )
        if primer_match is not None:
            matched.update(primer_match)
            score += 2
        elif any(key in meta for key in ("primer", "primers")) and cls._context_has_any(context, ("primers", "primer")):
            return None

        waterproof_match = cls._match_any_value(
            [context.get("waterproofing_options"), context.get("waterproofing")],
            ("waterproofing", "waterproofing_options"),
            meta,
            "waterproofing",
        )
        if waterproof_match is not None:
            matched.update(waterproof_match)
            score += 2
        elif any(key in meta for key in ("waterproofing", "waterproofing_options")) and cls._context_has_any(context, ("waterproofing_options", "waterproofing")):
            return None

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

        # location
        loc = context.get("location")
        if "location" in meta:
            want = cls._as_list(meta.get("location"))
            if loc and any(str(w).lower() in str(loc).lower() for w in want):
                matched["location"] = loc
                score += 1
            elif loc is not None:
                return None

        app = context.get("application")
        if "application" in meta or "applications" in meta:
            want = []
            if "application" in meta:
                want += cls._as_list(meta.get("application"))
            if "applications" in meta:
                want += cls._as_list(meta.get("applications"))
            want = [str(w) for w in want]
            if app and str(app) in want:
                matched["application"] = app
                score += 1
            elif app is not None:
                return None

        if entry.tags:
            want = cls._as_list(meta.get("tags")) if "tags" in meta else []
            if want:
                intersect = [t for t in entry.tags if str(t) in [str(w) for w in want]]
                if intersect:
                    matched["tags"] = intersect
                    score += 1
                else:
                    return None

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
                    reason = cls._build_reason(matched_conditions)
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
