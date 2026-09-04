import json

from django import forms

from quotation.config import (
    ALL_GENERIC_SECTION_CONFIGS,
    FINISHES,
    GENERIC_SURFACE_CONDITIONS_FULL,
    OTHER_PREP_OPTIONS,
    PRIMER_OPTIONS,
    SURFACE_CONDITIONS,
    WALL_TYPES,
    WATERPROOFING_OPTIONS,
)
from quotation.services import ALL_SUBSECTIONS

from .models import SpecificationTemplate
from .models import KnowledgeEntry, KnowledgeCategory, SpecificationRule, SurfaceDefault
from .services.template_service import TemplateService

LEGACY_SURFACE_CONDITION_CHOICES = [
    ("new", "New surface"),
    ("previously_painted", "Previously painted"),
    ("cracks", "Cracks / holes"),
    ("peeling", "Peeling / flaking"),
    ("mould", "Mould / mildew"),
    ("efflorescence", "Efflorescence"),
    ("rough", "Rough / uneven surface"),
    ("stained", "Stained"),
]

SURFACE_CONDITION_CHOICES = list(dict.fromkeys(list(SURFACE_CONDITIONS) + LEGACY_SURFACE_CONDITION_CHOICES))


def _combine_surface_condition_choices(*groups):
    merged = []
    seen = set()
    for group in groups:
        for value, label in list(group or []):
            value_key = str(value)
            if value_key in seen:
                continue
            seen.add(value_key)
            merged.append((value, label))
    return merged


