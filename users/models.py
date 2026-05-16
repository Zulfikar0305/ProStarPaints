import re

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


def validate_phone_number(value: str) -> None:
    """Allow only digits, spaces, +, -, and parentheses; 7–15 digits total."""
    cleaned = re.sub(r"[\s\-\(\)\+]", "", value)
    if not cleaned.isdigit():
        raise ValidationError(_("Phone number may only contain digits, spaces, +, -, and parentheses."))
    if not (7 <= len(cleaned) <= 15):
        raise ValidationError(_("Phone number must contain between 7 and 15 digits."))


class User(AbstractUser):
    """
    Custom user model for ProStar Paints.

    Roles
    -----
    ADMIN  – Full system access; can create/manage rep accounts.
    REP    – Sales representative; can build and submit quotations.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", _("Admin")
        REP = "REP", _("Sales Rep")

    # Override email to make it required and unique
    email = models.EmailField(
        _("email address"),
        unique=True,
        error_messages={"unique": _("A user with that email address already exists.")},
    )

    # Additional fields
    phone_number = models.CharField(
        _("phone number"),
        max_length=20,
        blank=True,
        default="",
        validators=[validate_phone_number],
    )
    profile_image = models.ImageField(
        _("profile image"),
        upload_to="users/profile_images/",
        blank=True,
        null=True,
    )
    role = models.CharField(
        _("role"),
        max_length=10,
        choices=Role.choices,
        default=Role.REP,
    )

    # Timestamps (auto-managed)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Use email as the primary identifier for authentication
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.get_full_name()} ({self.email})"

    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN

    def is_rep_role(self) -> bool:
        return self.role == self.Role.REP


# ---------------------------------------------------------------------------
# Sales Rep Profile (extended business profile, OneToOne with User)
# ---------------------------------------------------------------------------

class SalesRepProfile(models.Model):
    """
    Extended business profile for every user.
    Core identity fields (profile_image, phone_number) live on User.
    This model holds business/sales-specific details.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sales_profile",
    )

    # ── Personal / business info ──────────────────────────────────
    bio = models.TextField(_("bio"), max_length=500, blank=True, default="")
    job_title = models.CharField(_("job title"), max_length=100, blank=True, default="")
    department = models.CharField(_("department"), max_length=100, blank=True, default="")
    branch_location = models.CharField(_("branch / office location"), max_length=100, blank=True, default="")
    company_phone = models.CharField(_("company phone"), max_length=20, blank=True, default="")
    whatsapp_number = models.CharField(_("WhatsApp number"), max_length=20, blank=True, default="")
    business_email = models.EmailField(_("business email"), blank=True, default="")
    sales_region = models.CharField(_("sales region"), max_length=100, blank=True, default="")
    employee_code = models.CharField(_("employee code"), max_length=30, blank=True, default="")
    years_experience = models.PositiveSmallIntegerField(_("years of experience"), null=True, blank=True)
    specialities = models.TextField(_("specialities"), max_length=300, blank=True, default="")

    # ── Quotation defaults ────────────────────────────────────────
    default_quote_intro = models.TextField(
        _("default quote intro"), max_length=1000, blank=True, default="",
        help_text=_("Introductory text auto-filled on new quotations."),
    )
    default_quote_footer = models.TextField(
        _("default quote footer"), max_length=1000, blank=True, default="",
        help_text=_("Footer / closing text auto-filled on new quotations."),
    )
    signature_name = models.CharField(_("signature name"), max_length=150, blank=True, default="")
    signature_title = models.CharField(_("signature title"), max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("sales rep profile")
        verbose_name_plural = _("sales rep profiles")

    def __str__(self) -> str:
        return f"Profile — {self.user}"

    def profile_completion_pct(self) -> int:
        """Return 0–100 indicating how complete the profile is."""
        # Fields on this model we consider "completable"
        profile_fields = [
            self.bio,
            self.job_title,
            self.department,
            self.branch_location,
            self.company_phone,
            self.business_email,
            self.sales_region,
            self.signature_name,
        ]
        filled = sum(1 for v in profile_fields if v)
        # Also count User-level completable fields
        try:
            if self.user.profile_image:
                filled += 1
            if self.user.phone_number:
                filled += 1
            total = len(profile_fields) + 2
        except Exception:
            total = len(profile_fields)
        return round(filled / total * 100) if total else 0


# ---------------------------------------------------------------------------
# User App Settings (per-user UI/behaviour preferences)
# ---------------------------------------------------------------------------

class UserAppSettings(models.Model):
    """Per-user UI preferences. Served globally via context processor."""

    class Appearance(models.TextChoices):
        LIGHT  = "light",  _("Light")
        DARK   = "dark",   _("Dark")
        SYSTEM = "system", _("System Default")

    class AccentStyle(models.TextChoices):
        DEFAULT       = "prostar_default", _("ProStar Default (Purple)")
        GREEN         = "green",           _("Green")
        HIGH_CONTRAST = "high_contrast",   _("High Contrast")

    class TableDensity(models.TextChoices):
        COMFORTABLE = "comfortable", _("Comfortable")
        COMPACT     = "compact",     _("Compact")

    class DashboardPeriod(models.TextChoices):
        ALL_TIME   = "all_time",    _("All Time")
        THIS_MONTH = "this_month",  _("This Month")
        LAST_30    = "last_30_days", _("Last 30 Days")

    class BuilderSummary(models.TextChoices):
        EXPANDED  = "expanded",  _("Expanded")
        COLLAPSED = "collapsed", _("Collapsed")

    ROWS_CHOICES = [(10, "10"), (25, "25"), (50, "50")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="app_settings",
    )

    # ── Appearance ────────────────────────────────────────────────
    appearance = models.CharField(
        _("appearance"), max_length=10,
        choices=Appearance.choices, default=Appearance.LIGHT,
    )
    accent_style = models.CharField(
        _("accent style"), max_length=20,
        choices=AccentStyle.choices, default=AccentStyle.DEFAULT,
    )

    # ── Display / layout ─────────────────────────────────────────
    table_density = models.CharField(
        _("table density"), max_length=15,
        choices=TableDensity.choices, default=TableDensity.COMFORTABLE,
    )
    default_dashboard_period = models.CharField(
        _("default dashboard period"), max_length=15,
        choices=DashboardPeriod.choices, default=DashboardPeriod.LAST_30,
    )
    rows_per_page = models.PositiveSmallIntegerField(
        _("rows per page"), choices=ROWS_CHOICES, default=25,
    )
    builder_summary_default = models.CharField(
        _("builder summary default"), max_length=10,
        choices=BuilderSummary.choices, default=BuilderSummary.EXPANDED,
    )

    # ── Behaviour ────────────────────────────────────────────────
    reduce_animations = models.BooleanField(_("reduce animations"), default=False)
    show_watermark = models.BooleanField(_("show watermark"), default=True)
    show_help_text = models.BooleanField(_("show help text"), default=True)

    # ── Notifications (placeholder) ──────────────────────────────
    email_notifications_enabled = models.BooleanField(
        _("email notifications enabled"), default=False,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("user app settings")
        verbose_name_plural = _("user app settings")

    def __str__(self) -> str:
        return f"Settings — {self.user}"
