import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import User


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _validate_sa_phone(value: str) -> None:
    """
    Validate a South African phone number.
    Accepts formats: +27821234567, 0821234567, 082 123 4567, etc.
    """
    if not value:
        return
    cleaned = re.sub(r"[\s\-\(\)\+]", "", value)
    if not cleaned.isdigit():
        raise ValidationError(_("Phone number may only contain digits, spaces, +, -, and parentheses."))
    # SA numbers: 10 digits local (0XXXXXXXXX) or 11 digits with country code (27XXXXXXXXX)
    if cleaned.startswith("27"):
        if len(cleaned) != 11:
            raise ValidationError(_("South African numbers with country code (+27) must have 11 digits total."))
    elif cleaned.startswith("0"):
        if len(cleaned) != 10:
            raise ValidationError(_("South African local numbers must have 10 digits (e.g. 082 123 4567)."))
    else:
        # Fallback: accept 7–15 digits for non-SA formats
        if not (7 <= len(cleaned) <= 15):
            raise ValidationError(_("Enter a valid phone number."))


# ---------------------------------------------------------------------------
# UserCreateForm
# ---------------------------------------------------------------------------

class UserCreateForm(UserCreationForm):
    """
    Form used by admin to create a new user (ADMIN or REP).
    Extends UserCreationForm to inherit password1/password2 with full validation.
    """

    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@example.com"}),
    )
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 082 123 4567 (optional)"}),
    )
    role = forms.ChoiceField(
        choices=User.Role.choices,
        initial=User.Role.REP,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "phone_number", "role")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Username"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"class": "form-control"})
        self.fields["password2"].widget.attrs.update({"class": "form-control"})

    # --- Field-level validation ---

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError(_("A user with that email address already exists."))
        return email

    def clean_phone_number(self) -> str:
        phone = self.cleaned_data.get("phone_number", "").strip()
        if phone:
            _validate_sa_phone(phone)
        return phone

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(_("A user with that username already exists."))
        return username

    # --- Cross-field validation ---

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("The two password fields didn't match."))
        return cleaned_data

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user


# ---------------------------------------------------------------------------
# UserUpdateForm
# ---------------------------------------------------------------------------

class UserUpdateForm(forms.ModelForm):
    """
    Form used by admin to update an existing user's profile and status.
    Password changes are handled separately; not included here.
    """

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "phone_number", "role", "is_active")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 082 123 4567 (optional)"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower().strip()
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(_("A user with that email address already exists."))
        return email

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        qs = User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(_("A user with that username already exists."))
        return username

    def clean_phone_number(self) -> str:
        phone = self.cleaned_data.get("phone_number", "").strip()
        if phone:
            _validate_sa_phone(phone)
        return phone