class CSVMultipleChoiceField(forms.MultipleChoiceField):
    def to_python(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            items = [part.strip() for part in value.split(",") if part.strip()]
            return items
        if isinstance(value, (list, tuple, set)):
            return [str(part).strip() for part in value if str(part).strip()]
        return [str(value).strip()] if str(value).strip() else []


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
    section_key = forms.ChoiceField(
        required=False,
        choices=[("", "---------")] + [(s.key, s.display_name) for s in sorted(ALL_SUBSECTIONS.values(), key=lambda s: s.display_name)],
        help_text="Which quote-builder subsection this guidance applies to.",
    )
    substrate_type = forms.ChoiceField(
        required=False,
        choices=[("", "---------"), ("INTERIOR", "Interior"), ("EXTERIOR", "Exterior")],
        help_text="Interior or exterior substrate context.",
    )
    types = CSVMultipleChoiceField(
        required=False,
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        help_text="Material or substrate family.",
    )
    surface_conditions = CSVMultipleChoiceField(
        required=False,
        choices=SURFACE_CONDITION_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Surface conditions this rule applies to.",
    )
    finishes = CSVMultipleChoiceField(
        required=False,
        choices=FINISHES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Applicable finishes.",
    )
    preparations = CSVMultipleChoiceField(
        required=False,
        choices=OTHER_PREP_OPTIONS,
        widget=forms.CheckboxSelectMultiple,
        help_text="Preparation work this applies to.",
    )
    preparation_requirements = CSVMultipleChoiceField(
        required=False,
        choices=OTHER_PREP_OPTIONS,
        widget=forms.CheckboxSelectMultiple,
        help_text="Structured preparation requirement labels for this selection.",
    )
    additional_preparation_notes = forms.CharField(
        required=False,
        label="Preparation",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Extra instructions for preparation, repairs, or substrate condition.",
    )
    application_method = forms.CharField(
        required=False,
        label="Application",
        help_text="Recommended application method or technique.",
    )
    coating_system_notes = forms.CharField(
        required=False,
        label="Coating System",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Coating system guidance for this selection.",
    )
    technical_notes = forms.CharField(
        required=False,
        label="Technical Information",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Technical notes, thresholds, or warnings for the selected section.",
    )
    drying_recoat_guidance = forms.CharField(
        required=False,
        label="Drying / Recoat",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Drying and recoat guidance for the chosen system.",
    )
    primers = CSVMultipleChoiceField(
        required=False,
        choices=PRIMER_OPTIONS,
        widget=forms.CheckboxSelectMultiple,
        help_text="Relevant primer / sealer options.",
    )
    waterproofing = CSVMultipleChoiceField(
        required=False,
        choices=WATERPROOFING_OPTIONS,
        widget=forms.CheckboxSelectMultiple,
        help_text="Relevant waterproofing guidance.",
    )
    moisture_min = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=2,
        help_text="Minimum moisture reading (%) allowed for this rule.",
    )
    moisture_max = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=2,
        help_text="Maximum moisture reading (%) allowed for this rule.",
    )
    application = forms.ChoiceField(
        required=False,
        choices=[("", "---------"), ("interior", "Interior"), ("exterior", "Exterior")],
        help_text="Application context.",
    )

    class Meta:
        model = KnowledgeEntry
        fields = ["title", "body", "category", "kind", "is_default", "is_active", "sort_order", "priority"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6}),
        }
    # Friendly tag input (comma-separated) and metadata JSON
    tags = forms.CharField(required=False, help_text="Comma-separated tags for filtering")
    metadata = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, help_text="Optional legacy JSON metadata (advanced fallback)")

    def _section_choices_for_substrate(self, substrate_type=None):
        substrate = (substrate_type or "").upper()
        choices = [("", "---------")]
        for subsection in sorted(ALL_SUBSECTIONS.values(), key=lambda s: (s.substrate, s.display_name)):
            if not substrate or subsection.substrate == substrate:
                choices.append((subsection.key, subsection.display_name))
        return choices

    def _section_choice_map(self):
        data = {}
        for subsection in sorted(ALL_SUBSECTIONS.values(), key=lambda item: (item.substrate, item.display_name)):
            data.setdefault(subsection.substrate, []).append({"value": subsection.key, "label": subsection.display_name})
        return data

    def _section_config_for_key(self, section_key=None):
        if section_key == "interior_walls":
            return {
                "types": WALL_TYPES,
                "surface_conditions": _combine_surface_condition_choices(
                    GENERIC_SURFACE_CONDITIONS_FULL,
                    LEGACY_SURFACE_CONDITION_CHOICES,
                ),
                "finishes": FINISHES,
                "substrate_type": "INTERIOR",
            }

        section_config = ALL_GENERIC_SECTION_CONFIGS.get(section_key)
        if section_config:
            return {
                "types": list(section_config.types),
                "surface_conditions": _combine_surface_condition_choices(
                    list(section_config.surface_conditions),
                    LEGACY_SURFACE_CONDITION_CHOICES,
                ),
                "finishes": list(section_config.finishes),
                "substrate_type": getattr(section_config, "substrate_type", "INTERIOR"),
            }

        return {"types": [], "surface_conditions": [], "finishes": [], "substrate_type": None}

    def _type_choices_for_section(self, section_key=None):
        return self._section_config_for_key(section_key).get("types", [])

    def _surface_condition_choices_for_section(self, section_key=None):
        return self._section_config_for_key(section_key).get("surface_conditions", [])

    def _finish_choices_for_section(self, section_key=None):
        return self._section_config_for_key(section_key).get("finishes", [])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.section_choice_map = self._section_choice_map()
        self.section_target_config = {
            key: {
                "types": [
                    {"value": value, "label": label}
                    for value, label in self._section_config_for_key(key)["types"]
                ],
                "surface_conditions": [
                    {"value": value, "label": label}
                    for value, label in self._section_config_for_key(key)["surface_conditions"]
                ],
                "finishes": [
                    {"value": value, "label": label}
                    for value, label in self._section_config_for_key(key)["finishes"]
                ],
            }
            for key in sorted(set(ALL_GENERIC_SECTION_CONFIGS) | {"interior_walls"})
        }

        initial_substrate = None
        initial_section = None
        if self.instance and getattr(self.instance, "metadata", None):
            initial_substrate = self.instance.metadata.get("substrate_type")
            initial_section = self.instance.metadata.get("section_key")
        if self.data.get("substrate_type"):
            initial_substrate = self.data.get("substrate_type")
        if self.data.get("section_key"):
            initial_section = self.data.get("section_key")

        if initial_substrate:
            self.fields["section_key"].choices = self._section_choices_for_substrate(initial_substrate)
        else:
            self.fields["section_key"].choices = self._section_choices_for_substrate()

        if initial_section:
            self.fields["types"].choices = self._type_choices_for_section(initial_section)
            self.fields["surface_conditions"].choices = self._surface_condition_choices_for_section(initial_section)
            self.fields["finishes"].choices = self._finish_choices_for_section(initial_section)
        else:
            self.fields["types"].choices = []
            self.fields["surface_conditions"].choices = []
            self.fields["finishes"].choices = []

        data = getattr(self.instance, "tags", []) or []
        if isinstance(data, (list, tuple)):
            self.fields["tags"].initial = ", ".join([str(t) for t in data])
        else:
            self.fields["tags"].initial = str(data)

        meta = getattr(self.instance, "metadata", None) or {}
        for field_name, meta_key in (
            ("section_key", "section_key"),
            ("substrate_type", "substrate_type"),
            ("application", "application"),
        ):
            if meta.get(meta_key):
                self.fields[field_name].initial = meta.get(meta_key)

        values = meta.get("types") or meta.get("type") or []
        if values:
            self.fields["types"].initial = list(values) if isinstance(values, (list, tuple, set)) else [values]
            self.fields["types"].choices = self._type_choices_for_section(meta.get("section_key"))

        for field_name, meta_key in (
            ("surface_conditions", "surface_conditions"),
            ("finishes", "finishes"),
            ("preparations", "preparations"),
            ("preparation_requirements", "preparation_requirements"),
            ("primers", "primers"),
            ("waterproofing", "waterproofing"),
        ):
            values = meta.get(meta_key) or []
            if values:
                self.fields[field_name].initial = list(values) if isinstance(values, (list, tuple, set)) else [values]

        for field_name, meta_key in (
            ("additional_preparation_notes", "additional_preparation_notes"),
            ("application_method", "application_method"),
            ("coating_system_notes", "coating_system_notes"),
            ("technical_notes", "technical_notes"),
            ("drying_recoat_guidance", "drying_recoat_guidance"),
            ("moisture_min", "moisture_min"),
            ("moisture_max", "moisture_max"),
        ):
            value = meta.get(meta_key)
            if value not in (None, ""):
                self.fields[field_name].initial = str(value)

        if meta.get("section_key"):
            self.fields["types"].choices = self._type_choices_for_section(meta.get("section_key"))
            self.fields["surface_conditions"].choices = self._surface_condition_choices_for_section(meta.get("section_key"))
            self.fields["finishes"].choices = self._finish_choices_for_section(meta.get("section_key"))
            self.fields["section_key"].choices = self._section_choices_for_substrate(meta.get("substrate_type"))

        try:
            self.fields["metadata"].initial = json.dumps(meta, ensure_ascii=False, indent=2)
        except Exception:
            self.fields["metadata"].initial = str(meta)

    @staticmethod
    def _coerce_multivalue(value):
        if value in (None, "", [], (), {}):
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(part).strip() for part in value if str(part).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def clean(self):
        data = super().clean()
        section_key = data.get("section_key")
        substrate_type = data.get("substrate_type")
        if section_key and substrate_type:
            config = self._section_config_for_key(section_key)
            expected_substrate = config.get("substrate_type")
            if expected_substrate and str(expected_substrate).upper() != str(substrate_type).upper():
                self.add_error("section_key", "This subsection does not belong to the selected main section.")
                self.add_error("substrate_type", "Choose a matching main section for this subsection.")

        so = data.get("sort_order")
        if so is None:
            data["sort_order"] = 0

        raw_meta = self.cleaned_data.get("metadata")
        parsed_meta = {}
        if raw_meta:
            try:
                parsed_meta = json.loads(raw_meta)
            except Exception as exc:
                self.add_error("metadata", "Invalid JSON: %s" % exc)
        if not isinstance(parsed_meta, dict):
            parsed_meta = {}

        explicit_values = {
            "section_key": self.cleaned_data.get("section_key"),
            "substrate_type": self.cleaned_data.get("substrate_type"),
            "types": self.cleaned_data.get("types"),
            "surface_conditions": self.cleaned_data.get("surface_conditions"),
            "finishes": self.cleaned_data.get("finishes"),
            "preparations": self.cleaned_data.get("preparations"),
            "preparation_requirements": self.cleaned_data.get("preparation_requirements"),
            "additional_preparation_notes": self.cleaned_data.get("additional_preparation_notes"),
            "application_method": self.cleaned_data.get("application_method"),
            "coating_system_notes": self.cleaned_data.get("coating_system_notes"),
            "technical_notes": self.cleaned_data.get("technical_notes"),
            "drying_recoat_guidance": self.cleaned_data.get("drying_recoat_guidance"),
            "primers": self.cleaned_data.get("primers"),
            "waterproofing": self.cleaned_data.get("waterproofing"),
            "moisture_min": self.cleaned_data.get("moisture_min"),
            "moisture_max": self.cleaned_data.get("moisture_max"),
            "application": self.cleaned_data.get("application"),
        }
        for key, value in explicit_values.items():
            if value not in (None, "", [], (), {}):
                if key in {"types", "surface_conditions", "finishes", "preparations", "preparation_requirements", "primers", "waterproofing"}:
                    parsed_meta[key] = self._coerce_multivalue(value)
                elif key in {"moisture_min", "moisture_max"} and value is not None:
                    parsed_meta[key] = str(value)
                else:
                    parsed_meta[key] = value

        if parsed_meta.get("preparations") and not parsed_meta.get("preparation_requirements"):
            parsed_meta["preparation_requirements"] = parsed_meta["preparations"]
        elif parsed_meta.get("preparation_requirements") and not parsed_meta.get("preparations"):
            parsed_meta["preparations"] = parsed_meta["preparation_requirements"]

        data["_parsed_metadata"] = parsed_meta
        return data

    def save(self, commit=True):
        inst = super().save(commit=False)
        raw_tags = self.cleaned_data.get("tags") or ""
        tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        inst.tags = tags_list

        parsed_meta = self.cleaned_data.get("_parsed_metadata", {}) or {}
        inst.metadata = parsed_meta

        if commit:
            inst.save()
        return inst


