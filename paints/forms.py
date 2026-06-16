from decimal import ROUND_HALF_UP, Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Paint


def _get_vat_rate() -> Decimal:
    """Return the current VAT rate. Import deferred to avoid circular imports."""
    from system_tools.models import AppSetting
    return AppSetting.get_vat_rate()


class PaintForm(forms.ModelForm):
    """
    Shared form for creating and updating Paint records.
    Server-side VAT auto-calculation:
    - If only price_excl_vat provided → calculate price_incl_vat
    - If only price_incl_vat provided → calculate price_excl_vat (back-calculate)
    - If both provided → validate they are consistent (within ±R0.02 rounding)
    """

    class Meta:
        model = Paint
        fields = (
            "name",
            "description",
            "category",
            "base_type",
            "colour",
            "finish",
            "pricing_method",
            "package_size",
            "package_unit",
            "variant_label",
            "predetermined_note",
            "standard_coats",
            "spread_rate_per_litre",
            "priced_volume_litres",
            "price_excl_vat",
            "price_incl_vat",
            "image",
            "is_active",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Plascon Double Velvet"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional product description"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "base_type": forms.Select(attrs={"class": "form-select"}),
            "finish": forms.Select(attrs={"class": "form-select"}),
            "colour": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Bright White, Tinted"}),
            "spread_rate_per_litre": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01", "placeholder": "e.g. 10.00"}),
            "priced_volume_litres": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01", "placeholder": "1.00"}),
            "pricing_method": forms.Select(attrs={"class": "form-select"}),
            "package_size": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01", "placeholder": "e.g. 2.00"}),
            "package_unit": forms.Select(attrs={"class": "form-select"}),
            "variant_label": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 80 grit"}),
            "predetermined_note": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional predetermined client note"}),
            "standard_coats": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "1", "placeholder": "e.g. 1"}),
            "price_excl_vat": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "0.00", "id": "id_price_excl_vat"}),
            "price_incl_vat": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "0.00", "id": "id_price_incl_vat"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

        help_texts = {
            "spread_rate_per_litre": _(
                "Coverage in square metres per litre for one coat."
            ),
            "priced_volume_litres": _(
                "Litres represented by the entered price. Use 1 for a per-litre price."
            ),
            "pricing_method": _(
                "How this product is calculated when used in a quotation."
            ),
            "package_size": _(
                "Size of one package, such as 2 kg or 5 L."
            ),
            "variant_label": _(
                "Optional product variant, such as 80 grit."
            ),
            "predetermined_note": _(
                "Client-facing note used for note-only quotation items."
            ),
            "standard_coats": _(
                "Fixed coat count for products such as primer or waterproofing."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow server-side VAT auto-calculation by letting the inclusive price be optional
        # at the form level. The model field remains required (DB-level) so cleaned_data
        # must contain a computed value prior to saving.
        if "price_incl_vat" in self.fields:
            self.fields["price_incl_vat"].required = False
        # Note: `pricing_method` and `package_unit` are intentionally kept as
        # required form fields to enforce catalogue classification at the UI level.

        # If the submitted category is a note-only category, some fields that
        # would normally be required are not relevant. Relax their `required`
        # flags so the form can validate and then normalize values server-side
        # in `clean()` (this mirrors what the UI would submit when JS runs).
        try:
            submitted_cat = None
            # `self.data` is a QueryDict when the form is bound with POST data
            if getattr(self, "data", None):
                submitted_cat = self.data.get("category")
            # Fallback to initial or instance when available
            if not submitted_cat and kwargs.get("initial"):
                submitted_cat = kwargs.get("initial").get("category")
            if not submitted_cat and hasattr(self, "instance") and getattr(self.instance, "pk", None):
                submitted_cat = getattr(self.instance, "category", None)

            if submitted_cat in (Paint.Category.EFFLORESCENCE, Paint.Category.OLD_PAINT_REMOVAL):
                for f in ("priced_volume_litres", "spread_rate_per_litre", "package_size", "standard_coats", "variant_label"):
                    if f in self.fields:
                        self.fields[f].required = False
        except Exception:
            # Defensive: if anything goes wrong here, don't prevent form usage.
            pass

    def clean_price_excl_vat(self):
        value = self.cleaned_data.get("price_excl_vat")
        if value is not None and value < 0:
            raise ValidationError(_("Price (excl. VAT) cannot be negative."))
        return value

    def clean_price_incl_vat(self):
        value = self.cleaned_data.get("price_incl_vat")
        if value is not None and value < 0:
            raise ValidationError(_("Price (incl. VAT) cannot be negative."))
        return value

    def clean(self):
        cleaned_data = super().clean()
        excl = cleaned_data.get("price_excl_vat")
        incl = cleaned_data.get("price_incl_vat")

        # If neither field has an individual validation error, apply VAT logic
        if "price_excl_vat" not in self.errors and "price_incl_vat" not in self.errors:
            vat_rate = _get_vat_rate()
            multiplier = (Decimal("1") + vat_rate / Decimal("100"))

            if excl is not None and (incl is None or incl == Decimal("0")):
                # Auto-calculate incl from excl
                cleaned_data["price_incl_vat"] = (excl * multiplier).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            elif incl is not None and (excl is None or excl == Decimal("0")):
                # Back-calculate excl from incl
                cleaned_data["price_excl_vat"] = (incl / multiplier).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            elif excl is not None and incl is not None:
                # Both provided: validate consistency within ±R0.02 rounding tolerance
                expected_incl = (excl * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if abs(incl - expected_incl) > Decimal("0.02"):
                    self.add_error(
                        "price_incl_vat",
                        _("Price (incl. VAT) does not match the expected VAT calculation "
                          "(%(expected)s at %(rate)s%% VAT). Adjust one field or leave the "
                          "other blank to auto-calculate.")
                        % {"expected": expected_incl, "rate": vat_rate},
                    )

        # Continue to category-specific form-level validation and safe normalization
        cat = cleaned_data.get("category")
        pm = cleaned_data.get("pricing_method")
        pu = cleaned_data.get("package_unit")
        finish = cleaned_data.get("finish")
        base_type = cleaned_data.get("base_type")
        spread = cleaned_data.get("spread_rate_per_litre")
        priced_volume = cleaned_data.get("priced_volume_litres")
        pkg_size = cleaned_data.get("package_size")
        std_coats = cleaned_data.get("standard_coats")
        variant = cleaned_data.get("variant_label")
        note = cleaned_data.get("predetermined_note")

        # Helper to add field-specific errors
        def ferror(field, msg):
            self.add_error(field, msg)

        if cat in (Paint.Category.INTERIOR, Paint.Category.EXTERIOR):
            if pm != Paint.PricingMethod.AREA_COATING:
                ferror("pricing_method", _("Interior/Exterior products must use area-based pricing."))
            if not finish or finish == Paint.Finish.NOT_APPLICABLE:
                ferror("finish", _("Finish is required for Interior/Exterior products."))
            if spread is None or spread <= Decimal("0"):
                ferror("spread_rate_per_litre", _("Spread rate must be positive for Interior/Exterior products."))
            if priced_volume is None or priced_volume <= Decimal("0"):
                ferror("priced_volume_litres", _("Priced volume must be positive for Interior/Exterior products."))
            if pu != Paint.PackageUnit.NOT_APPLICABLE:
                ferror("package_unit", _("Package unit must be Not Applicable for Interior/Exterior products."))
            if pkg_size is not None:
                ferror("package_size", _("Package size must be blank for Interior/Exterior products."))
            if std_coats is not None:
                ferror("standard_coats", _("Standard coats must be blank for Interior/Exterior products."))
            if note:
                ferror("predetermined_note", _("Predetermined note must be blank for Interior/Exterior products."))

        elif cat in (Paint.Category.PRIMER, Paint.Category.WATERPROOFING):
            if pm != Paint.PricingMethod.AREA_COATING:
                ferror("pricing_method", _("Primer/Waterproofing must use area-based pricing."))
            if finish != Paint.Finish.NOT_APPLICABLE:
                ferror("finish", _("Finish must be Not Applicable for Primer/Waterproofing."))
            if base_type != Paint.BaseType.NOT_APPLICABLE:
                ferror("base_type", _("Base type must be Not Applicable for Primer/Waterproofing."))
            if spread is None or spread <= Decimal("0"):
                ferror("spread_rate_per_litre", _("Spread rate must be positive for Primer/Waterproofing."))
            if priced_volume is None or priced_volume <= Decimal("0"):
                ferror("priced_volume_litres", _("Priced volume must be positive for Primer/Waterproofing."))
            # Normalize standard_coats to 1 if empty
            if std_coats in (None, ""):
                cleaned_data["standard_coats"] = 1
            elif std_coats != 1:
                ferror("standard_coats", _("Primer/Waterproofing must have exactly 1 standard coat."))
            if pu != Paint.PackageUnit.NOT_APPLICABLE:
                ferror("package_unit", _("Package unit must be Not Applicable for Primer/Waterproofing."))
            if pkg_size is not None:
                ferror("package_size", _("Package size must be blank for Primer/Waterproofing."))

        elif cat == Paint.Category.CRACKS:
            allowed = {Decimal("2.00"), Decimal("5.00"), Decimal("10.00")}
            if pm != Paint.PricingMethod.FIXED_PACK:
                ferror("pricing_method", _("Cracks products must use fixed package pricing."))
            if pu != Paint.PackageUnit.KILOGRAM:
                ferror("package_unit", _("Cracks products must use kilogram package unit."))
            if pkg_size not in allowed:
                ferror("package_size", _("Cracks package size must be one of 2.00, 5.00, 10.00."))
            if finish != Paint.Finish.NOT_APPLICABLE:
                ferror("finish", _("Finish must be Not Applicable for Cracks products."))
            if base_type != Paint.BaseType.NOT_APPLICABLE:
                ferror("base_type", _("Base type must be Not Applicable for Cracks products."))
            if spread is not None:
                ferror("spread_rate_per_litre", _("Spread rate must be blank for Cracks products."))
            if std_coats is not None:
                ferror("standard_coats", _("Standard coats must be blank for Cracks products."))
            if note:
                ferror("predetermined_note", _("Predetermined note must be blank for Cracks products."))

        elif cat in (Paint.Category.MOULD, Paint.Category.CLEANING):
            allowed = {Decimal("1.00"), Decimal("5.00")}
            if pm != Paint.PricingMethod.FIXED_PACK:
                ferror("pricing_method", _("Mould/Cleaning products must use fixed package pricing."))
            if pu != Paint.PackageUnit.LITRE:
                ferror("package_unit", _("Mould/Cleaning products must use litre package unit."))
            if pkg_size not in allowed:
                ferror("package_size", _("Mould/Cleaning package size must be 1.00 or 5.00 (L)."))
            if finish != Paint.Finish.NOT_APPLICABLE:
                ferror("finish", _("Finish must be Not Applicable for Mould/Cleaning products."))
            if base_type != Paint.BaseType.NOT_APPLICABLE:
                ferror("base_type", _("Base type must be Not Applicable for Mould/Cleaning products."))
            if spread is not None:
                ferror("spread_rate_per_litre", _("Spread rate must be blank for Mould/Cleaning products."))
            if std_coats is not None:
                ferror("standard_coats", _("Standard coats must be blank for Mould/Cleaning products."))
            if note:
                ferror("predetermined_note", _("Predetermined note must be blank for Mould/Cleaning products."))

        elif cat == Paint.Category.SANDING:
            allowed_variants = {"40 grit", "60 grit", "80 grit", "100 grit"}
            if pm != Paint.PricingMethod.PER_METRE:
                ferror("pricing_method", _("Sanding products must use per-metre pricing."))
            if pu != Paint.PackageUnit.METRE:
                ferror("package_unit", _("Sanding products must use metre package unit."))
            if (not variant) or (variant not in allowed_variants):
                ferror("variant_label", _("Sanding variant must be one of 40/60/80/100 grit."))
            if finish != Paint.Finish.NOT_APPLICABLE:
                ferror("finish", _("Finish must be Not Applicable for Sanding products."))
            if base_type != Paint.BaseType.NOT_APPLICABLE:
                ferror("base_type", _("Base type must be Not Applicable for Sanding products."))
            if spread is not None:
                ferror("spread_rate_per_litre", _("Spread rate must be blank for Sanding products."))
            if pkg_size is not None:
                ferror("package_size", _("Package size must be blank for Sanding products."))
            if std_coats is not None:
                ferror("standard_coats", _("Standard coats must be blank for Sanding products."))
            if note:
                ferror("predetermined_note", _("Predetermined note must be blank for Sanding products."))

        elif cat in (Paint.Category.EFFLORESCENCE, Paint.Category.OLD_PAINT_REMOVAL):
            if pm != Paint.PricingMethod.NOTE_ONLY:
                ferror("pricing_method", _("This category must be note-only pricing."))
            if not (note and note.strip()):
                ferror("predetermined_note", _("Predetermined note is required for note-only products."))
            if finish != Paint.Finish.NOT_APPLICABLE:
                ferror("finish", _("Finish must be Not Applicable for this category."))
            if base_type != Paint.BaseType.NOT_APPLICABLE:
                ferror("base_type", _("Base type must be Not Applicable for this category."))
            if pu != Paint.PackageUnit.NOT_APPLICABLE:
                ferror("package_unit", _("Package unit must be Not Applicable for this category."))
            if pkg_size is not None:
                ferror("package_size", _("Package size must be blank for this category."))
            if spread is not None:
                ferror("spread_rate_per_litre", _("Spread rate must be blank for this category."))
            if std_coats is not None:
                ferror("standard_coats", _("Standard coats must be blank for this category."))
            if variant:
                ferror("variant_label", _("Variant label must be blank for this category."))
            # Normalize and enforce note-only canonical values so the model
            # receives authoritative values regardless of what the UI sent.
            cleaned_data["pricing_method"] = Paint.PricingMethod.NOTE_ONLY
            cleaned_data["finish"] = Paint.Finish.NOT_APPLICABLE
            cleaned_data["base_type"] = Paint.BaseType.NOT_APPLICABLE
            cleaned_data["package_unit"] = Paint.PackageUnit.NOT_APPLICABLE
            cleaned_data["package_size"] = None
            cleaned_data["spread_rate_per_litre"] = None
            cleaned_data["standard_coats"] = None
            cleaned_data["variant_label"] = ""

            # Ensure prices are explicit zeros (Decimal) to satisfy model validation
            cleaned_data["price_excl_vat"] = Decimal("0.00")
            cleaned_data["price_incl_vat"] = Decimal("0.00")

        return cleaned_data
