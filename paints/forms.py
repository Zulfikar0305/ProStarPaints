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
            "paint_type",
            "base_type",
            "colour",
            "price_excl_vat",
            "price_incl_vat",
            "image",
            "is_active",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Plascon Double Velvet"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional product description"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "paint_type": forms.Select(attrs={"class": "form-select"}),
            "base_type": forms.Select(attrs={"class": "form-select"}),
            "colour": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Bright White, Tinted"}),
            "price_excl_vat": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "0.00", "id": "id_price_excl_vat"}),
            "price_incl_vat": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "0.00", "id": "id_price_incl_vat"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

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

        return cleaned_data
