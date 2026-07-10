from decimal import Decimal, ROUND_HALF_UP, localcontext, ROUND_CEILING
from typing import Optional

from django.db import transaction

from .models import Quotation, QuotationLineItem



def _quantize_money(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_paint_pricing(
    *,
    price_excl_snapshot: Optional[Decimal],
    price_incl_snapshot: Optional[Decimal],
    priced_volume_litres: Optional[Decimal],
    spread_rate_per_litre: Optional[Decimal],
    area_sqm: Optional[Decimal],
    coats: int,
) -> dict:
    """Calculate paint pricing values.

    Returns a dict with keys described in the project spec. Does not mutate DB.
    """
    ZERO = Decimal("0")
    result = {
        "price_per_litre_excl_vat": None,
        "price_per_litre_incl_vat": None,
        "required_litres": Decimal("0.00"),
        "rate_per_sqm_per_coat_excl_vat": None,
        "rate_per_sqm_selected_coats_excl_vat": None,
        "total_excl_vat": Decimal("0.00"),
        "total_incl_vat": Decimal("0.00"),
        "vat_amount": Decimal("0.00"),
        "pricing_status": "pending",
        "pricing_pending_reason": None,
    }

    # Basic validation: require positive price snapshots
    if (
        price_excl_snapshot is None
        or price_incl_snapshot is None
        or Decimal(price_excl_snapshot) <= ZERO
        or Decimal(price_incl_snapshot) <= ZERO
    ):
        result["pricing_pending_reason"] = "missing_price_snapshot"
        return result

    if priced_volume_litres is None or priced_volume_litres <= ZERO:
        result["pricing_pending_reason"] = "missing_priced_volume"
        return result

    if spread_rate_per_litre is None or spread_rate_per_litre <= ZERO:
        result["pricing_pending_reason"] = "missing_spread_rate"
        return result

    if area_sqm is None or area_sqm <= ZERO:
        result["pricing_pending_reason"] = "missing_area"
        return result

    if not isinstance(coats, int) or coats <= 0:
        result["pricing_pending_reason"] = "invalid_coats"
        return result

    # Perform intermediate calculations inside a local high-precision context
    try:
        with localcontext() as ctx:
            ctx.prec = 28
            price_per_litre_excl = (Decimal(price_excl_snapshot) / Decimal(priced_volume_litres))
            price_per_litre_incl = (Decimal(price_incl_snapshot) / Decimal(priced_volume_litres))

            # Required litres = area * coats / spread_rate
            required_litres = (Decimal(area_sqm) * Decimal(coats)) / Decimal(spread_rate_per_litre)

            # Rates per sqm (excl) per coat and selected coats (kept unquantized for metadata)
            rate_per_sqm_per_coat_excl = price_per_litre_excl / Decimal(spread_rate_per_litre)
            rate_per_sqm_selected_coats_excl = rate_per_sqm_per_coat_excl * Decimal(coats)

            # Totals (unquantized intermediate)
            total_excl = required_litres * price_per_litre_excl
            total_incl = required_litres * price_per_litre_incl
    except Exception:
        result["pricing_pending_reason"] = "calculation_error"
        return result

    # Quantize final stored money values, then compute VAT from those quantized values
    total_excl_q = _quantize_money(total_excl)
    total_incl_q = _quantize_money(total_incl)
    vat_amount_q = _quantize_money(total_incl_q - total_excl_q)

    # Quantize price-per-litre snapshots for presentation/snapshots
    price_per_litre_excl_q = _quantize_money(price_per_litre_excl)
    price_per_litre_incl_q = _quantize_money(price_per_litre_incl)

    result.update({
        "price_per_litre_excl_vat": price_per_litre_excl_q,
        "price_per_litre_incl_vat": price_per_litre_incl_q,
        "required_litres": required_litres,
        "rate_per_sqm_per_coat_excl_vat": rate_per_sqm_per_coat_excl,
        "rate_per_sqm_selected_coats_excl_vat": rate_per_sqm_selected_coats_excl,
        "total_excl_vat": total_excl_q,
        "total_incl_vat": total_incl_q,
        "vat_amount": vat_amount_q,
        "pricing_status": "priced",
        "pricing_pending_reason": None,
    })

    return result


def apply_paint_pricing_to_line_item(line_item: QuotationLineItem) -> QuotationLineItem:
    """Apply paint pricing to a QuotationLineItem in-place and save it.

    Mutates and saves `line_item`. Preserves existing metadata keys and
    appends pricing snapshots. Returns the saved `line_item`.
    """
    # Snapshot existing metadata and preserve keys
    meta = dict(line_item.metadata or {})

    # Helper to JSON-safe-serialize Decimals and other values
    def _to_json_safe(v):
        if isinstance(v, Decimal):
            return str(v)
        return v

    # Load or build immutable product snapshot
    product_snapshot = meta.get("product_snapshot")
    paint = line_item.paint
    created_snapshot = False

    if product_snapshot is None:
        # If no linked paint, we cannot build a product snapshot from catalogue
        if paint is None:
            # Backward-compatibility: existing callers previously used "paint_not_matched",
            # Pack 4B2 uses explicit missing_product_snapshot reason for clarity.
            meta.update({
                "pricing_status": "pending",
                "pricing_pending_reason": "missing_product_snapshot",
            })
            # Clear numeric totals/quantity
            line_item.quantity = None
            line_item.unit = ""
            line_item.total_excl_vat = Decimal("0.00")
            line_item.total_incl_vat = Decimal("0.00")
            line_item.metadata = meta
            line_item.save(update_fields=["quantity", "unit", "total_excl_vat", "total_incl_vat", "metadata"])
            return line_item

        # Build snapshot once from line-item price fields and paint non-price attrs
        product_snapshot = {
            "paint_pk": int(paint.pk) if paint and paint.pk is not None else None,
            "pricing_method": str(paint.pricing_method),
            "category": str(paint.category),
            "price_excl_vat": _to_json_safe(line_item.price_excl_vat),
            "price_incl_vat": _to_json_safe(line_item.price_incl_vat),
            "priced_volume_litres": _to_json_safe(getattr(paint, "priced_volume_litres", None)),
            "spread_rate_per_litre": _to_json_safe(getattr(paint, "spread_rate_per_litre", None)),
            "package_size": _to_json_safe(getattr(paint, "package_size", None)),
            "package_unit": str(getattr(paint, "package_unit", "")),
            "variant_label": str(getattr(paint, "variant_label", "")),
            "predetermined_note": str(getattr(paint, "predetermined_note", "")),
            "standard_coats": int(getattr(paint, "standard_coats", None)) if getattr(paint, "standard_coats", None) is not None else None,
            "finish": str(getattr(paint, "finish", None)) if getattr(paint, "finish", None) is not None else None,
            "base_type": str(getattr(paint, "base_type", None)) if getattr(paint, "base_type", None) is not None else None,
        }

        # Backwards-compatibility: some historical rows stored top-level
        # area/packaging/pricing keys directly in line_item.metadata instead
        # of inside a nested `product_snapshot`. When creating a new snapshot
        # for legacy rows, prefer preserved metadata values where present so
        # recalculation reproduces previously persisted behaviour.
        for legacy_key in ("package_size", "package_unit", "spread_rate_per_litre", "priced_volume_litres", "price_excl_vat", "price_incl_vat"):
            if meta.get(legacy_key) is not None:
                product_snapshot[legacy_key] = _to_json_safe(meta.get(legacy_key))
        # Persist immutable snapshot into metadata
        meta["product_snapshot"] = product_snapshot
        created_snapshot = True

    # Prepare a calculation snapshot (do not mutate stored JSON snapshot)
    calc_snapshot = dict(product_snapshot)

    # Pricing snapshot prices: if we just created the snapshot, the prices
    # were sourced from the line_item at creation time. For existing snapshots
    # we MUST NOT override the snapshot prices - the stored snapshot is
    # authoritative for repricing. Only override when snapshot was just built.
    if created_snapshot:
        calc_snapshot["price_excl_vat"] = _to_json_safe(line_item.price_excl_vat)
        calc_snapshot["price_incl_vat"] = _to_json_safe(line_item.price_incl_vat)

    # Convert numeric strings back to Decimal where required by dispatcher
    def _maybe_decimal(v):
        if v is None:
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    calc_snapshot_conv = dict(calc_snapshot)
    # Convert numeric-string fields to Decimal for calculation; keep other fields as-is
    calc_snapshot_conv["price_excl_vat"] = _maybe_decimal(calc_snapshot.get("price_excl_vat"))
    calc_snapshot_conv["price_incl_vat"] = _maybe_decimal(calc_snapshot.get("price_incl_vat"))
    calc_snapshot_conv["priced_volume_litres"] = _maybe_decimal(calc_snapshot.get("priced_volume_litres"))
    calc_snapshot_conv["spread_rate_per_litre"] = _maybe_decimal(calc_snapshot.get("spread_rate_per_litre"))
    calc_snapshot_conv["package_size"] = _maybe_decimal(calc_snapshot.get("package_size"))

    # Determine method-specific inputs from metadata per spec
    pricing_method = calc_snapshot.get("pricing_method")
    package_count = meta.get("package_count")
    roll_count = meta.get("roll_count")

    # Call the canonical dispatcher
    try:
        if pricing_method == "AREA_COATING":
            result = calculate_product_pricing(
                calc_snapshot_conv,
                area_sqm=line_item.area_sqm,
                coats=line_item.coats,
            )
        elif pricing_method == "FIXED_PACK":
            result = calculate_product_pricing(calc_snapshot_conv, package_count=package_count)
        elif pricing_method == "PER_METRE":
            result = calculate_product_pricing(calc_snapshot_conv, roll_count=roll_count)
        elif pricing_method == "NOTE_ONLY":
            result = calculate_product_pricing(calc_snapshot_conv)
        else:
            result = _pending_result("unsupported_pricing_method")
    except Exception:
        result = _pending_result("calculation_error")

    # Apply result to line_item fields per spec
    if result.get("pricing_status") == "priced":
        qty = result.get("quantity")
        if qty is not None:
            # Quantize to two decimal places for DB field
            try:
                q = Decimal(qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception:
                q = None
            line_item.quantity = q
        else:
            line_item.quantity = None
        line_item.unit = result.get("unit") or ""
        line_item.total_excl_vat = result.get("total_excl_vat") or Decimal("0.00")
        line_item.total_incl_vat = result.get("total_incl_vat") or Decimal("0.00")
    else:
        # Pending: clear prior numeric values
        line_item.quantity = None
        line_item.unit = ""
        line_item.total_excl_vat = Decimal("0.00")
        line_item.total_incl_vat = Decimal("0.00")

    # Merge metadata: preserve unrelated keys
    # Update common keys
    meta["pricing_method"] = pricing_method
    meta["pricing_status"] = result.get("pricing_status")
    meta["pricing_pending_reason"] = result.get("pricing_pending_reason")
    # VAT amount in metadata (string or None)
    meta["vat_amount"] = _to_json_safe(result.get("vat_amount")) if result.get("vat_amount") is not None else None

    # Merge method-specific metadata safely (JSON-serializing Decimals)
    # Preserve legacy AREA_COATING keys and ensure they are overwritten appropriately
    if pricing_method == "AREA_COATING":
        # Clear or set area-specific keys
        area_keys = [
            "spread_rate_per_litre",
            "priced_volume_litres",
            "required_litres",
            "price_per_litre_excl_vat",
            "price_per_litre_incl_vat",
            "rate_per_sqm_per_coat_excl_vat",
            "rate_per_sqm_selected_coats_excl_vat",
            "recommended_containers",
            "package_size",
            "package_unit",
            "vat_amount",
        ]
        # Populate from result or set to None when pending. Use top-level result
        # value OR fall back to result["metadata"][key] when the top-level
        # value is absent. This keeps the pricing dispatcher contract
        # unchanged while ensuring metadata promotion works when calculators
        # place values inside the nested metadata dict.
        for k in area_keys:
            val = result.get(k)
            if val is None:
                val = (result.get("metadata") or {}).get(k)
            meta[k] = _to_json_safe(val) if val is not None else None

    if pricing_method == "FIXED_PACK":
        # package_count may come from metadata (user input)
        meta["package_count"] = _to_json_safe(meta.get("package_count")) if meta.get("package_count") is not None else None
        meta["package_size"] = _to_json_safe(product_snapshot.get("package_size")) if product_snapshot.get("package_size") is not None else None
        meta["package_unit"] = _to_json_safe(product_snapshot.get("package_unit"))
        meta["variant_label"] = _to_json_safe(product_snapshot.get("variant_label"))
        # price per package from result extras; clear to None when pending
        val = result.get("price_per_package_excl_vat")
        meta["price_per_package_excl_vat"] = _to_json_safe(val) if val is not None else None
        val = result.get("price_per_package_incl_vat")
        meta["price_per_package_incl_vat"] = _to_json_safe(val) if val is not None else None

    if pricing_method == "PER_METRE":
        meta["roll_count"] = _to_json_safe(meta.get("roll_count")) if meta.get("roll_count") is not None else None
        meta["variant_label"] = _to_json_safe(product_snapshot.get("variant_label"))
        # price per metre from result extras; clear to None when pending
        val = result.get("price_per_metre_excl_vat")
        meta["price_per_metre_excl_vat"] = _to_json_safe(val) if val is not None else None
        val = result.get("price_per_metre_incl_vat")
        meta["price_per_metre_incl_vat"] = _to_json_safe(val) if val is not None else None

    if pricing_method == "NOTE_ONLY":
        # Ensure predetermined note remains
        meta["predetermined_note"] = _to_json_safe(product_snapshot.get("predetermined_note"))

    # Ensure product_snapshot stored (unchanged) and JSON-safe
    meta["product_snapshot"] = product_snapshot

    # Write back metadata and save
    line_item.metadata = meta
    line_item.save(update_fields=["quantity", "unit", "total_excl_vat", "total_incl_vat", "metadata"])
    return line_item


def recalculate_quotation_totals(quotation: Quotation) -> Quotation:
    """Recalculate and write cached totals on the Quotation from its line items."""
    from decimal import Decimal

    items = QuotationLineItem.objects.filter(quotation=quotation)
    subtotal = Decimal("0.00")
    total_incl = Decimal("0.00")
    for li in items:
        subtotal += Decimal(li.total_excl_vat or 0)
        total_incl += Decimal(li.total_incl_vat or 0)

    vat_amount = total_incl - subtotal

    quotation.subtotal_excl_vat = _quantize_money(Decimal(subtotal))
    quotation.vat_amount = _quantize_money(Decimal(vat_amount))
    quotation.total_incl_vat = _quantize_money(Decimal(total_incl))
    quotation.save(update_fields=["subtotal_excl_vat", "vat_amount", "total_incl_vat"])
    return quotation
# ---------------------------------------------------------------------------
# Pure calculators + dispatcher (Pack 4B1)
# ---------------------------------------------------------------------------
def _to_decimal(value):
    """Convert common numeric inputs to Decimal without mutating inputs.

    Returns None when value is None. Uses string conversion to avoid
    accidental float binary artifacts when callers pass numeric literals.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _is_positive_whole_number(value) -> tuple[bool, Decimal | None]:
    """Return (is_valid, integral_decimal) for positive whole-number check.

    Accepts ints or Decimal-like values. Does not accept fractional values.
    """
    if value is None:
        return False, None
    try:
        d = _to_decimal(value)
        if d is None:
            return False, None
        if d != d.to_integral_value():
            return False, d
        return (d > 0), d.to_integral_value()
    except Exception:
        return False, None


def _pending_result(reason: str) -> dict:
    """Standard pending result dictionary per Pack 4B1 common contract."""
    return {
        "pricing_method": None,
        "pricing_status": "pending",
        "pricing_pending_reason": reason,
        "quantity": None,
        "unit": "",
        "total_excl_vat": Decimal("0.00"),
        "total_incl_vat": Decimal("0.00"),
        "vat_amount": Decimal("0.00"),
        "metadata": {},
    }


def _priced_result_common(**kwargs) -> dict:
    """Build a common priced result ensuring VAT invariant and quantization.

    Expects Decimal-typed totals in kwargs: total_excl_vat, total_incl_vat.
    """
    total_excl = kwargs.get("total_excl_vat") or Decimal("0.00")
    total_incl = kwargs.get("total_incl_vat") or Decimal("0.00")
    # Quantize final money values
    total_excl_q = _quantize_money(total_excl)
    total_incl_q = _quantize_money(total_incl)
    vat_q = _quantize_money(total_incl_q - total_excl_q)

    res = {
        "pricing_method": kwargs.get("pricing_method"),
        "pricing_status": "priced",
        "pricing_pending_reason": None,
        "quantity": kwargs.get("quantity"),
        "unit": kwargs.get("unit", ""),
        "total_excl_vat": total_excl_q,
        "total_incl_vat": total_incl_q,
        "vat_amount": vat_q,
        "metadata": kwargs.get("metadata", {}),
    }
    # Merge any extra provided keys (e.g. package_count, price_per_metre...)
    extras = kwargs.get("extras") or {}
    res.update(extras)
    return res


def _calculate_fixed_pack_from_snapshot(snapshot: dict, package_count) -> dict:
    # Validate price snapshots
    price_excl = _to_decimal(snapshot.get("price_excl_vat"))
    price_incl = _to_decimal(snapshot.get("price_incl_vat"))
    if price_excl is None or price_incl is None or price_excl <= Decimal("0") or price_incl <= Decimal("0"):
        return _pending_result("missing_price_snapshot")

    # Validate package_count
    ok, pc_int = _is_positive_whole_number(package_count)
    if package_count is None:
        return _pending_result("missing_package_count")
    if not ok:
        return _pending_result("invalid_package_count")

    # Arithmetic
    total_excl = pc_int * price_excl
    total_incl = pc_int * price_incl

    metadata = {
        "package_count": pc_int,
        "package_size": _to_decimal(snapshot.get("package_size")),
        "package_unit": snapshot.get("package_unit"),
        "variant_label": snapshot.get("variant_label"),
    }

    extras = {
        "package_count": pc_int,
        "package_size": _to_decimal(snapshot.get("package_size")),
        "package_unit": snapshot.get("package_unit"),
        "price_per_package_excl_vat": price_excl,
        "price_per_package_incl_vat": price_incl,
    }

    return _priced_result_common(
        pricing_method="FIXED_PACK",
        quantity=pc_int,
        unit="pack",
        total_excl_vat=total_excl,
        total_incl_vat=total_incl,
        metadata=metadata,
        extras=extras,
    )


def _calculate_per_metre_from_snapshot(snapshot: dict, roll_count) -> dict:
    price_excl = _to_decimal(snapshot.get("price_excl_vat"))
    price_incl = _to_decimal(snapshot.get("price_incl_vat"))
    if price_excl is None or price_incl is None or price_excl <= Decimal("0") or price_incl <= Decimal("0"):
        return _pending_result("missing_price_snapshot")

    ok, rc_int = _is_positive_whole_number(roll_count)
    if roll_count is None:
        return _pending_result("missing_roll_count")
    if not ok:
        return _pending_result("invalid_roll_count")

    total_excl = rc_int * price_excl
    total_incl = rc_int * price_incl

    metadata = {
        "roll_count": rc_int,
        "variant_label": snapshot.get("variant_label"),
        "price_per_metre_excl_vat": price_excl,
        "price_per_metre_incl_vat": price_incl,
    }

    extras = {
        "roll_count": rc_int,
        "price_per_metre_excl_vat": price_excl,
        "price_per_metre_incl_vat": price_incl,
    }

    return _priced_result_common(
        pricing_method="PER_METRE",
        quantity=rc_int,
        unit="m",
        total_excl_vat=total_excl,
        total_incl_vat=total_incl,
        metadata=metadata,
        extras=extras,
    )


def _calculate_note_only_from_snapshot(snapshot: dict) -> dict:
    note = snapshot.get("predetermined_note")
    if not (note and str(note).strip()):
        return _pending_result("missing_predetermined_note")

    metadata = {"predetermined_note": note}
    res = _priced_result_common(
        pricing_method="NOTE_ONLY",
        quantity=None,
        unit="",
        total_excl_vat=Decimal("0.00"),
        total_incl_vat=Decimal("0.00"),
        metadata=metadata,
        extras={"predetermined_note": note},
    )
    return res


def calculate_product_pricing(
    product_snapshot,
    *,
    area_sqm=None,
    coats=None,
    package_count=None,
    roll_count=None,
) -> dict:
    """Pure dispatcher that prices a product snapshot without DB access.

    Routes to the appropriate calculator based on `pricing_method` and
    returns a consistent dictionary as described in Pack 4B1.
    """
    # Defensive: do not mutate snapshot
    pm = product_snapshot.get("pricing_method")
    # AREA_COATING delegates to existing calculate_paint_pricing
    if pm == "AREA_COATING":
        # Extract and coerce necessary snapshot fields
        price_excl_snapshot = _to_decimal(product_snapshot.get("price_excl_vat"))
        price_incl_snapshot = _to_decimal(product_snapshot.get("price_incl_vat"))
        priced_volume_litres = _to_decimal(product_snapshot.get("priced_volume_litres"))
        spread_rate_per_litre = _to_decimal(product_snapshot.get("spread_rate_per_litre"))
        area_sqm_dec = _to_decimal(area_sqm)
        category = product_snapshot.get("category")

        # Primer/Waterproofing special rules
        if category in ("PRIMER", "WATERPROOFING"):
            if coats is None:
                used_coats = 1
            else:
                # supplied value must equal 1
                try:
                    if int(coats) != 1:
                        return _pending_result("invalid_coats")
                    used_coats = 1
                except Exception:
                    return _pending_result("invalid_coats")
        else:
            # For normal area-coating products, require explicit positive whole-number coats
            if coats is None:
                return _pending_result("invalid_coats")
            try:
                used_coats = int(coats)
                if used_coats <= 0:
                    return _pending_result("invalid_coats")
            except Exception:
                return _pending_result("invalid_coats")

        # Call existing area-calculator (preserves its own pending reasons)
        try:
            calc = calculate_paint_pricing(
                price_excl_snapshot=price_excl_snapshot,
                price_incl_snapshot=price_incl_snapshot,
                priced_volume_litres=priced_volume_litres,
                spread_rate_per_litre=spread_rate_per_litre,
                area_sqm=area_sqm_dec,
                coats=used_coats,
            )
        except Exception:
            return _pending_result("calculation_error")

        # Build common result while preserving AREA_COATING keys
        status = calc.get("pricing_status", "pending")
        if status != "priced":
            # Ensure pending shape conforms to common contract
            pr = _pending_result(calc.get("pricing_pending_reason"))
            # Preserve area-specific metadata keys where useful
            pr.update({
                "pricing_method": "AREA_COATING",
                "metadata": {
                    "spread_rate_per_litre": _to_decimal(product_snapshot.get("spread_rate_per_litre")),
                    "priced_volume_litres": _to_decimal(product_snapshot.get("priced_volume_litres")),
                },
            })
            # Merge area keys (keep Decimal types)
            for k in ("price_per_litre_excl_vat", "price_per_litre_incl_vat", "required_litres", "rate_per_sqm_per_coat_excl_vat", "rate_per_sqm_selected_coats_excl_vat"):
                if k in calc:
                    pr[k] = calc.get(k)
            return pr

        # Priced path: propagate area calc values and metadata
        metadata = {
            "spread_rate_per_litre": _to_decimal(product_snapshot.get("spread_rate_per_litre")),
            "priced_volume_litres": _to_decimal(product_snapshot.get("priced_volume_litres")),
            "required_litres": calc.get("required_litres"),
            "price_per_litre_excl_vat": calc.get("price_per_litre_excl_vat"),
            "price_per_litre_incl_vat": calc.get("price_per_litre_incl_vat"),
            "rate_per_sqm_per_coat_excl_vat": calc.get("rate_per_sqm_per_coat_excl_vat"),
            "rate_per_sqm_selected_coats_excl_vat": calc.get("rate_per_sqm_selected_coats_excl_vat"),
        }

        # Recommended containers and pack-based pricing: if package size is provided (litres),
        # compute how many packages are required to cover the required litres (ceiling division)
        # and charge using whole saleable packs. Falls back to litre-based pricing when no
        # suitable package information is present.
        # Determine package size: prefer explicit package_size, but fallback
        # to priced_volume_litres when package_size is not present. Some
        # catalogue products store their package volume in
        # `priced_volume_litres` (e.g. 20.00 for a 20L drum).
        package_size = _to_decimal(product_snapshot.get("package_size"))
        if package_size is None:
            package_size = _to_decimal(product_snapshot.get("priced_volume_litres"))
        package_unit = product_snapshot.get("package_unit")

        req = calc.get("required_litres")

        if package_size is not None and package_size > 0 and req is not None:
            try:
                # Derive package price from the authoritative product snapshot.
                # product_snapshot.price_excl_vat is the price for
                # product_snapshot.priced_volume_litres. Scale that price
                # to the configured package_size to obtain the package price.
                snap_price_excl = _to_decimal(product_snapshot.get("price_excl_vat"))
                snap_price_incl = _to_decimal(product_snapshot.get("price_incl_vat"))
                snap_priced_vol = _to_decimal(product_snapshot.get("priced_volume_litres"))

                price_per_package_excl = None
                price_per_package_incl = None
                # Use product catalogue selling price as the package price.
                # Do NOT derive package price by scaling by litres.
                if snap_price_excl is not None:
                    price_per_package_excl = snap_price_excl
                    price_per_package_incl = snap_price_incl
                # Do NOT derive package price by scaling price-per-litre. The
                # product catalogue value (`price_excl_vat`) is the authoritative
                # selling price for the package. If it's missing, we fall back to
                # litre-based pricing (do not invent a package price).

                # Ceiling division to determine number of packs required
                packs_needed = (req / package_size).to_integral_value(rounding=ROUND_CEILING)

                # Totals priced by whole packages (fall back to litre-based calc if package price missing)
                total_excl = (price_per_package_excl * packs_needed) if price_per_package_excl is not None else calc.get("total_excl_vat")
                total_incl = (price_per_package_incl * packs_needed) if price_per_package_incl is not None else calc.get("total_incl_vat")

                # Populate metadata and extras (store recommended_containers as string
                # for JSON-friendly legacy metadata expectations)
                metadata["recommended_containers"] = str(packs_needed)
                metadata["package_size"] = package_size
                metadata["package_unit"] = package_unit

                # Only expose price-per-litre when the product itself is a 1L product
                price_per_litre_excl = calc.get("price_per_litre_excl_vat") if snap_priced_vol == Decimal("1") else None
                price_per_litre_incl = calc.get("price_per_litre_incl_vat") if snap_priced_vol == Decimal("1") else None

                extras = {
                    "price_per_litre_excl_vat": price_per_litre_excl,
                    "price_per_litre_incl_vat": price_per_litre_incl,
                    "required_litres": calc.get("required_litres"),
                    "rate_per_sqm_per_coat_excl_vat": calc.get("rate_per_sqm_per_coat_excl_vat"),
                    "rate_per_sqm_selected_coats_excl_vat": calc.get("rate_per_sqm_selected_coats_excl_vat"),
                    "recommended_containers": str(packs_needed),
                    "package_size": package_size,
                    "package_unit": package_unit,
                    "price_per_package_excl_vat": price_per_package_excl,
                    "price_per_package_incl_vat": price_per_package_incl,
                }

                res = _priced_result_common(
                    pricing_method="AREA_COATING",
                    quantity=packs_needed,
                    unit="pack",
                    total_excl_vat=total_excl or Decimal("0.00"),
                    total_incl_vat=total_incl or Decimal("0.00"),
                    metadata=metadata,
                    extras=extras,
                )
                return res
            except Exception:
                # On any error fall back to litre-based priced result below
                pass

        # Default behaviour (no package information): maintain litre-based pricing
        res = _priced_result_common(
            pricing_method="AREA_COATING",
            quantity=calc.get("required_litres"),
            unit="L",
            total_excl_vat=calc.get("total_excl_vat") or Decimal("0.00"),
            total_incl_vat=calc.get("total_incl_vat") or Decimal("0.00"),
            metadata=metadata,
            extras={
                "price_per_litre_excl_vat": calc.get("price_per_litre_excl_vat"),
                "price_per_litre_incl_vat": calc.get("price_per_litre_incl_vat"),
                "required_litres": calc.get("required_litres"),
                "rate_per_sqm_per_coat_excl_vat": calc.get("rate_per_sqm_per_coat_excl_vat"),
                "rate_per_sqm_selected_coats_excl_vat": calc.get("rate_per_sqm_selected_coats_excl_vat"),
                "recommended_containers": metadata.get("recommended_containers"),
                "package_size": metadata.get("package_size"),
                "package_unit": metadata.get("package_unit"),
            },
        )
        return res

    if pm == "FIXED_PACK":
        return _calculate_fixed_pack_from_snapshot(product_snapshot, package_count)

    if pm == "PER_METRE":
        return _calculate_per_metre_from_snapshot(product_snapshot, roll_count)

    if pm == "NOTE_ONLY":
        return _calculate_note_only_from_snapshot(product_snapshot)

    return _pending_result("unsupported_pricing_method")
