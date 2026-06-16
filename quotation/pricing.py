from decimal import Decimal, ROUND_HALF_UP, localcontext
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

    # Obtain snapshot prices from the line_item (these represent the price for priced_volume_litres)
    price_excl_snapshot = line_item.price_excl_vat
    price_incl_snapshot = line_item.price_incl_vat

    paint = line_item.paint
    if paint is None:
        meta.update({
            "pricing_status": "pending",
            "pricing_pending_reason": "paint_not_matched",
        })
        line_item.metadata = meta
        line_item.save(update_fields=["metadata"])
        return line_item

    priced_volume = getattr(paint, "priced_volume_litres", None)
    spread_rate = getattr(paint, "spread_rate_per_litre", None)

    # Calculate
    calc = calculate_paint_pricing(
        price_excl_snapshot=price_excl_snapshot,
        price_incl_snapshot=price_incl_snapshot,
        priced_volume_litres=priced_volume,
        spread_rate_per_litre=spread_rate,
        area_sqm=line_item.area_sqm,
        coats=line_item.coats or 0,
    )

    # Update line item fields according to calc
    if calc["pricing_status"] == "priced":
        # quantity stored as litres (rounded to 2 dp to match model)
        qty = Decimal(calc["required_litres"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_item.quantity = qty
        line_item.unit = "L"
        # total values
        line_item.total_excl_vat = calc["total_excl_vat"]
        line_item.total_incl_vat = calc["total_incl_vat"]
    else:
        # Leave totals and quantity at zero/blank
        line_item.quantity = None
        line_item.unit = ""
        line_item.total_excl_vat = Decimal("0.00")
        line_item.total_incl_vat = Decimal("0.00")

    # Merge metadata snapshots (store Decimal as strings)
    meta.update({
        "pricing_status": calc.get("pricing_status"),
        "pricing_pending_reason": calc.get("pricing_pending_reason"),
        "spread_rate_per_litre": str(spread_rate) if spread_rate is not None else None,
        "priced_volume_litres": str(priced_volume) if priced_volume is not None else None,
        "required_litres": str(calc.get("required_litres")) if calc.get("required_litres") is not None else None,
        "price_per_litre_excl_vat": str(calc.get("price_per_litre_excl_vat")) if calc.get("price_per_litre_excl_vat") is not None else None,
        "price_per_litre_incl_vat": str(calc.get("price_per_litre_incl_vat")) if calc.get("price_per_litre_incl_vat") is not None else None,
        "rate_per_sqm_per_coat_excl_vat": str(calc.get("rate_per_sqm_per_coat_excl_vat")) if calc.get("rate_per_sqm_per_coat_excl_vat") is not None else None,
        "rate_per_sqm_selected_coats_excl_vat": str(calc.get("rate_per_sqm_selected_coats_excl_vat")) if calc.get("rate_per_sqm_selected_coats_excl_vat") is not None else None,
        "vat_amount": str(calc.get("vat_amount")) if calc.get("vat_amount") is not None else None,
    })

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
