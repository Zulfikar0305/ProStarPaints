from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _


class VATSettingsForm(forms.Form):
    """Form for updating the application VAT rate."""

    vat_rate = forms.DecimalField(
        label=_("VAT Rate (%)"),
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "max": "100",
            "placeholder": "15.00",
        }),
        help_text=_("Enter the VAT rate as a percentage, e.g. 15 for 15%."),
    )

    def clean_vat_rate(self):
        rate = self.cleaned_data.get("vat_rate")
        if rate is None:
            raise forms.ValidationError(_("VAT rate is required."))
        if rate < Decimal("0"):
            raise forms.ValidationError(_("VAT rate cannot be negative."))
        if rate > Decimal("100"):
            raise forms.ValidationError(_("VAT rate cannot exceed 100%."))
        return rate
