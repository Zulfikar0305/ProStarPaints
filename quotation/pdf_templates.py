"""
quotation.pdf_templates
=======================
Registry of available PDF output templates.

Each entry maps a template_key (safe, validated slug) to:
  - name           : human-readable template name
  - description    : one-line description shown on selection UI
  - template_path  : Django template path (relative to any app template dir)
  - preview_label  : short badge label for the selection card

Usage:
    from quotation.pdf_templates import PDF_TEMPLATES, get_template_config

SECURITY:
    Template keys are validated against this registry before use.
    No user-supplied template paths are ever accepted.
"""

from __future__ import annotations

PDF_TEMPLATES: dict[str, dict] = {
    "professional": {
        "name": "Professional Quotation",
        "description": "Clean, customer-facing quotation layout with branding, sections, and a professional signature block.",
        "template_path": "quotation/pdf/professional.html",
        "preview_label": "Recommended",
        "preview_icon": "bi-award-fill",
        "preview_color": "#7c3aed",
    },
    "detailed_spec": {
        "name": "Detailed Specification",
        "description": "Technical section-by-section specification sheet — includes surface type, conditions, coats, and paint details.",
        "template_path": "quotation/pdf/detailed_spec.html",
        "preview_label": "Technical",
        "preview_icon": "bi-list-columns-reverse",
        "preview_color": "#0f172a",
    },
    "compact": {
        "name": "Compact Estimate",
        "description": "Shorter one-page layout for fast quoting and overview presentations.",
        "template_path": "quotation/pdf/compact.html",
        "preview_label": "Fast",
        "preview_icon": "bi-lightning-charge-fill",
        "preview_color": "#059669",
    },
}


def get_template_config(template_key: str) -> dict:
    """
    Return the config dict for *template_key*.

    Raises KeyError if the key is not in the registry — callers must handle
    this and never fall back to an arbitrary file path.
    """
    if template_key not in PDF_TEMPLATES:
        raise KeyError(
            f"Unknown PDF template key: {template_key!r}. "
            f"Allowed keys: {list(PDF_TEMPLATES)}"
        )
    return PDF_TEMPLATES[template_key]
