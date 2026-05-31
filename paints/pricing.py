"""
paints.pricing
==============

Admin-only Pricing Maintenance dashboard.

Read-only catalogue diagnostics + a thin inline editor that writes
`price_excl_vat` and `price_incl_vat` (recomputing incl_vat from the live
VAT setting unless the admin overrides it).

This module does **not** compute quotation totals — pricing engine remains
intentionally separate.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db.models import Count, Q
from django.utils.timezone import now

from system_tools.models import AppSetting

from .models import Paint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TWO_PLACES = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    """Round a Decimal to 2 places using banker-friendly half-up."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_incl_vat(excl: Decimal, vat_rate: Decimal | None = None) -> Decimal:
    """incl = excl * (1 + vat_rate/100). Pure function, never raises."""
    if vat_rate is None:
        vat_rate = AppSetting.get_vat_rate()
    multiplier = (Decimal("100") + Decimal(vat_rate)) / Decimal("100")
    return quantize_money(Decimal(excl) * multiplier)


def parse_money(raw: str | None) -> Decimal | None:
    """
    Parse a money string from a form field.
    Returns Decimal or None if missing/blank. Raises InvalidOperation on
    bad input — callers should catch.
    """
    if raw is None:
        return None
    raw = str(raw).strip().replace(",", "").replace(" ", "")
    if raw == "":
        return None
    return Decimal(raw)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def filter_paints(params) -> "QuerySet[Paint]":
    """Apply search/category/type/base/status/price filters from a QueryDict."""
    qs = Paint.objects.all()

    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(colour__icontains=q)
            | Q(description__icontains=q)
        )

    category = (params.get("category") or "").strip()
    if category:
        qs = qs.filter(category=category)

    paint_type = (params.get("paint_type") or "").strip()
    if paint_type:
        qs = qs.filter(paint_type=paint_type)

    base_type = (params.get("base_type") or "").strip()
    if base_type:
        qs = qs.filter(base_type=base_type)

    status = (params.get("status") or "all").strip()
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    price_state = (params.get("price_state") or "").strip()
    if price_state == "missing":
        qs = qs.filter(Q(price_excl_vat__isnull=True) | Q(price_excl_vat=0) | Q(price_incl_vat=0))
    elif price_state == "priced":
        qs = qs.filter(price_excl_vat__gt=0, price_incl_vat__gt=0)

    return qs.order_by("category", "name")


# ---------------------------------------------------------------------------
# Catalogue quality
# ---------------------------------------------------------------------------

def get_catalogue_quality() -> dict:
    """Compute the catalogue quality scorecard across all paints."""
    all_qs = Paint.objects.all()
    total = all_qs.count()
    active = all_qs.filter(is_active=True).count()
    inactive = total - active

    missing_price_qs = all_qs.filter(
        Q(price_excl_vat__isnull=True) | Q(price_excl_vat=0) | Q(price_incl_vat=0)
    )
    missing_image_qs = all_qs.filter(Q(image="") | Q(image__isnull=True))

    # "Missing classification" — any blank-ish category/type/base.
    # Choices use defaults so blanks are unusual, but guard against empty strings.
    missing_class_qs = all_qs.filter(
        Q(category="") | Q(paint_type="") | Q(base_type="")
    )

    # Duplicates: same name + category + base_type repeated
    dup_groups = (
        all_qs.values("name", "category", "base_type")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .order_by("-n", "name")
    )
    dup_count = sum(g["n"] for g in dup_groups) - len(dup_groups)

    score_parts = []
    if total:
        score_parts.append(1 - (missing_price_qs.count() / total))
        score_parts.append(1 - (missing_image_qs.count() / total))
        score_parts.append(1 - (missing_class_qs.count() / total))
        score_parts.append(1 - (dup_count / total if dup_count <= total else 1))
        score = round(sum(score_parts) / len(score_parts) * 100)
    else:
        score = 0

    return {
        "total":              total,
        "active":             active,
        "inactive":           inactive,
        "missing_price":      missing_price_qs.count(),
        "missing_image":      missing_image_qs.count(),
        "missing_class":      missing_class_qs.count(),
        "duplicate_groups":   list(dup_groups[:10]),
        "duplicate_count":    dup_count,
        "score":              score,
        "generated_at":       now(),
    }


# ---------------------------------------------------------------------------
# Inline update
# ---------------------------------------------------------------------------

class PriceUpdateError(ValueError):
    """Raised when an inline price update is rejected."""


def apply_price_update(
    paint: Paint,
    raw_excl: str | None,
    raw_incl: str | None,
    auto_vat: bool,
) -> tuple[dict, dict]:
    """
    Validate and apply a price update. Returns (before, after) dicts of
    {price_excl_vat, price_incl_vat} for audit metadata.

    Rules:
    - both must be parseable
    - neither can be negative
    - if `auto_vat` is True (default), incl is recomputed from excl using the
      current VAT setting and any submitted incl value is ignored
    - if `auto_vat` is False, incl must be >= excl
    """
    try:
        excl = parse_money(raw_excl)
    except InvalidOperation as e:
        raise PriceUpdateError("Price (excl. VAT) is not a valid number.") from e

    if excl is None:
        raise PriceUpdateError("Price (excl. VAT) is required.")
    if excl < 0:
        raise PriceUpdateError("Price (excl. VAT) cannot be negative.")

    if auto_vat:
        incl = calculate_incl_vat(excl)
    else:
        try:
            incl = parse_money(raw_incl)
        except InvalidOperation as e:
            raise PriceUpdateError("Price (incl. VAT) is not a valid number.") from e
        if incl is None:
            raise PriceUpdateError("Price (incl. VAT) is required when auto-VAT is off.")
        if incl < 0:
            raise PriceUpdateError("Price (incl. VAT) cannot be negative.")
        if incl < excl:
            raise PriceUpdateError("Price (incl. VAT) must be greater than or equal to price (excl. VAT).")

    before = {
        "price_excl_vat": str(paint.price_excl_vat),
        "price_incl_vat": str(paint.price_incl_vat),
    }
    paint.price_excl_vat = quantize_money(excl)
    paint.price_incl_vat = quantize_money(incl)
    paint.full_clean(exclude=["image"])
    paint.save(update_fields=["price_excl_vat", "price_incl_vat", "updated_at"])
    after = {
        "price_excl_vat": str(paint.price_excl_vat),
        "price_incl_vat": str(paint.price_incl_vat),
    }
    return before, after
