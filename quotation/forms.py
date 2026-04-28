from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Quotation

_INPUT  = "form-control"
_SELECT = "form-select"


class QuotationStartForm(forms.ModelForm):
    """
    Collects the minimum customer / project information needed to open a
    DRAFT quotation.  Financial fields are populated later by the builder.
    """

    class Meta:
        model  = Quotation
        fields = [
            "customer_name",
            "customer_email",
            "customer_phone",
            "project_name",
            "project_location",
            "notes",
        ]
        widgets = {
            "customer_name":    forms.TextInput(attrs={
                "class": _INPUT, "placeholder": "Full name or company",
                "autofocus": True,
            }),
            "customer_email":   forms.EmailInput(attrs={
                "class": _INPUT, "placeholder": "email@example.com",
            }),
            "customer_phone":   forms.TextInput(attrs={
                "class": _INPUT, "placeholder": "+27 …",
            }),
            "project_name":     forms.TextInput(attrs={
                "class": _INPUT, "placeholder": "Project or job name",
            }),
            "project_location": forms.TextInput(attrs={
                "class": _INPUT, "placeholder": "Site address or area",
            }),
            "notes": forms.Textarea(attrs={
                "class": _INPUT, "rows": 3,
                "placeholder": "Optional notes…",
            }),
        }
        labels = {
            "customer_name":    _("Customer name"),
            "customer_email":   _("Email"),
            "customer_phone":   _("Phone"),
            "project_name":     _("Project name"),
            "project_location": _("Project location"),
            "notes":            _("Notes"),
        }
        help_texts = {
            "customer_email": _("Optional."),
            "customer_phone": _("Optional."),
            "project_name":   _("Optional."),
            "project_location": _("Optional."),
            "notes":          _("Optional."),
        }
