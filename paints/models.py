from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Paint(models.Model):
    """
    Represents a single paint / product in the ProStar Paints catalogue.
    Prices are stored exclusive of VAT; inclusive price is stored separately
    so the quotation engine can reference either without recalculating.
    """

    class Category(models.TextChoices):
        INTERIOR       = "INTERIOR",       _("Interior")
        EXTERIOR       = "EXTERIOR",       _("Exterior")
        PRIMER         = "PRIMER",         _("Primer")
        WATERPROOFING  = "WATERPROOFING",  _("Waterproofing")
        TEXTURE        = "TEXTURE",        _("Texture")
        SPECIALIST     = "SPECIALIST",     _("Specialist")

    class PaintType(models.TextChoices):
        WATER_BASED    = "WATER_BASED",    _("Water Based")
        SOLVENT_BASED  = "SOLVENT_BASED",  _("Solvent Based")
        ENAMEL         = "ENAMEL",         _("Enamel")
        ACRYLIC        = "ACRYLIC",        _("Acrylic")
        OIL_BASED      = "OIL_BASED",      _("Oil Based")
        EPOXY          = "EPOXY",          _("Epoxy")
        OTHER          = "OTHER",          _("Other")

    class BaseType(models.TextChoices):
        WHITE          = "WHITE",          _("White")
        PASTEL         = "PASTEL",         _("Pastel Base")
        MEDIUM         = "MEDIUM",         _("Medium Base")
        DEEP           = "DEEP",           _("Deep Base")
        CLEAR          = "CLEAR",          _("Clear Base")
        TRANSPARENT    = "TRANSPARENT",    _("Transparent Base")
        NATURAL        = "NATURAL",        _("Natural")
        NOT_APPLICABLE = "NOT_APPLICABLE", _("Not Applicable")

    # Core identity
    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True, default="")
    category = models.CharField(
        _("category"), max_length=20, choices=Category.choices, default=Category.INTERIOR
    )
    paint_type = models.CharField(
        _("paint type"), max_length=20, choices=PaintType.choices, default=PaintType.WATER_BASED
    )
    base_type = models.CharField(
        _("base type"), max_length=20, choices=BaseType.choices, default=BaseType.WHITE
    )
    colour = models.CharField(_("colour"), max_length=100, blank=True, default="")

    # Pricing — stored in ZAR; two decimal places enforced at DB level
    price_excl_vat = models.DecimalField(
        _("price (excl. VAT)"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    price_incl_vat = models.DecimalField(
        _("price (incl. VAT)"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    # Optional product image
    image = models.ImageField(
        _("product image"),
        upload_to="paints/images/",
        blank=True,
        null=True,
    )

    # Status & timestamps
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("paint")
        verbose_name_plural = _("paints")
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_category_display()})"

    # --- Model-level validation ---

    def clean(self) -> None:
        errors = {}

        if self.price_excl_vat is not None and self.price_excl_vat < 0:
            errors["price_excl_vat"] = _("Price (excl. VAT) cannot be negative.")

        if self.price_incl_vat is not None and self.price_incl_vat < 0:
            errors["price_incl_vat"] = _("Price (incl. VAT) cannot be negative.")

        if (
            self.price_excl_vat is not None
            and self.price_incl_vat is not None
            and self.price_incl_vat < self.price_excl_vat
        ):
            errors["price_incl_vat"] = _(
                "Price (incl. VAT) must be greater than or equal to price (excl. VAT)."
            )

        if errors:
            raise ValidationError(errors)

