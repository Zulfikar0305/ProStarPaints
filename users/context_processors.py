"""
users.context_processors
========================
Makes UserAppSettings available in every template as `user_app_settings`.
For unauthenticated requests a safe defaults object is returned so templates
can always reference {{ user_app_settings.appearance }} etc. without errors.
"""

from .models import UserAppSettings


def user_app_settings(request):
    if not request.user.is_authenticated:
        # Return an unsaved instance with all defaults — no DB hit.
        return {"user_app_settings": UserAppSettings()}

    try:
        settings_obj = request.user.app_settings
    except UserAppSettings.DoesNotExist:
        settings_obj, _ = UserAppSettings.objects.get_or_create(user=request.user)

    return {"user_app_settings": settings_obj}
