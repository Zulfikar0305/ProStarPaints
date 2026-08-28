from django import forms

from .models import SpecificationTemplate
from .models import KnowledgeEntry, KnowledgeCategory, SpecificationRule
from .services.template_service import TemplateService


class SpecificationTemplateForm(forms.ModelForm):
    cover_page = forms.CharField(widget=forms.Textarea(attrs={"rows":4}), required=False)
    document_title = forms.CharField(required=False)
    introduction = forms.CharField(widget=forms.Textarea(attrs={"rows":4}), required=False)
    header = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    footer = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    closing_statement = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    company_info = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    logo_options = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)
    typography = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)
    colours = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)
    spacing = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)

    class Meta:
        model = SpecificationTemplate
        fields = ["name", "key", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfg = getattr(self.instance, "config", {}) or {}
        # populate initial values from the JSON config
        self.fields["cover_page"].initial = cfg.get("cover_page", "")
        self.fields["document_title"].initial = cfg.get("document_title", "")
        self.fields["introduction"].initial = cfg.get("introduction", "")
        self.fields["header"].initial = cfg.get("header", "")
        self.fields["footer"].initial = cfg.get("footer", "")
        self.fields["closing_statement"].initial = cfg.get("closing_statement", "")
        self.fields["company_info"].initial = cfg.get("company_info", "")
        self.fields["logo_options"].initial = cfg.get("logo_options", "")
        self.fields["typography"].initial = cfg.get("typography", "")
        self.fields["colours"].initial = cfg.get("colours", "")
        self.fields["spacing"].initial = cfg.get("spacing", "")

        self.report_control_definitions = [
            {"key": "show_photos", "label": "Photos"},
            {"key": "show_moisture_reading", "label": "Moisture Reading"},
            {"key": "show_preparation_requirements", "label": "Preparation Requirements"},
            {"key": "show_coating_system", "label": "Coating System"},
            {"key": "show_tds", "label": "Technical Data / TDS"},
            {"key": "show_product_table", "label": "Product Table"},
            {"key": "show_pricing", "label": "Pricing"},
            {"key": "show_warranty", "label": "Warranty"},
            {"key": "show_recommendations", "label": "Recommendations"},
            {"key": "show_notes", "label": "Notes"},
        ]
        report_controls = TemplateService.normalize_report_controls(cfg.get("report_controls"))
        self.report_controls_ui = []
        for ctrl in self.report_control_definitions:
            key = ctrl["key"]
            self.report_controls_ui.append({
                "key": key,
                "label": ctrl["label"],
                "enabled": bool(report_controls.get(key, True)),
            })

        # Canonical document blocks that administrators may configure.
        # Keep this list conservative and stable; future packs may expand it.
        self.BLOCK_DEFINITIONS = [
            {"section_key": "cover", "display_name": "Cover"},
            {"section_key": "project_overview", "display_name": "Project Overview"},
            {"section_key": "general_notes", "display_name": "General Notes"},
            {"section_key": "surface_sections", "display_name": "Surface Sections"},
            {"section_key": "material_schedule", "display_name": "Material Schedule"},
            {"section_key": "recommendations", "display_name": "Recommendations"},
            {"section_key": "summary", "display_name": "Summary"},
            {"section_key": "disclaimer", "display_name": "Disclaimer"},
        ]

        # Build a lookup of existing section defaults from template config
        self.sections_initial = {}
        for s in cfg.get("sections", []) if isinstance(cfg.get("sections", []), list) else []:
            k = s.get("section_key")
            if k:
                self.sections_initial[str(k)] = s

        # UI-friendly list for template rendering: preserve display order
        self.sections_ui = []
        for blk in self.BLOCK_DEFINITIONS:
            key = blk.get("section_key")
            display = blk.get("display_name")
            init = self.sections_initial.get(str(key), {})
            visible = True if init.get("visible") is None else bool(init.get("visible"))
            heading = init.get("heading") or ""
            self.sections_ui.append({
                "section_key": key,
                "display_name": display,
                "visible": visible,
                "heading": heading,
            })

    def _report_controls_from_post(self):
        settings = {}
        for ctrl in getattr(self, "report_control_definitions", []):
            key = ctrl["key"]
            raw = self.data.get(f"report_control_{key}")
            settings[key] = raw in ("on", "true", "1", "yes", "True")
        return TemplateService.normalize_report_controls(settings)

    def save(self, commit=True):
        inst = super().save(commit=False)
        inst.config = {
            "cover_page": self.cleaned_data.get("cover_page", ""),
            "document_title": self.cleaned_data.get("document_title", ""),
            "introduction": self.cleaned_data.get("introduction", ""),
            "header": self.cleaned_data.get("header", ""),
            "footer": self.cleaned_data.get("footer", ""),
            "closing_statement": self.cleaned_data.get("closing_statement", ""),
            "company_info": self.cleaned_data.get("company_info", ""),
            "logo_options": self.cleaned_data.get("logo_options", ""),
            "typography": self.cleaned_data.get("typography", ""),
            "colours": self.cleaned_data.get("colours", ""),
            "spacing": self.cleaned_data.get("spacing", ""),
        }
        try:
            inst.config["report_controls"] = self._report_controls_from_post()
        except Exception:
            pass
        # Persist section defaults from POSTed form fields. The edit
        # template posts fields named `section_<key>_visible` and
        # `section_<key>_heading` for each canonical block.
        try:
            sections = []
            for blk in getattr(self, "BLOCK_DEFINITIONS", []):
                key = blk.get("section_key")
                if not key:
                    continue
                # Checkbox presence means visible; absence means False
                raw_vis = self.data.get(f"section_{key}_visible")
                visible = True if raw_vis in ("on", "true", "1") else False
                heading = self.data.get(f"section_{key}_heading")
                heading = heading if heading is not None and heading != "" else None
                sections.append({
                    "section_key": key,
                    "name": blk.get("display_name"),
                    "visible": visible,
                    "heading": heading,
                })
            inst.config["sections"] = sections
        except Exception:
            # Non-fatal: do not stop saving template if sections parsing fails
            pass
        if commit:
            inst.save()
        return inst



class KnowledgeEntryForm(forms.ModelForm):
    class Meta:
        model = KnowledgeEntry
        fields = ["title", "body", "category", "kind", "is_default", "is_active", "sort_order", "priority"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6}),
        }
    # Friendly tag input (comma-separated) and metadata JSON
    tags = forms.CharField(required=False, help_text="Comma-separated tags for filtering")
    metadata = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, help_text="Optional JSON metadata (advanced)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        data = getattr(self.instance, "tags", []) or []
        if isinstance(data, (list, tuple)):
            self.fields["tags"].initial = ", ".join([str(t) for t in data])
        else:
            self.fields["tags"].initial = str(data)

        meta = getattr(self.instance, "metadata", None) or {}
        try:
            import json

            self.fields["metadata"].initial = json.dumps(meta, ensure_ascii=False, indent=2)
        except Exception:
            self.fields["metadata"].initial = str(meta)

    def clean(self):
        data = super().clean()
        # ensure sort_order is non-negative
        so = data.get("sort_order")
        if so is None:
            data["sort_order"] = 0

        # Validate metadata JSON if provided
        raw_meta = self.cleaned_data.get("metadata")
        if raw_meta:
            try:
                import json

                parsed = json.loads(raw_meta)
                data["_parsed_metadata"] = parsed
            except Exception as exc:
                self.add_error("metadata", "Invalid JSON: %s" % exc)
        else:
            data["_parsed_metadata"] = {}

        return data

    def save(self, commit=True):
        inst = super().save(commit=False)
        # Parse tags
        raw_tags = self.cleaned_data.get("tags") or ""
        tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        inst.tags = tags_list

        # Attach parsed metadata
        inst.metadata = self.cleaned_data.get("_parsed_metadata", {}) or {}

        if commit:
            inst.save()
        return inst


class KnowledgeCategoryForm(forms.ModelForm):
    class Meta:
        model = KnowledgeCategory
        fields = ["name", "slug", "description"]


class SpecificationRuleForm(forms.ModelForm):
    class Meta:
        model = SpecificationRule
        fields = [
            "name",
            "rule_type",
            "min_value",
            "max_value",
            "unit",
            "notes",
            "active",
            "priority",
            "clauses",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "clauses" in self.fields:
            self.fields["clauses"].widget = forms.CheckboxSelectMultiple()
            self.fields["clauses"].help_text = "Select clauses applied when rule matches"
