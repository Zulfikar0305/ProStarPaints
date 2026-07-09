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
        DEEP           = "DEEP",           _("Deep Base")
        CLEAR          = "CLEAR",          _("Clear Base")
        TRANSPARENT    = "TRANSPARENT",    _("Transparent Base")
        NOT_APPLICABLE = "NOT_APPLICABLE", _("Not Applicable")

    class Category(models.TextChoices):
        INTERIOR       = "INTERIOR",       _("Interior")
        EXTERIOR       = "EXTERIOR",       _("Exterior")
        PRIMER         = "PRIMER",         _("Primer")
        WATERPROOFING  = "WATERPROOFING",  _("Waterproofing")
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

    group_key = models.CharField(
        _("group key"),
        max_length=50,
        blank=True,
        null=True,
        help_text="Machine key linking this product to a PAINT_GROUPS entry for UI grouping",
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

        # Category-specific authoritative rules
        cat = self.category
        # Helper shortcuts
        pm = self.pricing_method
        pu = self.package_unit
        st = self.standard_coats
        ps = self.package_size

        # INTERIOR / EXTERIOR
        if cat in (self.Category.INTERIOR, self.Category.EXTERIOR):
            if pm != self.PricingMethod.AREA_COATING:
                errors["pricing_method"] = _("Interior/Exterior products must use area-based pricing.")
            if not self.finish or self.finish == self.Finish.NOT_APPLICABLE:
                errors["finish"] = _("Finish is required for Interior/Exterior products.")
            if self.spread_rate_per_litre is None or self.spread_rate_per_litre <= Decimal("0"):
                errors["spread_rate_per_litre"] = _(
                    "Spread rate must be a positive number for Interior/Exterior products."
                )
            if self.priced_volume_litres is None or self.priced_volume_litres <= Decimal("0"):
                errors["priced_volume_litres"] = _(
                    "Priced volume must be a positive number for Interior/Exterior products."
                )
            if pu != self.PackageUnit.NOT_APPLICABLE:
                errors["package_unit"] = _(
                    "Package unit must be Not Applicable for Interior/Exterior products."
                )
            if ps is not None:
                errors["package_size"] = _("Package size must be blank for Interior/Exterior products.")
            if st is not None:
                errors["standard_coats"] = _("Standard coats must be blank for Interior/Exterior products.")
            if self.predetermined_note:
                errors["predetermined_note"] = _("Predetermined note must be blank for Interior/Exterior products.")

        # PRIMER / WATERPROOFING
        elif cat in (self.Category.PRIMER, self.Category.WATERPROOFING):
            if pm != self.PricingMethod.AREA_COATING:
                errors["pricing_method"] = _("Primer/Waterproofing must use area-based pricing.")
            if self.finish != self.Finish.NOT_APPLICABLE:
                errors["finish"] = _("Finish must be Not Applicable for Primer/Waterproofing.")
            if self.base_type != self.BaseType.NOT_APPLICABLE:
                errors["base_type"] = _("Base type must be Not Applicable for Primer/Waterproofing.")
            if self.spread_rate_per_litre is None or self.spread_rate_per_litre <= Decimal("0"):
                errors["spread_rate_per_litre"] = _(
                    "Spread rate must be a positive number for Primer/Waterproofing."
                )
            if self.priced_volume_litres is None or self.priced_volume_litres <= Decimal("0"):
                errors["priced_volume_litres"] = _(
                    "Priced volume must be a positive number for Primer/Waterproofing."
                )
            if st != 1:
                errors["standard_coats"] = _("Primer/Waterproofing must have exactly 1 standard coat.")
            if pu != self.PackageUnit.NOT_APPLICABLE:
                errors["package_unit"] = _("Package unit must be Not Applicable for Primer/Waterproofing.")
            if ps is not None:
                errors["package_size"] = _("Package size must be blank for Primer/Waterproofing.")

        # CRACKS
        elif cat == self.Category.CRACKS:
            allowed = {Decimal("2.00"), Decimal("5.00"), Decimal("10.00")}
            if pm != self.PricingMethod.FIXED_PACK:
                errors["pricing_method"] = _("Cracks products must use fixed package pricing.")
            if pu != self.PackageUnit.KILOGRAM:
                errors["package_unit"] = _("Cracks products must use kilogram package unit.")
            if ps not in allowed:
                errors["package_size"] = _(
                    "Cracks package size must be one of: 2.00, 5.00, 10.00 (kg)."
                )
            if self.finish != self.Finish.NOT_APPLICABLE:
                errors["finish"] = _("Finish must be Not Applicable for Cracks products.")
            if self.base_type != self.BaseType.NOT_APPLICABLE:
                errors["base_type"] = _("Base type must be Not Applicable for Cracks products.")
            if self.spread_rate_per_litre is not None:
                errors["spread_rate_per_litre"] = _("Spread rate must be blank for Cracks products.")
            if st is not None:
                errors["standard_coats"] = _("Standard coats must be blank for Cracks products.")
            if self.predetermined_note:
                errors["predetermined_note"] = _("Predetermined note must be blank for Cracks products.")

        # MOULD / CLEANING
        elif cat in (self.Category.MOULD, self.Category.CLEANING):
            allowed = {Decimal("1.00"), Decimal("5.00")}
            if pm != self.PricingMethod.FIXED_PACK:
                errors["pricing_method"] = _("Mould/Cleaning products must use fixed package pricing.")
            if pu != self.PackageUnit.LITRE:
                errors["package_unit"] = _("Mould/Cleaning products must use litre package unit.")
            if ps not in allowed:
                errors["package_size"] = _("Mould/Cleaning package size must be 1.00 or 5.00 (L).")
            if self.finish != self.Finish.NOT_APPLICABLE:
                errors["finish"] = _("Finish must be Not Applicable for Mould/Cleaning products.")
            if self.base_type != self.BaseType.NOT_APPLICABLE:
                errors["base_type"] = _("Base type must be Not Applicable for Mould/Cleaning products.")
            if self.spread_rate_per_litre is not None:
                errors["spread_rate_per_litre"] = _("Spread rate must be blank for Mould/Cleaning products.")
            if st is not None:
                errors["standard_coats"] = _("Standard coats must be blank for Mould/Cleaning products.")
            if self.predetermined_note:
                errors["predetermined_note"] = _("Predetermined note must be blank for Mould/Cleaning products.")

        # SANDING
        elif cat == self.Category.SANDING:
            allowed_variants = {"40 grit", "60 grit", "80 grit", "100 grit"}
            if pm != self.PricingMethod.PER_METRE:
                errors["pricing_method"] = _("Sanding products must use per-metre pricing.")
            if pu != self.PackageUnit.METRE:
                errors["package_unit"] = _("Sanding products must use metre package unit.")
            if (not self.variant_label) or (self.variant_label not in allowed_variants):
                errors["variant_label"] = _(
                    "Sanding variant must be one of: 40 grit, 60 grit, 80 grit, 100 grit."
                )
            if self.finish != self.Finish.NOT_APPLICABLE:
                errors["finish"] = _("Finish must be Not Applicable for Sanding products.")
            if self.base_type != self.BaseType.NOT_APPLICABLE:
                errors["base_type"] = _("Base type must be Not Applicable for Sanding products.")
            if self.spread_rate_per_litre is not None:
                errors["spread_rate_per_litre"] = _("Spread rate must be blank for Sanding products.")
            if ps is not None:
                errors["package_size"] = _("Package size must be blank for Sanding products.")
            if st is not None:
                errors["standard_coats"] = _("Standard coats must be blank for Sanding products.")
            if self.predetermined_note:
                errors["predetermined_note"] = _("Predetermined note must be blank for Sanding products.")

        # EFFLORESCENCE / OLD PAINT REMOVAL
        elif cat in (self.Category.EFFLORESCENCE, self.Category.OLD_PAINT_REMOVAL):
            if pm != self.PricingMethod.NOTE_ONLY:
                errors["pricing_method"] = _("This category must be note-only pricing.")
            if not (self.predetermined_note and self.predetermined_note.strip()):
                errors["predetermined_note"] = _("Predetermined note is required for note-only products.")
            if self.finish != self.Finish.NOT_APPLICABLE:
                errors["finish"] = _("Finish must be Not Applicable for this category.")
            if self.base_type != self.BaseType.NOT_APPLICABLE:
                errors["base_type"] = _("Base type must be Not Applicable for this category.")
            if pu != self.PackageUnit.NOT_APPLICABLE:
                errors["package_unit"] = _("Package unit must be Not Applicable for this category.")
            if ps is not None:
                errors["package_size"] = _("Package size must be blank for this category.")
            if self.spread_rate_per_litre is not None:
                errors["spread_rate_per_litre"] = _("Spread rate must be blank for this category.")
            if st is not None:
                errors["standard_coats"] = _("Standard coats must be blank for this category.")
            if self.variant_label:
                errors["variant_label"] = _("Variant label must be blank for this category.")
            if (self.price_excl_vat != Decimal("0.00")) or (self.price_incl_vat != Decimal("0.00")):
                errors["price_excl_vat"] = _("Note-only products must have zero prices.")

        if errors:
            raise ValidationError(errors)

