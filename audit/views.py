from django.db.models import Q
from django.views.generic import ListView

from users.mixins import AdminRequiredMixin

from .models import AuditLog


class AuditLogListView(AdminRequiredMixin, ListView):
    """Read-only audit log viewer for ADMIN users and superusers."""

    model = AuditLog
    template_name = "audit/audit_log_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user").order_by("-created_at")

        # Free-text search across key fields
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(action__icontains=q)
                | Q(module__icontains=q)
                | Q(description__icontains=q)
                | Q(user__username__icontains=q)
                | Q(user__email__icontains=q)
            )

        # Module filter
        module = self.request.GET.get("module", "")
        if module:
            qs = qs.filter(module=module)

        # Date-range filters (YYYY-MM-DD from date inputs)
        date_from = self.request.GET.get("date_from", "")
        date_to = self.request.GET.get("date_to", "")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["current_module"] = self.request.GET.get("module", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["module_choices"] = (
            AuditLog.objects.values_list("module", flat=True)
            .distinct()
            .order_by("module")
        )
        return ctx