class SurfaceDefaultForm(forms.ModelForm):
    main_section = forms.ChoiceField(
        required=True,
        choices=[("", "---------"), ("INTERIOR", "Interior"), ("EXTERIOR", "Exterior")],
        help_text="The top-level ProStar section for this surface default.",
    )
    subsection = forms.ChoiceField(
        required=False,
        choices=[("", "---------")],
        help_text="The subsection within the selected main section.",
    )
    surface = forms.ChoiceField(
        required=False,
        choices=[("", "---------")],
        help_text="The exact leaf surface/material selection.",
    )
    preparation_requirements = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Reusable preparation requirements for this exact surface.",
    )
    surface_rules = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Reusable surface description or rules for this surface target.",
    )

    class Meta:
        model = SurfaceDefault
        fields = ["main_section", "subsection", "surface", "preparation_requirements", "surface_rules", "is_active"]

    def _subsection_choices_for_main_section(self, main_section=None):
        substrate = (main_section or "").upper()
        choices = [("", "---------")]
        for subsection in sorted(ALL_SUBSECTIONS.values(), key=lambda item: (item.substrate, item.display_name)):
            if not substrate or subsection.substrate == substrate:
                choices.append((subsection.key, subsection.display_name))
        return choices

    def _surface_choices_for_subsection(self, subsection=None):
        choices = [("", "---------")]
        section_key = subsection or ""
        config = ALL_GENERIC_SECTION_CONFIGS.get(section_key)
        if not config:
            if section_key == "interior_walls":
                config = type("_Cfg", (), {"types": WALL_TYPES})()
        if config:
            for value, label in getattr(config, "types", []) or []:
                choices.append((value, label))
        return choices

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.section_choice_map = {
            substrate: [
                {"value": subsection.key, "label": subsection.display_name}
                for subsection in sorted(ALL_SUBSECTIONS.values(), key=lambda item: (item.substrate, item.display_name))
                if subsection.substrate == substrate
            ]
            for substrate in ["INTERIOR", "EXTERIOR"]
        }
        self.surface_choice_map = {
            subsection.key: [
                {"value": value, "label": label}
                for value, label in self._surface_choices_for_subsection(subsection.key)[1:]
            ]
            for subsection in sorted(ALL_SUBSECTIONS.values(), key=lambda item: (item.substrate, item.display_name))
        }

        initial_main = None
        initial_section = None
        if self.instance and getattr(self.instance, "pk", None):
            initial_main = self.instance.main_section
            initial_section = self.instance.subsection
        if self.data.get("main_section"):
            initial_main = self.data.get("main_section")
        if self.data.get("subsection"):
            initial_section = self.data.get("subsection")

        if initial_main:
            self.fields["subsection"].choices = self._subsection_choices_for_main_section(initial_main)
        else:
            self.fields["subsection"].choices = self._subsection_choices_for_main_section()

        if initial_section:
            self.fields["surface"].choices = self._surface_choices_for_subsection(initial_section)
        else:
            self.fields["surface"].choices = [("", "---------")]

        if isinstance(self.instance, SurfaceDefault) and self.instance.pk and self.instance.subsection:
            self.fields["subsection"].initial = self.instance.subsection
            self.fields["surface"].initial = self.instance.surface
            self.fields["main_section"].initial = self.instance.main_section

    def clean(self):
        cleaned = super().clean()
        main_section = cleaned.get("main_section")
        subsection = cleaned.get("subsection")
        surface = cleaned.get("surface")

        if main_section and subsection:
            config = ALL_GENERIC_SECTION_CONFIGS.get(subsection)
            if config and getattr(config, "substrate_type", None):
                if str(config.substrate_type).upper() != str(main_section).upper():
                    self.add_error("subsection", "This subsection does not belong to the selected main section.")
                    self.add_error("main_section", "Choose a matching main section for this subsection.")

        if subsection and surface:
            allowed_values = {value for value, _ in self._surface_choices_for_subsection(subsection)}
            if surface not in allowed_values:
                self.add_error("surface", "Select a valid surface for the chosen subsection.")

        return cleaned


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
