from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _


class AdminRequiredMixin(LoginRequiredMixin):
    """
    Allow access only to authenticated users who are ADMIN role or Django superusers.
    Redirect everyone else back to the login page with an error message.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, "role", None) == "ADMIN"):
            messages.error(request, _("You do not have permission to access that page."))
            return redirect("login")
        return super().dispatch(request, *args, **kwargs)
