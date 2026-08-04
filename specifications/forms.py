from django import forms

from .models import SpecificationTemplate
from .models import KnowledgeEntry, KnowledgeCategory, SpecificationRule


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
        fields = ["title", "body", "category", "kind", "is_default", "is_active", "sort_order"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6}),
        }

    def clean(self):
        data = super().clean()
        # ensure sort_order is non-negative
        so = data.get("sort_order")
        if so is None:
            data["sort_order"] = 0
        return data


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
