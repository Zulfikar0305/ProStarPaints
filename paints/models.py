from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class Paint(models.Model):
    """
    Represents a single paint / product in the ProStar Paints catalogue.
    Prices are stored exclusive of VAT; inclusive price is stored separately
    so the quotation engine can reference either without recalculating.
    """

    class PaintType(models.TextChoices):
        WATER_BASED    = "WATER_BASED",    _("Water Based")
        SOLVENT_BASED  = "SOLVENT_BASED",  _("Solvent Based")
        ENAMEL         = "ENAMEL",         _("Enamel")
        ACRYLIC        = "ACRYLIC",        _("Acrylic")
        OIL_BASED      = "OIL_BASED",      _("Oil Based")
        EPOXY          = "EPOXY",          _("Epoxy")
        OTHER          = "OTHER",          _("Other")

    class Finish(models.TextChoices):
        SMOOTH_MATTE   = "SMOOTH_MATTE",   _("Smooth Matte")
        SMOOTH_SHEEN   = "SMOOTH_SHEEN",   _("Smooth Sheen")
        DECO_PLAST     = "DECO_PLAST",     _("Deco-plast")
        FINE_TEXTURE   = "FINE_TEXTURE",   _("Fine Texture")
        COARSE_TEXTURE = "COARSE_TEXTURE", _("Coarse Texture")
        NOT_APPLICABLE = "NOT_APPLICABLE", _("Not Applicable")

    class BaseType(models.TextChoices):
        WHITE          = "WHITE",          _("White")
        PASTEL         = "PASTEL",         _("Pastel Base")
        MEDIUM         = "MEDIUM",         _("Medium Base")
        DEEP           = "DEEP",           _("Deep Base")
        CLEAR          = "CLEAR",          _("Clear Base")
        TRANSPARENT    = "TRANSPARENT",    _("Transparent Base")
        NATURAL        = "NATURAL",        _("Natural")
        NOT_APPLICABLE = "NOT_APPLICABLE", _("Not Applicable")

    class Category(models.TextChoices):
        # existing categories preserved
        INTERIOR       = "INTERIOR",       _("Interior")
        EXTERIOR       = "EXTERIOR",       _("Exterior")
        PRIMER         = "PRIMER",         _("Primer")
        WATERPROOFING  = "WATERPROOFING",  _("Waterproofing")
        TEXTURE        = "TEXTURE",        _("Texture")
        SPECIALIST     = "SPECIALIST",     _("Specialist")
        # New catalogue categories for Product Pack 3A
        CRACKS         = "CRACKS",         _("Cracks")
        MOULD          = "MOULD",          _("Mould")
        CLEANING       = "CLEANING",       _("Cleaning")
        SANDING        = "SANDING",        _("Sanding")
        EFFLORESCENCE  = "EFFLORESCENCE",  _("Efflorescence")
        OLD_PAINT_REMOVAL = "OLD_PAINT_REMOVAL", _("Old Paint Removal")

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

    class PricingMethod(models.TextChoices):
        AREA_COATING = "AREA_COATING", _("Area-based coating")
        FIXED_PACK = "FIXED_PACK", _("Fixed package")
        PER_METRE = "PER_METRE", _("Per metre")
        NOTE_ONLY = "NOTE_ONLY", _("Note only")

    # Pricing Pack 1A additions
    finish = models.CharField(
        _("finish"),
        max_length=30,
        choices=Finish.choices,
        null=True,
        blank=True,
    )

    # Pricing product type (transitional) — defaults to area coating for existing records
    pricing_method = models.CharField(
        _("pricing method"),
        max_length=20,
        choices=PricingMethod.choices,
        default=PricingMethod.AREA_COATING,
    )

    # Coverage: square metres per litre for one coat
    spread_rate_per_litre = models.DecimalField(
        _("spread rate (m² per litre)"),
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )

    # Litres represented by the entered price (default 1 litre)
    priced_volume_litres = models.DecimalField(
        _("priced volume (litres)"),
        max_digits=7,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # Generic package information for fixed packs and similar products
    package_size = models.DecimalField(
        _("package size"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class PackageUnit(models.TextChoices):
        LITRE = "L", _("L")
        KILOGRAM = "kg", _("kg")
        METRE = "m", _("m")
        NOT_APPLICABLE = "NA", _("Not Applicable")

    package_unit = models.CharField(
        _("package unit"),
        max_length=10,
        choices=PackageUnit.choices,
        default=PackageUnit.NOT_APPLICABLE,
    )

    variant_label = models.CharField(
        _("variant label"),
        max_length=50,
        blank=True,
        default="",
    )

    predetermined_note = models.TextField(
        _("predetermined note"),
        blank=True,
        default="",
    )

    standard_coats = models.PositiveSmallIntegerField(
        _("standard coats"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )

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

