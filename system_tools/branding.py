"""
system_tools.branding
=====================
Single source of truth for resolving branding/business-identity values.

`get_branding()` returns a plain dict safe to drop into any template context.
It NEVER raises — if the DB row is missing, the table doesn't exist yet, or
the uploaded logo file is gone, callers always get usable defaults.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from django.templatetags.static import static

logger = logging.getLogger(__name__)


DEFAULT_COMPANY_NAME = "ProStar Paints"
_STATIC_LOGO_PATH = "images/prostar-logo.png"


def _safe_static(path: str) -> str:
    try:
        return static(path)
    except Exception:
        return f"/static/{path}"


def get_branding() -> dict[str, Any]:
    """
    Return the effective branding values as a dict.

    Keys:
        company_name, company_tagline, support_email, support_phone,
        website, pdf_footer_note, primary_colour, accent_colour,
        logo_url       — usable in HTML pages (uploaded MEDIA url or static fallback)
        has_custom_logo — True only if an uploaded ImageField file is present
    """
    fallback_logo = _safe_static(_STATIC_LOGO_PATH)
    base = {
        "company_name":     DEFAULT_COMPANY_NAME,
        "company_tagline":  "",
        "support_email":    "",
        "support_phone":    "",
        "website":          "",
        "pdf_footer_note":  "",
        "primary_colour":   "",
        "accent_colour":    "",
        "logo_url":         fallback_logo,
        "has_custom_logo":  False,
    }

    try:
        from .models import BrandingSetting
        obj = BrandingSetting.load()
    except Exception:
        # Table may not exist yet (e.g. during migrate). Use defaults.
        return base

    base["company_name"]    = obj.company_name or DEFAULT_COMPANY_NAME
    base["company_tagline"] = obj.company_tagline or ""
    base["support_email"]   = obj.support_email or ""
    base["support_phone"]   = obj.support_phone or ""
    base["website"]         = obj.website or ""
    base["pdf_footer_note"] = obj.pdf_footer_note or ""
    base["primary_colour"]  = obj.primary_colour or ""
    base["accent_colour"]   = obj.accent_colour or ""

    if obj.company_logo:
        try:
            url = obj.company_logo.url
            base["logo_url"] = url
            base["has_custom_logo"] = True
        except Exception:
            pass

    return base


def get_pdf_logo_data_uri() -> str | None:
    """
    Resolve the logo as a base64 data URI for PDF embedding.

    Uses the uploaded BrandingSetting.company_logo first, then falls back
    to the static prostar-logo.png. Returns None if neither is readable.
    """
    # 1. Try uploaded branding logo
    try:
        from .models import BrandingSetting
        obj = BrandingSetting.load()
        if obj.company_logo and obj.company_logo.name:
            try:
                path = obj.company_logo.path
            except (NotImplementedError, ValueError):
                path = None
            if path and os.path.exists(path):
                ext = (os.path.splitext(path)[1] or ".png").lower().lstrip(".")
                mime = {
                    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
                }.get(ext, "image/png")
                with open(path, "rb") as fh:
                    return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()
    except Exception:
        logger.exception("Failed to load uploaded branding logo for PDF")

    # 2. Fall back to static logo
    try:
        from django.contrib.staticfiles.finders import find as static_find
        logo_path = static_find(_STATIC_LOGO_PATH)
        if logo_path and os.path.exists(logo_path):
            with open(logo_path, "rb") as fh:
                return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except Exception:
        return None
    return None
