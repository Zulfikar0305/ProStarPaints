from typing import Any, Dict, Optional

from specifications.models import SpecificationTemplate

DEFAULT_REPORT_CONTROLS: Dict[str, bool] = {
    "show_photos": True,
    "show_moisture_reading": True,
    "show_preparation_requirements": True,
    "show_coating_system": True,
    "show_tds": True,
    "show_product_table": True,
    "show_pricing": True,
    "show_warranty": True,
    "show_recommendations": True,
    "show_notes": True,
}


class TemplateService:
    """Helpers to fetch and normalise SpecificationTemplate content.

    Returns a simple dict built from `SpecificationTemplate.config`.
    """

    @staticmethod
    def normalize_report_controls(raw: Any = None) -> Dict[str, bool]:
        """Normalise the canonical report-control schema for all templates."""
        defaults = dict(DEFAULT_REPORT_CONTROLS)
        source = raw if isinstance(raw, dict) else {}
        for key, default_value in DEFAULT_REPORT_CONTROLS.items():
            if key not in source:
                defaults[key] = bool(default_value)
                continue
            try:
                defaults[key] = bool(source.get(key))
            except Exception:
                defaults[key] = bool(default_value)
        return defaults

    @staticmethod
    def get_active_template(key: Optional[str] = None) -> SpecificationTemplate | None:
        if key:
            t = SpecificationTemplate.objects.filter(key=key, is_active=True).first()
            if t:
                return t

        # The automatic specification template is the canonical report source.
        # When present, prefer it over any newer but unrelated template so the
        # resolver, preview and export paths all read the same active defaults.
        auto_key = "automatic_specification"
        auto_template = SpecificationTemplate.objects.filter(key=auto_key, is_active=True).first()
        if auto_template:
            return auto_template

        return SpecificationTemplate.objects.filter(is_active=True).order_by("-created_at").first()

    @staticmethod
    def as_dict(template: SpecificationTemplate | None) -> dict:
        if not template:
            return {"report_controls": TemplateService.normalize_report_controls()}
        cfg = getattr(template, "config", None) or {}
        report_controls = TemplateService.normalize_report_controls(cfg.get("report_controls"))
        return {
            "cover_page": cfg.get("cover_page", ""),
            "document_title": cfg.get("document_title", ""),
            "introduction": cfg.get("introduction", ""),
            "header": cfg.get("header", ""),
            "footer": cfg.get("footer", ""),
            "closing_statement": cfg.get("closing_statement", ""),
            "company_info": cfg.get("company_info", ""),
            "logo_options": cfg.get("logo_options", ""),
            "typography": cfg.get("typography", ""),
            "colours": cfg.get("colours", ""),
            "spacing": cfg.get("spacing", ""),
            # Optional per-template section definitions. This may be an
            # array of section metadata objects describing default order,
            # headings and visibility. Keep optional for backwards
            # compatibility.
            "sections": cfg.get("sections", []),
            "report_controls": report_controls,
        }
