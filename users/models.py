import re

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
