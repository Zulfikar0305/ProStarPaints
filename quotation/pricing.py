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
