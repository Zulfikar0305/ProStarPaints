from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from .notifications import get_data_quality
from .onboarding import get_admin_checklist, get_rep_checklist
from .services import get_admin_metrics, get_rep_metrics

_VALID_PERIODS = {"all", "this_month", "last_30_days"}


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        period = self.request.GET.get("period", "all")
        if period not in _VALID_PERIODS:
            period = "all"
        ctx["period"] = period

        is_admin = user.is_superuser or getattr(user, "role", None) == "ADMIN"
        ctx["is_admin"] = is_admin

        if is_admin:
            ctx.update(get_admin_metrics(period))
            ctx["onboarding"] = get_admin_checklist()
        else:
            ctx.update(get_rep_metrics(user, period))
            ctx["onboarding"] = get_rep_checklist(user)

        ctx["data_quality"] = get_data_quality(user)

        return ctx
