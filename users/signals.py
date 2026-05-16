"""
users.signals
=============
Auto-create SalesRepProfile and UserAppSettings whenever a User is saved
for the first time. Uses get_or_create so it is safe to run on existing
users (e.g. if the migration runs after users already exist).
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_extras(sender, instance, created, **kwargs):
    """Ensure every user has a SalesRepProfile and UserAppSettings."""
    if created:
        # Lazy import avoids any potential circular-import issues at startup.
        from .models import SalesRepProfile, UserAppSettings

        SalesRepProfile.objects.get_or_create(user=instance)
        UserAppSettings.objects.get_or_create(user=instance)
