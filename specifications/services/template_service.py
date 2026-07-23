from typing import Optional

from specifications.models import SpecificationTemplate


class TemplateService:
    """Helpers to fetch and normalise SpecificationTemplate content.

    Returns a simple dict built from `SpecificationTemplate.config`.
    """

    @staticmethod
    def get_active_template(key: Optional[str] = None) -> SpecificationTemplate | None:
        if key:
            t = SpecificationTemplate.objects.filter(key=key, is_active=True).first()
            if t:
                return t
        return SpecificationTemplate.objects.filter(is_active=True).order_by("-created_at").first()

    @staticmethod
    def as_dict(template: SpecificationTemplate | None) -> dict:
        if not template:
            return {}
        cfg = getattr(template, "config", None) or {}
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
        }
