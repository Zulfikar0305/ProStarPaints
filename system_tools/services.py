"""
System Tools scan services — all read-only, no destructive DB operations.

Each public function returns:
    {
        "status":  "SUCCESS" | "WARNING" | "ERROR",
        "summary": str,
        "checks":  [{"label": str, "value": ..., "flag": bool, "note": str}, ...]
    }
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check(label: str, value, flag: bool = False, note: str = "") -> dict:
    return {"label": label, "value": value, "flag": flag, "note": note}


def _derive_status(checks: list) -> str:
    if any(c["flag"] for c in checks):
        return "WARNING"
    return "SUCCESS"


def _run_scan(scan_fn, *args, **kwargs) -> dict:
    """Wrap a scan so unexpected exceptions surface as ERROR results."""
    try:
        return scan_fn(*args, **kwargs)
    except Exception as exc:
        logger.exception("System tool scan failed: %s", scan_fn.__name__)
        return {
            "status": "ERROR",
            "summary": f"Scan failed with an unexpected error: {exc}",
            "checks": [],
        }


# ---------------------------------------------------------------------------
# Tool registry — maps slug → (display_name, service_function)
# ---------------------------------------------------------------------------

def _user_integrity_scan() -> dict:
    from users.models import User
    from audit.models import AuditLog

    checks = []

    active_admins = User.objects.filter(role=User.Role.ADMIN, is_active=True).count()
    checks.append(_check("Active admins", active_admins))

    active_reps = User.objects.filter(role=User.Role.REP, is_active=True).count()
    checks.append(_check("Active reps", active_reps))

    inactive_users = User.objects.filter(is_active=False).count()
    checks.append(_check("Inactive users", inactive_users))

    # Missing email
    missing_email = User.objects.filter(email="").count()
    checks.append(_check(
        "Users missing email", missing_email,
        flag=missing_email > 0,
        note="These users cannot receive email notifications." if missing_email else "",
    ))

    # Missing first or last name
    missing_name = User.objects.filter(first_name="").count() + User.objects.filter(last_name="").count()
    checks.append(_check(
        "Users with incomplete names", missing_name,
        flag=missing_name > 0,
        note="First or last name is blank." if missing_name else "",
    ))

    # Reps with no audit log activity
    rep_ids = set(User.objects.filter(role=User.Role.REP, is_active=True).values_list("id", flat=True))
    active_rep_ids = set(AuditLog.objects.filter(user_id__in=rep_ids).values_list("user_id", flat=True).distinct())
    idle_reps = len(rep_ids - active_rep_ids)
    checks.append(_check(
        "Active reps with no recorded activity", idle_reps,
        flag=idle_reps > 0,
        note="These reps have never triggered an audit event." if idle_reps else "",
    ))

    status = _derive_status(checks)
    flag_count = sum(1 for c in checks if c["flag"])
    summary = (
        f"Scan complete. {flag_count} item(s) need attention."
        if flag_count else "All user integrity checks passed."
    )
    return {"status": status, "summary": summary, "checks": checks}


def _paint_integrity_scan() -> dict:
    from paints.models import Paint
    from django.db.models import Q

    checks = []

    active_paints = Paint.objects.filter(is_active=True).count()
    checks.append(_check("Active paints", active_paints))

    inactive_paints = Paint.objects.filter(is_active=False).count()
    checks.append(_check("Inactive paints", inactive_paints))

    # Missing prices (null or zero)
    missing_prices = Paint.objects.filter(
        Q(price_excl_vat__isnull=True) | Q(price_incl_vat__isnull=True)
    ).count()
    checks.append(_check(
        "Paints with missing prices", missing_prices,
        flag=missing_prices > 0,
        note="price_excl_vat or price_incl_vat is NULL." if missing_prices else "",
    ))

    # incl_vat < excl_vat
    from django.db.models import F
    bad_prices = Paint.objects.filter(price_incl_vat__lt=F("price_excl_vat")).count()
    checks.append(_check(
        "Paints where incl. VAT price < excl. VAT price", bad_prices,
        flag=bad_prices > 0,
        note="Price data inconsistency detected." if bad_prices else "",
    ))

    # Missing category / type / base
    missing_category = Paint.objects.filter(category="").count()
    checks.append(_check(
        "Paints missing category", missing_category,
        flag=missing_category > 0,
    ))

    missing_type = Paint.objects.filter(paint_type="").count()
    checks.append(_check(
        "Paints missing paint type", missing_type,
        flag=missing_type > 0,
    ))

    missing_base = Paint.objects.filter(base_type="").count()
    checks.append(_check(
        "Paints missing base type", missing_base,
        flag=missing_base > 0,
    ))

    status = _derive_status(checks)
    flag_count = sum(1 for c in checks if c["flag"])
    summary = (
        f"Scan complete. {flag_count} item(s) need attention."
        if flag_count else "All paint integrity checks passed."
    )
    return {"status": status, "summary": summary, "checks": checks}


def _invoice_integrity_scan() -> dict:
    from invoices.models import Invoice
    from django.db.models import F, Q

    checks = []

    completed = Invoice.objects.filter(status=Invoice.Status.COMPLETED, is_removed=False).count()
    checks.append(_check("Completed invoices", completed))

    draft = Invoice.objects.filter(status=Invoice.Status.DRAFT, is_removed=False).count()
    checks.append(_check("Draft invoices", draft))

    cancelled = Invoice.objects.filter(status=Invoice.Status.CANCELLED, is_removed=False).count()
    checks.append(_check("Cancelled invoices", cancelled))

    removed = Invoice.objects.filter(is_removed=True).count()
    checks.append(_check("Removed invoices", removed))

    # Negative totals
    negative_totals = Invoice.objects.filter(
        Q(subtotal_excl_vat__lt=0) | Q(vat_amount__lt=0) | Q(total_incl_vat__lt=0)
    ).count()
    checks.append(_check(
        "Invoices with negative amounts", negative_totals,
        flag=negative_totals > 0,
        note="Financial data integrity issue." if negative_totals else "",
    ))

    # total_incl_vat < subtotal_excl_vat
    bad_totals = Invoice.objects.filter(total_incl_vat__lt=F("subtotal_excl_vat")).count()
    checks.append(_check(
        "Invoices where total (incl. VAT) < subtotal (excl. VAT)", bad_totals,
        flag=bad_totals > 0,
        note="Total should always be >= subtotal." if bad_totals else "",
    ))

    # Missing created_by
    missing_owner = Invoice.objects.filter(created_by__isnull=True).count()
    checks.append(_check(
        "Invoices missing created_by", missing_owner,
        flag=missing_owner > 0,
        note="Orphaned invoice records." if missing_owner else "",
    ))

    status = _derive_status(checks)
    flag_count = sum(1 for c in checks if c["flag"])
    summary = (
        f"Scan complete. {flag_count} item(s) need attention."
        if flag_count else "All invoice integrity checks passed."
    )
    return {"status": status, "summary": summary, "checks": checks}


def _audit_integrity_scan() -> dict:
    from audit.models import AuditLog

    checks = []

    total_logs = AuditLog.objects.count()
    checks.append(_check("Total audit log entries", total_logs))

    missing_user = AuditLog.objects.filter(user__isnull=True).count()
    checks.append(_check(
        "Audit logs missing user", missing_user,
        flag=False,  # expected for system actions; informational only
        note="These were logged without an authenticated user (system/anonymous)." if missing_user else "",
    ))

    missing_action = AuditLog.objects.filter(action="").count()
    checks.append(_check(
        "Audit logs missing action", missing_action,
        flag=missing_action > 0,
        note="Action field is blank — data quality issue." if missing_action else "",
    ))

    missing_module = AuditLog.objects.filter(module="").count()
    checks.append(_check(
        "Audit logs missing module", missing_module,
        flag=missing_module > 0,
        note="Module field is blank — data quality issue." if missing_module else "",
    ))

    status = _derive_status(checks)
    flag_count = sum(1 for c in checks if c["flag"])
    summary = (
        f"Scan complete. {flag_count} item(s) need attention."
        if flag_count else "All audit integrity checks passed."
    )
    return {"status": status, "summary": summary, "checks": checks}


# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, tuple[str, callable]] = {
    "user_integrity_scan": (
        "User Integrity Scan",
        lambda: _run_scan(_user_integrity_scan),
    ),
    "paint_integrity_scan": (
        "Paint Integrity Scan",
        lambda: _run_scan(_paint_integrity_scan),
    ),
    "invoice_integrity_scan": (
        "Invoice Integrity Scan",
        lambda: _run_scan(_invoice_integrity_scan),
    ),
    "audit_integrity_scan": (
        "Audit Integrity Scan",
        lambda: _run_scan(_audit_integrity_scan),
    ),
}


def run_tool(slug: str) -> dict | None:
    """
    Execute the tool identified by *slug*.
    Returns the result dict, or None if the slug is unknown.
    """
    entry = TOOL_REGISTRY.get(slug)
    if entry is None:
        return None
    _, fn = entry
    return fn()


def get_tool_display_name(slug: str) -> str:
    entry = TOOL_REGISTRY.get(slug)
    return entry[0] if entry else slug
