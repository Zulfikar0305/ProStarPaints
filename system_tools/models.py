from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SystemToolRun(models.Model):
    """
    Immutable record of a system-tool scan run by an admin.
    Never edited or deleted through the application UI.
    """

    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", _("Success")
        WARNING = "WARNING", _("Warning")
        ERROR   = "ERROR",   _("Error")

    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_tool_runs",
        verbose_name=_("run by"),
    )
    tool_name = models.CharField(_("tool name"), max_length=100)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.SUCCESS,
        db_index=True,
    )
    summary = models.TextField(_("summary"))
    result_data = models.JSONField(_("result data"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("system tool run")
        verbose_name_plural = _("system tool runs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["tool_name"]),
        ]

    def __str__(self) -> str:
        user = self.run_by.username if self.run_by else "unknown"
        return f"[{self.tool_name}] {self.status} by {user} at {self.created_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Application-wide key/value settings
# ---------------------------------------------------------------------------

class AppSetting(models.Model):
    """
    Key-value store for application-wide configuration settings.
    Used for VAT rate and any future global settings.
    """

    VAT_RATE_KEY = "VAT_RATE"
    DEFAULT_VAT_RATE = Decimal("15.00")

    key = models.CharField(
        _("key"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("Unique identifier for this setting, e.g. VAT_RATE"),
    )
    value = models.CharField(
        _("value"),
        max_length=500,
        help_text=_("String representation of the setting value"),
    )
    description = models.TextField(_("description"), blank=True, default="")
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="setting_updates",
        verbose_name=_("updated by"),
    )

    class Meta:
        verbose_name = _("app setting")
        verbose_name_plural = _("app settings")
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"

    # --- Convenience class methods ---

    @classmethod
    def get_value(cls, key: str, default: str = "") -> str:
        """Return the stored value for a key, or *default* if not found."""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def get_vat_rate(cls) -> Decimal:
        """Return the current VAT rate as a Decimal. Falls back to 15.00."""
        raw = cls.get_value(cls.VAT_RATE_KEY, str(cls.DEFAULT_VAT_RATE))
        try:
            return Decimal(raw)
        except InvalidOperation:
            return cls.DEFAULT_VAT_RATE

