import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import SalesRepProfile, User, UserAppSettings


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


# ---------------------------------------------------------------------------
# UserProfileForm — self-service update of User-level fields
# ---------------------------------------------------------------------------

class UserProfileForm(forms.ModelForm):
    """Lets the current user update their own base User fields."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone_number", "profile_image")
        widgets = {
            "first_name":    forms.TextInput(attrs={"class": "form-control"}),
            "last_name":     forms.TextInput(attrs={"class": "form-control"}),
            "email":         forms.EmailInput(attrs={"class": "form-control"}),
            "phone_number":  forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 082 123 4567 (optional)"}
            ),
            "profile_image": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "image/png,image/jpeg,image/webp"}
            ),
        }

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower().strip()
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(_("A user with that email address already exists."))
        return email

    def clean_phone_number(self) -> str:
        phone = self.cleaned_data.get("phone_number", "").strip()
        if phone:
            _validate_sa_phone(phone)
        return phone

    def clean_profile_image(self):
        image = self.cleaned_data.get("profile_image")
        if image and hasattr(image, "name"):
            ext = image.name.rsplit(".", 1)[-1].lower() if "." in image.name else ""
            if ext not in {"png", "jpg", "jpeg", "webp"}:
                raise ValidationError(
                    _("Profile image must be PNG, JPG, JPEG, or WebP.")
                )
            if image.size > 5 * 1024 * 1024:
                raise ValidationError(_("Profile image must be 5 MB or smaller."))
        return image


# ---------------------------------------------------------------------------
# SalesRepProfileForm — extended business profile
# ---------------------------------------------------------------------------

class SalesRepProfileForm(forms.ModelForm):
    """Extended business / sales rep profile fields."""

    class Meta:
        model = SalesRepProfile
        fields = (
            "bio", "job_title", "department", "branch_location",
            "company_phone", "whatsapp_number", "business_email",
            "sales_region", "employee_code", "years_experience",
            "specialities", "default_quote_intro", "default_quote_footer",
            "signature_name", "signature_title",
        )
        widgets = {
            "bio": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "maxlength": 500}
            ),
            "job_title":        forms.TextInput(attrs={"class": "form-control"}),
            "department":       forms.TextInput(attrs={"class": "form-control"}),
            "branch_location":  forms.TextInput(attrs={"class": "form-control"}),
            "company_phone":    forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 011 123 4567"}
            ),
            "whatsapp_number":  forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 082 123 4567"}
            ),
            "business_email":   forms.EmailInput(attrs={"class": "form-control"}),
            "sales_region":     forms.TextInput(attrs={"class": "form-control"}),
            "employee_code":    forms.TextInput(attrs={"class": "form-control"}),
            "years_experience": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 50}
            ),
            "specialities": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "maxlength": 300}
            ),
            "default_quote_intro": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "maxlength": 1000}
            ),
            "default_quote_footer": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "maxlength": 1000}
            ),
            "signature_name":  forms.TextInput(attrs={"class": "form-control"}),
            "signature_title": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_company_phone(self) -> str:
        phone = self.cleaned_data.get("company_phone", "").strip()
        if phone:
            _validate_sa_phone(phone)
        return phone

    def clean_whatsapp_number(self) -> str:
        phone = self.cleaned_data.get("whatsapp_number", "").strip()
        if phone:
            _validate_sa_phone(phone)
        return phone

    def clean_years_experience(self):
        val = self.cleaned_data.get("years_experience")
        if val is not None and val < 0:
            raise ValidationError(_("Years of experience cannot be negative."))
        return val


# ---------------------------------------------------------------------------
# UserAppSettingsForm — personal UI/display preferences
# ---------------------------------------------------------------------------

class UserAppSettingsForm(forms.ModelForm):
    """Let users update their own appearance and display preferences."""

    VALID_ROWS = {10, 25, 50}
    # Safe keys for the PDF template choice; mirrors quotation.pdf_templates
    VALID_PDF_TEMPLATES = {"professional", "detailed_spec", "compact"}
    VALID_LANDING_PAGES = {"dashboard", "quotations", "new_quotation", "profile"}

    class Meta:
        model = UserAppSettings
        fields = (
            # Appearance
            "appearance", "accent_style",
            # Display
            "table_density", "default_dashboard_period",
            "rows_per_page", "builder_summary_default",
            # Dashboard
            "default_landing_page",
            "show_onboarding_checklist", "show_data_quality_widget",
            "show_recent_activity_widget", "show_draft_quotations_widget",
            # Quotation
            "preferred_quotation_view", "default_quotation_sort",
            "auto_collapse_builder_summary_mobile", "show_builder_help_tips",
            # PDF
            "preferred_pdf_template", "remember_last_pdf_template",
            # Navigation
            "show_quick_actions_fab", "show_command_palette_hint",
            "compact_navigation",
            # Behaviour
            "reduce_animations", "show_watermark", "show_help_text",
            # Accessibility
            "larger_text", "high_contrast_mode",
            # Notifications
            "email_notifications_enabled",
            "notify_profile_incomplete", "notify_draft_quotations",
            "notify_failed_pdfs", "notify_placeholder_sections",
            "notify_system_activity",
        )
        widgets = {
            "appearance":                forms.Select(attrs={"class": "form-select"}),
            "accent_style":              forms.Select(attrs={"class": "form-select"}),
            "table_density":             forms.Select(attrs={"class": "form-select"}),
            "default_dashboard_period":  forms.Select(attrs={"class": "form-select"}),
            "rows_per_page":             forms.Select(attrs={"class": "form-select"}),
            "builder_summary_default":   forms.Select(attrs={"class": "form-select"}),
            "default_landing_page":      forms.Select(attrs={"class": "form-select"}),
            "preferred_quotation_view":  forms.Select(attrs={"class": "form-select"}),
            "default_quotation_sort":    forms.Select(attrs={"class": "form-select"}),
            "preferred_pdf_template":    forms.Select(attrs={"class": "form-select"}),
            # Switches
            "reduce_animations":                    forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_watermark":                       forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_help_text":                       forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "email_notifications_enabled":          forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_onboarding_checklist":            forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_data_quality_widget":             forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_recent_activity_widget":          forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_draft_quotations_widget":         forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "auto_collapse_builder_summary_mobile": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_builder_help_tips":               forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "remember_last_pdf_template":           forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_quick_actions_fab":               forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_command_palette_hint":            forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "compact_navigation":                   forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "larger_text":                          forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "high_contrast_mode":                   forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_profile_incomplete":            forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_draft_quotations":              forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_failed_pdfs":                   forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_placeholder_sections":          forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_system_activity":               forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_rows_per_page(self):
        val = self.cleaned_data.get("rows_per_page")
        if val not in self.VALID_ROWS:
            raise ValidationError(_("Rows per page must be 10, 25, or 50."))
        return val

    def clean_preferred_pdf_template(self):
        val = self.cleaned_data.get("preferred_pdf_template")
        if val not in self.VALID_PDF_TEMPLATES:
            raise ValidationError(_("Please choose a valid PDF template."))
        return val

    def clean_default_landing_page(self):
        val = self.cleaned_data.get("default_landing_page")
        if val not in self.VALID_LANDING_PAGES:
            raise ValidationError(_("Please choose a valid landing page."))
        return val

