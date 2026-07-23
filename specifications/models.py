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


class KnowledgeCategory(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


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

    def __str__(self):
        return self.title


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
