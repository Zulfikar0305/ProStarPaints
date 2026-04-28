from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditLog(models.Model):
    """
    Immutable record of a significant action performed in the system.
    Rows are written by audit.services.log_action and must never be
    edited or deleted through the application UI.
    """

    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name=_("user"),
    )

    # What
    action = models.CharField(_("action"), max_length=100)
    module = models.CharField(_("module"), max_length=100)
    description = models.TextField(_("description"), blank=True, default="")

    # Extra context (stored as JSON for flexibility)
    metadata = models.JSONField(_("metadata"), null=True, blank=True)

    # Request context
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=512, blank=True, default="")

    # When
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("audit log")
        verbose_name_plural = _("audit logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["module"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        username = self.user.username if self.user else "anonymous"
        return f"[{self.module}] {self.action} by {username} at {self.created_at:%Y-%m-%d %H:%M}"

