from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class SpecificationTemplate(TimeStampedModel):
    name = models.CharField(max_length=200)
    key = models.SlugField(max_length=200, unique=True)
    content = models.TextField(blank=True)
    # Flexible configuration storage for document template sections
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        Persist the template and ensure there is at most one active template
        for a given `key`. After saving this instance, any other templates
        with the same key will be marked inactive when this instance is
        active. This keeps the "one active per key" invariant simple and
        database-driven without adding schema fields.
        """
        super().save(*args, **kwargs)
        try:
            if self.is_active:
                SpecificationTemplate.objects.filter(key=self.key).exclude(pk=self.pk).update(is_active=False)
        except Exception:
            # Do not raise from save() to avoid breaking admin/save flows
            pass


class KnowledgeCategory(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# Canonical knowledge categories used by the specification engine.
# These are created on-demand by admin views to simplify initial setup.
KNOWLEDGE_CATEGORIES = [
    ("surface_preparation", "Surface Preparation"),
    ("general_notes", "General Notes"),
    ("safety", "Safety"),
    ("application", "Application"),
    ("drying", "Drying"),
    ("cleaning", "Cleaning"),
    ("environmental", "Environmental"),
    ("recommendations", "Recommendations"),
    ("warranty", "Warranty"),
    ("custom", "Custom"),
]


class KnowledgeEntry(TimeStampedModel):
    title = models.CharField(max_length=200)
    category = models.ForeignKey(
        KnowledgeCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entries",
    )
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    # Entry kind: note (existing) or clause (specification clause)
    KIND_NOTE = "note"
    KIND_CLAUSE = "clause"
    KIND_CHOICES = [
        (KIND_NOTE, "Note"),
        (KIND_CLAUSE, "Clause"),
    ]
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_NOTE)

    # Clause-related fields (used when kind == 'clause')
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Administrator-visible priority used when composing lists of knowledge
    # (higher priority items may be applied before lower priority ones).
    priority = models.IntegerField(default=0)
    # Lightweight tags for filtering/searching; stored as a JSON array of strings.
    tags = models.JSONField(default=list, blank=True)
    # Optional arbitrary metadata stored as JSON. Consumers may use this
    # for resolver hints in future packs.
    metadata = models.JSONField(default=dict, blank=True)

    @staticmethod
    def _format_selection_value(value):
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return ", ".join(
                KnowledgeEntry._format_selection_value(v)
                for v in value
                if KnowledgeEntry._format_selection_value(v)
            )
        text = str(value).replace("_", " ").replace("-", " ")
        return text.title()

    @property
    def selection_summary(self):
        meta = self.metadata or {}
        if not meta:
            return ""

        parts = []
        section_key = meta.get("section_key")
        if section_key:
            parts.append(self._format_selection_value(section_key).replace("Walls", "Walls"))

        substrate = meta.get("substrate_type")
        if substrate:
            parts.append(self._format_selection_value(substrate))

        for key in ("types", "type"):
            values = meta.get(key)
            if values:
                parts.append(self._format_selection_value(values))
                break

        for key in ("surface_conditions", "surface_condition"):
            values = meta.get(key)
            if values:
                parts.append(f"Conditions: {self._format_selection_value(values)}")
                break

        for key in ("finishes", "finish"):
            values = meta.get(key)
            if values:
                parts.append(f"Finish: {self._format_selection_value(values)}")
                break

        return " → ".join(part for part in parts if part)

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            result = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, (list, tuple, set)):
                    result.extend(KnowledgeEntry._as_list(item))
                else:
                    text = str(item).strip()
                    if text:
                        result.append(text)
            return result
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _humanise_phrase(value):
        text = str(value).strip()
        if not text:
            return ""
        text = text.replace("_", " ").replace("-", " ")
        text = " ".join(part for part in text.split() if part)
        return text.title()

    def automatic_spec_content(self):
        meta = self.metadata or {}
        sections = []

        if self.body and str(self.body).strip():
            sections.append(str(self.body).strip())

        prep_values = self._as_list(meta.get("preparation_requirements") or meta.get("preparations"))
        if prep_values:
            sections.append("Preparation\n" + "; ".join(self._humanise_phrase(v) for v in prep_values))

        extra_prep = (meta.get("additional_preparation_notes") or "").strip()
        if extra_prep:
            sections.append("Additional Preparation\n" + extra_prep)

        application_method = (meta.get("application_method") or "").strip()
        if application_method:
            sections.append("Application\n" + application_method)
        elif meta.get("application"):
            sections.append("Application\n" + str(meta.get("application")).strip())

        coating_system_notes = (meta.get("coating_system_notes") or "").strip()
        if coating_system_notes:
            sections.append("Coating System\n" + coating_system_notes)

        technical_notes = (meta.get("technical_notes") or "").strip()
        if technical_notes:
            sections.append("Technical Information\n" + technical_notes)

        drying_recoat = (meta.get("drying_recoat_guidance") or "").strip()
        if drying_recoat:
            sections.append("Drying / Recoat\n" + drying_recoat)

        primer_values = self._as_list(meta.get("primers") or meta.get("primer"))
        if primer_values:
            sections.append("Primer\n" + "; ".join(self._humanise_phrase(v) for v in primer_values))

        waterproof_values = self._as_list(meta.get("waterproofing") or meta.get("waterproofing_options"))
        if waterproof_values:
            sections.append("Waterproofing\n" + "; ".join(self._humanise_phrase(v) for v in waterproof_values))

        moisture_min = meta.get("moisture_min")
        moisture_max = meta.get("moisture_max")
        if moisture_min is not None or moisture_max is not None:
            moisture_values = []
            if moisture_min is not None:
                moisture_values.append(f"Min {moisture_min}%")
            if moisture_max is not None:
                moisture_values.append(f"Max {moisture_max}%")
            if moisture_values:
                sections.append("Moisture\n" + "; ".join(moisture_values))

        rendered = "\n\n".join(sections)
        return rendered.strip() or (self.body or "")

    def __str__(self):
        return self.title


class SurfaceDefault(TimeStampedModel):
    """Simple, exact surface target for reusable specification defaults.

    One record represents exactly one ProStar leaf surface target:
    Main Section → Subsection → Surface.
    The content is intentionally minimal and business-focused.
    """

    MAIN_SECTION_CHOICES = [
        ("INTERIOR", "Interior"),
        ("EXTERIOR", "Exterior"),
    ]

    main_section = models.CharField(max_length=20, choices=MAIN_SECTION_CHOICES, db_index=True)
    subsection = models.CharField(max_length=120, db_index=True)
    surface = models.CharField(max_length=120, db_index=True)
    preparation_requirements = models.TextField(blank=True)
    surface_rules = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["main_section", "subsection", "surface"]
        unique_together = [("main_section", "subsection", "surface")]
        verbose_name = "Surface Default"
        verbose_name_plural = "Surface Defaults"

    @property
    def selection_summary(self):
        from quotation.config import ALL_GENERIC_SECTION_CONFIGS
        from quotation.services import ALL_SUBSECTIONS

        main_label = dict(self.MAIN_SECTION_CHOICES).get(self.main_section, self.main_section)
        subsection_cfg = ALL_SUBSECTIONS.get(self.subsection)
        subsection_label = subsection_cfg.display_name if subsection_cfg else self.subsection.replace("_", " ").title()

        surface_label = self.surface.replace("_", " ").title() if self.surface else ""
        config = ALL_GENERIC_SECTION_CONFIGS.get(self.subsection)
        if config:
            for value, label in getattr(config, "types", []) or []:
                if value == self.surface:
                    surface_label = label
                    break

        return f"{main_label} → {subsection_label} → {surface_label}"

    def __str__(self):
        return self.selection_summary


class KnowledgeRule(TimeStampedModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    rule_type = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class MoistureRule(TimeStampedModel):
    name = models.CharField(max_length=200)
    min_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ClauseTrigger(models.Model):
    """Domain-specific trigger mapping linking a simple trigger key/type
    to a `KnowledgeEntry` (clause).

    Examples for `trigger_type` include: 'wall_type', 'paint', 'finish'.
    `trigger_key` can be a stable string identifying the selection (e.g. 'previously_painted').
    This keeps the model simple and understandable while still being flexible
    for future wiring in Pack 2.
    """
    trigger_type = models.CharField(max_length=100)
    trigger_key = models.CharField(max_length=200, blank=True)
    clause = models.ForeignKey(KnowledgeEntry, on_delete=models.CASCADE, related_name="triggers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Clause Trigger"
        verbose_name_plural = "Clause Triggers"
        unique_together = (("trigger_type", "trigger_key", "clause"),)

    def __str__(self):
        return f"Trigger {self.trigger_type}:{self.trigger_key} -> {self.clause}"


class SpecificationRule(TimeStampedModel):
    """Generic specification rule that maps a numeric range to one or more clauses.

    Designed to be extensible for different rule types (moisture, coverage, area, etc.).
    """
    RULE_MOISTURE = "MOISTURE"
    RULE_COVERAGE = "COVERAGE"
    RULE_AREA = "AREA"
    RULE_SPREAD_RATE = "SPREAD_RATE"
    RULE_COATS = "COATS"
    RULE_PRODUCT_WARNING = "PRODUCT_WARNING"
    RULE_TEMPERATURE = "TEMPERATURE"
    RULE_CUSTOM = "CUSTOM"

    RULE_TYPE_CHOICES = [
        (RULE_MOISTURE, "Moisture"),
        (RULE_COVERAGE, "Coverage"),
        (RULE_AREA, "Area"),
        (RULE_SPREAD_RATE, "Spread Rate"),
        (RULE_COATS, "Number of Coats"),
        (RULE_PRODUCT_WARNING, "Product Warning"),
        (RULE_TEMPERATURE, "Temperature"),
        (RULE_CUSTOM, "Custom"),
    ]

    name = models.CharField(max_length=200)
    rule_type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES)
    # Generic numeric range values. Interpretation (percent/meters/etc.) handled by consumers.
    min_value = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Lower values evaluate first")

    # Link to clauses (KnowledgeEntry) that should be applied when this rule matches
    clauses = models.ManyToManyField("KnowledgeEntry", blank=True, related_name="spec_rules")

    class Meta:
        ordering = ["priority", "pk"]
        verbose_name = "Specification Rule"
        verbose_name_plural = "Specification Rules"

    def __str__(self):
        if self.min_value is None and self.max_value is None:
            rng = "Any"
        elif self.min_value is None:
            rng = f"≤ {self.max_value}{self.unit or ''}"
        elif self.max_value is None:
            rng = f"≥ {self.min_value}{self.unit or ''}"
        else:
            rng = f"{self.min_value}{self.unit or ''}–{self.max_value}{self.unit or ''}"
        return f"{self.name} ({self.get_rule_type_display()}) — {rng}"


class ManualSpecificationDraft(TimeStampedModel):
    """User-editable draft of a resolved specification.

    Drafts are standalone JSON blobs derived from the
    `SpecificationResolver.resolve()` output and belong to a single
    `Quotation`. They do not modify the original quotation and are safe
    to create and delete without affecting pricing or quotation data.
    """

    STATUS_DRAFT = "DRAFT"
    STATUS_PUBLISHED = "PUBLISHED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
    ]

    quotation = models.ForeignKey(
        "quotation.Quotation",
        on_delete=models.CASCADE,
        related_name="spec_drafts",
    )
    title = models.CharField(max_length=200, blank=True)
    data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        qref = getattr(self.quotation, "reference", "?")
        return f"Draft {self.pk} for {qref}"
