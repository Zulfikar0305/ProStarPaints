import re

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Reference generator
# ---------------------------------------------------------------------------

def _next_quotation_reference() -> str:
    """
    Return the next PSP-Q-XXXXXX reference number.

    Reads the current MAX numeric suffix from the database and increments by 1.
    Not using a DB sequence to stay portable across SQLite and PostgreSQL.
    The UNIQUE constraint on ``reference`` catches any write-time race condition.
    """
    last = (
        Quotation.objects.filter(reference__startswith="PSP-Q-")
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )
    if last:
        m = re.search(r"PSP-Q-(\d+)$", last)
        number = int(m.group(1)) + 1 if m else 1
    else:
        number = 1
    return f"PSP-Q-{number:06d}"


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------

class Quotation(models.Model):
    """
    Top-level quotation document.

    Financial fields (subtotal_excl_vat, vat_amount, total_incl_vat) are
    *derived* from line items and stored here for fast retrieval and PDF
    generation. They should be recalculated whenever line items change.
    """

    class Status(models.TextChoices):
        DRAFT     = "DRAFT",     _("Draft")
        COMPLETED = "COMPLETED", _("Completed")
        CANCELLED = "CANCELLED", _("Cancelled")

    # Identity
    reference = models.CharField(
        _("reference"),
        max_length=20,
        unique=True,
        default=_next_quotation_reference,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="quotations",
        verbose_name=_("created by"),
    )

    # Customer
    customer_name  = models.CharField(_("customer name"), max_length=200)
    customer_email = models.EmailField(_("customer email"), blank=True, default="")
    customer_phone = models.CharField(_("customer phone"), max_length=30, blank=True, default="")

    # Project
    project_name     = models.CharField(_("project name"), max_length=200, blank=True, default="")
    project_location = models.CharField(_("project location"), max_length=300, blank=True, default="")

    # Status
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    # Financials (cached totals — recalculated from line items)
    subtotal_excl_vat = models.DecimalField(
        _("subtotal (excl. VAT)"),
        max_digits=12, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    vat_amount = models.DecimalField(
        _("VAT amount"),
        max_digits=12, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    total_incl_vat = models.DecimalField(
        _("total (incl. VAT)"),
        max_digits=12, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    # Notes
    notes = models.TextField(_("notes"), blank=True, default="")

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("quotation")
        verbose_name_plural = _("quotations")

    def __str__(self) -> str:
        return f"{self.reference} — {self.customer_name}"


# ---------------------------------------------------------------------------
# QuotationSection
# ---------------------------------------------------------------------------

class QuotationSection(models.Model):
    """
    An optional grouping layer inside a quotation.

    Sections represent logical areas of work (e.g. Interior Walls, Exterior
    Fascias). Line items can belong to a section or sit directly on the
    quotation (section=None).
    """

    class SubstrateType(models.TextChoices):
        INTERIOR = "INTERIOR", _("Interior")
        EXTERIOR = "EXTERIOR", _("Exterior")

    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name=_("quotation"),
    )
    substrate_type = models.CharField(
        _("substrate type"),
        max_length=10,
        choices=SubstrateType.choices,
        default=SubstrateType.INTERIOR,
    )
    # Machine-readable key, e.g. "interior_walls", "exterior_fascias"
    subsection_key = models.CharField(_("subsection key"), max_length=80)
    display_name   = models.CharField(_("display name"), max_length=120)
    sort_order     = models.PositiveSmallIntegerField(_("sort order"), default=0)

    # When True this section is a placeholder/heading with no real line items yet
    is_placeholder = models.BooleanField(_("is placeholder"), default=False)

    class Meta:
        ordering = ["quotation", "sort_order", "display_name"]
        verbose_name = _("quotation section")
        verbose_name_plural = _("quotation sections")

    def __str__(self) -> str:
        return f"{self.quotation.reference} › {self.display_name}"


# ---------------------------------------------------------------------------
# QuotationLineItem
# ---------------------------------------------------------------------------

class QuotationLineItem(models.Model):
    """
    A single billable line on a quotation.

    Measurements
    ------------
    *area_sqm* and *quantity* are both nullable because some item types do
    not involve a measurable area (e.g. NOTE, flat-rate PREP_WORK).
    Use whichever is relevant and leave the other null.

    Pricing
    -------
    All four price/total fields are stored explicitly so the quotation PDF
    can display either VAT-inclusive or VAT-exclusive breakdowns without
    needing the VAT rate to be known at read time.
    """

    class ItemType(models.TextChoices):
        PAINT          = "PAINT",          _("Paint")
        PREP_WORK      = "PREP_WORK",      _("Prep Work")
        PRIMER         = "PRIMER",         _("Primer")
        WATERPROOFING  = "WATERPROOFING",  _("Waterproofing")
        NOTE           = "NOTE",           _("Note / Comment")

    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="line_items",
        verbose_name=_("quotation"),
    )
    section = models.ForeignKey(
        QuotationSection,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="line_items",
        verbose_name=_("section"),
    )

    item_type = models.CharField(
        _("item type"),
        max_length=20,
        choices=ItemType.choices,
        default=ItemType.PAINT,
        db_index=True,
    )
    description = models.TextField(_("description"))

    # Optional link to catalogue paint
    paint = models.ForeignKey(
        "paints.Paint",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="quotation_line_items",
        verbose_name=_("paint"),
    )

    # Application details
    coats    = models.PositiveSmallIntegerField(_("coats"), default=1)
    area_sqm = models.DecimalField(
        _("area (m²)"),
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    unit = models.CharField(_("unit"), max_length=30, blank=True, default="")

    # Per-unit pricing
    price_excl_vat = models.DecimalField(
        _("unit price (excl. VAT)"),
        max_digits=10, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    price_incl_vat = models.DecimalField(
        _("unit price (incl. VAT)"),
        max_digits=10, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    # Line totals (unit price × quantity/area)
    total_excl_vat = models.DecimalField(
        _("line total (excl. VAT)"),
        max_digits=12, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    total_incl_vat = models.DecimalField(
        _("line total (incl. VAT)"),
        max_digits=12, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    # Flexible bag for future data (coverage rate, tint code, surface condition…)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        ordering = ["quotation", "section__sort_order", "pk"]
        verbose_name = _("quotation line item")
        verbose_name_plural = _("quotation line items")

    def __str__(self) -> str:
        return f"{self.quotation.reference} — {self.get_item_type_display()}: {self.description[:60]}"

