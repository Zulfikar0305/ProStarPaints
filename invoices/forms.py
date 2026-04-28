from decimal import ROUND_HALF_UP, Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Invoice

_INPUT = "form-control"
_INPUT_SM = "form-control form-control-sm"
_SELECT = "form-select"


def _get_vat_rate() -> Decimal:
    from system_tools.models import AppSetting
    return AppSetting.get_vat_rate()


class InvoiceForm(forms.ModelForm):
    """
    Form for creating and updating Invoice records.
    Server-side VAT auto-calculation:
    - If subtotal_excl_vat entered → compute vat_amount and total_incl_vat
    - If total_incl_vat entered and subtotal is 0/blank → back-calculate subtotal and vat_amount
    - If all three provided → validate they're self-consistent
    """

    class Meta:
        model = Invoice
        fields = [
            "customer_name",
            "customer_email",
            "customer_phone",
            "project_name",
            "project_location",
            "status",
            "subtotal_excl_vat",
            "vat_amount",
            "total_incl_vat",
            "notes",
        ]
        widgets = {
            "customer_name":    forms.TextInput(attrs={"class": _INPUT, "placeholder": "Full name or company"}),
            "customer_email":   forms.EmailInput(attrs={"class": _INPUT, "placeholder": "email@example.com"}),
            "customer_phone":   forms.TextInput(attrs={"class": _INPUT, "placeholder": "+27 …"}),
            "project_name":     forms.TextInput(attrs={"class": _INPUT, "placeholder": "Project or job name"}),
            "project_location": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Site address or area"}),
            "status":           forms.Select(attrs={"class": _SELECT}),
            "subtotal_excl_vat": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0", "id": "id_subtotal_excl_vat"}),
            "vat_amount":        forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0", "id": "id_vat_amount", "readonly": "readonly"}),
            "total_incl_vat":    forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0", "id": "id_total_incl_vat"}),
            "notes": forms.Textarea(attrs={"class": _INPUT, "rows": 3, "placeholder": "Optional notes…"}),
        }

    def clean(self):
        cleaned = super().clean()
        subtotal = cleaned.get("subtotal_excl_vat")
        total = cleaned.get("total_incl_vat")
        vat = cleaned.get("vat_amount")

        # Basic negative checks
        for field, value in [
            ("subtotal_excl_vat", subtotal),
            ("vat_amount", vat),
            ("total_incl_vat", total),
        ]:
            if value is not None and value < 0:
                self.add_error(field, _("This amount cannot be negative."))

        # Stop further processing if there are already errors
        if self.errors:
            return cleaned

        vat_rate = _get_vat_rate()
        multiplier = Decimal("1") + vat_rate / Decimal("100")
        zero = Decimal("0")

        subtotal = subtotal or zero
        total = total or zero
        vat = vat or zero

        if subtotal > zero and total == zero:
            # Forward-calculate from subtotal
            vat_calc = (subtotal * vat_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cleaned["vat_amount"] = vat_calc
            cleaned["total_incl_vat"] = (subtotal + vat_calc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        elif total > zero and subtotal == zero:
            # Back-calculate from total
            subtotal_calc = (total / multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            vat_calc = (total - subtotal_calc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cleaned["subtotal_excl_vat"] = subtotal_calc
            cleaned["vat_amount"] = vat_calc

        elif subtotal > zero and total > zero:
            # Both provided — validate consistency
            expected_vat = (subtotal * vat_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            expected_total = (subtotal + expected_vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if abs(total - expected_total) > Decimal("0.02"):
                self.add_error(
                    "total_incl_vat",
                    _("Total (incl. VAT) does not match the expected calculation "
                      "(%(expected)s at %(rate)s%% VAT).")
                    % {"expected": expected_total, "rate": vat_rate},
                )
            else:
                cleaned["vat_amount"] = expected_vat

        if total < subtotal:
            self.add_error(
                "total_incl_vat",
                _("Total (incl. VAT) cannot be less than the subtotal (excl. VAT)."),
            )

        return cleaned
