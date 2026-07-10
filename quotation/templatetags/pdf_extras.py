from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


_LABELS = {
    "spread_rate_per_litre": "Spread Rate (m²/L)",
    "required_litres": "Required Litres",
    "recommended_containers": "Package",
    "package_size": "Package Size",
    "package_unit": "Package Unit",
    "rate_per_sqm_selected_coats_excl_vat": "Rate (R/m²) excl. VAT",
    "price_per_litre_excl_vat": "Price per L (R) excl. VAT",
    "coverage": "Coverage",
    "est_material_cost": "Estimated Cost",
    "area": "Area",
    "coats": "Coats",
    "finish": "Finish",
    "product": "Product",
}


def _format_val(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, (list, tuple, set)):
        try:
            return ", ".join(str(x) for x in v if x is not None)
        except Exception:
            return str(v)
    if isinstance(v, dict):
        try:
            return ", ".join(f"{k}: {v[k]}" for k in v)
        except Exception:
            return str(v)
    try:
        # Monetary formatting for Decimal/float/int
        if isinstance(v, (Decimal, float, int)):
            d = Decimal(v)
            return f"R {d.quantize(Decimal('0.01')):,.2f}"
    except Exception:
        pass
    return str(v)


@register.filter
def render_technical(info: Any) -> str:
    """Render a technical info dict as a compact safe HTML table.

    The function is defensive: if a non-dict is passed it will be escaped
    and returned as plain text.
    """
    if not info:
        return ""
    if not isinstance(info, dict):
        return escape(str(info))

    rows = []
    # Preferred key order
    for key in _LABELS:
        if key in info:
            label = _LABELS.get(key, key)
            val = _format_val(info.get(key))
            rows.append(f"<tr><td class=\"k\">{escape(label)}</td><td class=\"v\">{escape(val)}</td></tr>")

    # Fallback: include any other keys not covered above
    for key in sorted(info.keys()):
        if key not in _LABELS:
            rows.append(f"<tr><td class=\"k\">{escape(key)}</td><td class=\"v\">{escape(_format_val(info.get(key)))}</td></tr>")

        html = f"""
<table class="tech-table" style="width:100%;border-collapse:collapse;font-size:9pt;margin:6px 0">
    {''.join(rows)}
</table>
"""
    return mark_safe(html)


def _format_package(p: Any) -> str:
    if p is None or p == "":
        return "—"
    if isinstance(p, (list, tuple, set)):
        return ", ".join(str(x) for x in p)
    return str(p)


@register.simple_tag
def render_coating_rows(coating_system: Any, technical: Any) -> str:
    """Render table rows for the requested coating_system list.

    Each coating_system entry is expected to be a dict with at least
    ``product``, ``finish``, ``coats`` and ``line_item_pk``. The ``technical``
    list can provide additional per-line metadata (e.g. spread rate) which is
    associated by `line_item_pk`.
    """
    if not coating_system:
        return ""

    tech_map = {}
    try:
        for t in technical or []:
            if isinstance(t, dict):
                pk = t.get("line_item_pk")
                tech_map[pk] = t.get("info")
    except Exception:
        tech_map = {}

    rows = []
    for m in coating_system:
        product = m.get("product") if isinstance(m, dict) else getattr(m, "product", None)
        finish = m.get("finish") if isinstance(m, dict) else getattr(m, "finish", None)
        coats = m.get("coats") if isinstance(m, dict) else getattr(m, "coats", None)
        pk = m.get("line_item_pk") if isinstance(m, dict) else getattr(m, "line_item_pk", None)

        tech = tech_map.get(pk) or {}
        spread = tech.get("spread_rate_per_litre") if isinstance(tech, dict) else None
        coverage = tech.get("coverage") if isinstance(tech, dict) else None
        required = (m.get("required_litres") if isinstance(m, dict) else getattr(m, "required_litres", None)) or tech.get("required_litres") if isinstance(tech, dict) else None

        spread_txt = f"{spread} m²/L" if spread is not None else "—"
        coverage_txt = _format_val(coverage) if coverage is not None else "—"
        required_txt = _format_val(required)

        rows.append(
            f"<tr>"
            f"<td>{escape(product or '—')}</td>"
            f"<td>{escape(finish or '—')}</td>"
            f"<td>{escape(str(coats) if coats is not None else '—')}</td>"
            f"<td>{escape(spread_txt)}</td>"
            f"<td>{escape(coverage_txt)}</td>"
            f"<td>{escape(required_txt)}</td>"
            f"</tr>"
        )

    return mark_safe("".join(rows))


@register.simple_tag
def render_material_schedule_rows(material_summary: Any, technical: Any) -> str:
    """Render rows for the material costing schedule.

    Columns: Product | Package | Coverage | Required Quantity | Estimated Cost
    """
    if not material_summary:
        return ""

    tech_map = {}
    try:
        for t in technical or []:
            if isinstance(t, dict):
                tech_map[t.get("line_item_pk")] = t.get("info")
    except Exception:
        tech_map = {}

    rows = []
    for m in material_summary:
        product = m.get("product") if isinstance(m, dict) else getattr(m, "product", None)
        package = m.get("recommended_containers") if isinstance(m, dict) else getattr(m, "recommended_containers", None)
        pk = m.get("line_item_pk") if isinstance(m, dict) else getattr(m, "line_item_pk", None)
        tech = tech_map.get(pk) or {}
        coverage = tech.get("coverage") if isinstance(tech, dict) else m.get("coverage")
        quantity = m.get("required_litres") if isinstance(m, dict) else getattr(m, "required_litres", None)
        est_cost = m.get("est_material_cost") if isinstance(m, dict) else getattr(m, "est_material_cost", None)

        est_text = _format_val(est_cost) if est_cost is not None else "—"

        rows.append(
            f"<tr>"
            f"<td>{escape(product or '—')}</td>"
            f"<td>{escape(_format_package(package))}</td>"
            f"<td>{escape(_format_val(coverage))}</td>"
            f"<td>{escape(_format_val(quantity))}</td>"
            f"<td>{escape(est_text)}</td>"
            f"</tr>"
        )

    return mark_safe("".join(rows))
