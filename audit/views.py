from django.contrib.auth import get_user_model
from django.views.generic import ListView

from users.mixins import AdminRequiredMixin

from .filters import apply_audit_filters, get_filter_choices
from .models import AuditLog


class AuditLogListView(AdminRequiredMixin, ListView):
    """Read-only audit log viewer for ADMIN users and superusers."""

    model = AuditLog
    template_name = "audit/audit_log_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user").order_by("-created_at")
        return apply_audit_filters(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        ctx["q"] = get.get("q", "")
        ctx["current_module"] = get.get("module", "")
        ctx["current_action"] = get.get("action", "")
        ctx["current_user"] = get.get("user", "")
        ctx["date_from"] = get.get("date_from", "")
        ctx["date_to"] = get.get("date_to", "")

        choices = get_filter_choices()
        ctx["module_choices"] = choices["modules"]
        ctx["action_choices"] = choices["actions"]
        ctx["user_choices"] = list(
            get_user_model()
            .objects.filter(audit_logs__isnull=False)
            .distinct()
            .order_by("username")
            .values("id", "username")
        )

        params = get.copy()
        params.pop("page", None)
        ctx["filter_querystring"] = params.urlencode()
        ctx["has_active_filters"] = any([
            ctx["q"], ctx["current_module"], ctx["current_action"],
            ctx["current_user"], ctx["date_from"], ctx["date_to"],
        ])
        return ctx
