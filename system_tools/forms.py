import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import BrandingSetting

HEX_COLOUR_RE = re.compile(r"^#(?:[0-9A-Fa-f]{6})$")
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


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


# ---------------------------------------------------------------------------
# Branding settings form (admin-only)
# ---------------------------------------------------------------------------

class BrandingSettingForm(forms.ModelForm):
    """ModelForm for the BrandingSetting singleton. Validates colours + logo."""

    class Meta:
        model = BrandingSetting
        fields = [
            "company_name", "company_tagline", "company_logo",
            "pdf_header_image", "pdf_footer_image",
            "primary_colour", "accent_colour",
            "support_email", "support_phone", "website",
            "pdf_footer_note",
        ]
        widgets = {
            "company_name":    forms.TextInput(attrs={"class": "form-control", "maxlength": 120}),
            "company_tagline": forms.TextInput(attrs={"class": "form-control", "maxlength": 200,
                                                       "placeholder": _("Optional short tagline")}),
            "company_logo":    forms.ClearableFileInput(attrs={"class": "form-control",
                                                                "accept": "image/png,image/jpeg,image/webp,image/svg+xml"}),
            "pdf_header_image": forms.ClearableFileInput(attrs={"class": "form-control",
                                                                "accept": "image/png,image/jpeg,image/webp,image/svg+xml"}),
            "pdf_footer_image": forms.ClearableFileInput(attrs={"class": "form-control",
                                                                "accept": "image/png,image/jpeg,image/webp,image/svg+xml"}),
            "primary_colour":  forms.TextInput(attrs={"class": "form-control", "placeholder": "#7c3aed",
                                                       "maxlength": 7}),
            "accent_colour":   forms.TextInput(attrs={"class": "form-control", "placeholder": "#0ea5e9",
                                                       "maxlength": 7}),
            "support_email":   forms.EmailInput(attrs={"class": "form-control",
                                                        "placeholder": "support@example.com"}),
            "support_phone":   forms.TextInput(attrs={"class": "form-control",
                                                       "placeholder": "+27 11 555 1234"}),
            "website":         forms.URLInput(attrs={"class": "form-control",
                                                      "placeholder": "https://www.example.com"}),
            "pdf_footer_note": forms.TextInput(attrs={"class": "form-control", "maxlength": 300,
                                                       "placeholder": _("Shown at the bottom of every PDF")}),
        }

    def clean_company_name(self):
        name = (self.cleaned_data.get("company_name") or "").strip()
        if not name:
            raise ValidationError(_("Company name is required."))
        return name

    def _clean_colour(self, value):
        value = (value or "").strip()
        if not value:
            return ""
        if not HEX_COLOUR_RE.match(value):
            raise ValidationError(_("Use a hex colour in the format #RRGGBB (e.g. #7c3aed)."))
        return value.lower()

    def clean_primary_colour(self):
        return self._clean_colour(self.cleaned_data.get("primary_colour"))

    def clean_accent_colour(self):
        return self._clean_colour(self.cleaned_data.get("accent_colour"))

    def _clean_uploaded_brand_image(self, field_name):
        f = self.cleaned_data.get(field_name)
        if not f or not hasattr(f, "size"):
            return f
        if f.size > MAX_LOGO_BYTES:
            raise ValidationError(_("Image must be 2 MB or smaller."))
        content_type = (getattr(f, "content_type", "") or "").lower()
        if content_type and content_type not in ALLOWED_LOGO_TYPES:
            raise ValidationError(
                _("Unsupported image type. Use PNG, JPEG, WebP or SVG.")
            )
        return f

    def clean_company_logo(self):
        return self._clean_uploaded_brand_image("company_logo")

    def clean_pdf_header_image(self):
        return self._clean_uploaded_brand_image("pdf_header_image")

    def clean_pdf_footer_image(self):
        return self._clean_uploaded_brand_image("pdf_footer_image")
