import re

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


def _next_invoice_reference() -> str:
    """
    Return the next PSP-INV-XXXXXX reference number.
    Reads the current MAX numeric suffix and increments by 1.
    Deliberately not using a DB sequence so it stays portable (SQLite + PostgreSQL).
    The reference has a UNIQUE constraint, so any race is caught at DB level.
    """
    last = (
        Invoice.objects.filter(reference__startswith="PSP-INV-")
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )
    if last:
        m = re.search(r"PSP-INV-(\d+)$", last)
        number = int(m.group(1)) + 1 if m else 1
    else:
        number = 1
    return f"PSP-INV-{number:06d}"


class Invoice(models.Model):
    """
    Stores a completed invoice / specification sheet for a customer.
    Each record belongs to the rep who created it.
    The quotation line-items will be linked to this model in a future phase.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        COMPLETED = "COMPLETED", _("Completed")
        CANCELLED = "CANCELLED", _("Cancelled")

    # Identity
    reference = models.CharField(
        _("reference"),
        max_length=20,
        unique=True,
        default=_next_invoice_reference,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("created by"),
    )

    # Customer
    customer_name = models.CharField(_("customer name"), max_length=200)
    customer_email = models.EmailField(_("customer email"), blank=True, default="")
    customer_phone = models.CharField(_("customer phone"), max_length=30, blank=True, default="")

    # Project
    project_name = models.CharField(_("project name"), max_length=200, blank=True, default="")
    project_location = models.CharField(_("project location"), max_length=300, blank=True, default="")

    # Status
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    # Financials
    subtotal_excl_vat = models.DecimalField(
        _("subtotal (excl. VAT)"),
        max_digits=12,
        decimal_places=2,
        default="0.00",
        validators=[MinValueValidator(0)],
    )
    vat_amount = models.DecimalField(
        _("VAT amount"),
        max_digits=12,
        decimal_places=2,
        default="0.00",
        validators=[MinValueValidator(0)],
    )
    total_incl_vat = models.DecimalField(
        _("total (incl. VAT)"),
        max_digits=12,
        decimal_places=2,
        default="0.00",
        validators=[MinValueValidator(0)],
    )

    # Extra
    notes = models.TextField(_("notes"), blank=True, default="")

    # Soft-delete flag (admin sets this instead of hard-delete)
    is_removed = models.BooleanField(_("removed"), default=False, db_index=True)

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.customer_name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        for field in ("subtotal_excl_vat", "vat_amount", "total_incl_vat"):
            val = getattr(self, field)
            if val is not None and val < 0:
                errors[field] = _("This amount cannot be negative.")
        if (
            self.total_incl_vat is not None
            and self.subtotal_excl_vat is not None
            and self.total_incl_vat < self.subtotal_excl_vat
        ):
            errors["total_incl_vat"] = _("Total (incl. VAT) cannot be less than the subtotal (excl. VAT).")
        if errors:
            raise ValidationError(errors)

