from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from audit.models import AuditLog
from audit.services import log_action
from users.mixins import AdminRequiredMixin

from .control_center import (
    get_paint_catalogue_quality,
    get_pdf_export_health,
    get_quotation_quality,
    get_recent_system_activity,
    get_setup_health,
    get_staff_readiness,
)
from .forms import VATSettingsForm
from .models import AppSetting, SystemToolRun
from .services import TOOL_REGISTRY, get_tool_display_name, run_tool


class SystemToolsDashboardView(AdminRequiredMixin, View):
    """Display available tool cards and recent run history."""

    def get(self, request):
        recent_runs = SystemToolRun.objects.select_related("run_by").order_by("-created_at")[:20]
        tools = [
            {"slug": slug, "name": name}
            for slug, (name, _) in TOOL_REGISTRY.items()
        ]
        return render(request, "system_tools/dashboard.html", {
            "tools": tools,
            "recent_runs": recent_runs,
        })


class RunSystemToolView(AdminRequiredMixin, View):
    """POST-only view that runs a single tool and redirects to the result."""

    def post(self, request, slug):
        if slug not in TOOL_REGISTRY:
            messages.error(request, _("Unknown tool: %(slug)s") % {"slug": slug})
            return redirect("system_tools:dashboard")

        result = run_tool(slug)
        display_name = get_tool_display_name(slug)

        # Persist result
        run = SystemToolRun.objects.create(
            run_by=request.user,
            tool_name=display_name,
            status=result["status"],
            summary=result["summary"],
            result_data={"checks": result.get("checks", [])},
        )

        # Audit log
        log_action(
            user=request.user,
            action="SYSTEM_TOOL_RUN",
            module="system_tools",
            description=f"Ran '{display_name}' — {result['status']}: {result['summary']}",
            metadata={"tool_slug": slug, "status": result["status"], "run_id": run.pk},
            request=request,
        )

        return redirect("system_tools:tool_result", pk=run.pk)


class ToolResultView(AdminRequiredMixin, View):
    """Display the saved result of a single SystemToolRun."""

    def get(self, request, pk):
        run = get_object_or_404(SystemToolRun, pk=pk)
        checks = (run.result_data or {}).get("checks", [])
        return render(request, "system_tools/tool_result.html", {
            "run": run,
            "checks": checks,
        })


# ---------------------------------------------------------------------------
# System Settings (admin-only: VAT rate, future system config)
# ---------------------------------------------------------------------------

class SystemSettingsView(AdminRequiredMixin, View):
    """Allow admins to view and update system-wide settings including VAT rate."""

    template_name = "system_tools/system_settings.html"

    def get(self, request):
        current_rate = AppSetting.get_vat_rate()
        form = VATSettingsForm(initial={"vat_rate": current_rate})
        return render(request, self.template_name, {
            "form": form,
            "current_rate": current_rate,
        })

    def post(self, request):
        form = VATSettingsForm(request.POST)
        if form.is_valid():
            old_rate = AppSetting.get_vat_rate()
            new_rate = form.cleaned_data["vat_rate"]

            AppSetting.objects.update_or_create(
                key=AppSetting.VAT_RATE_KEY,
                defaults={
                    "value": str(new_rate),
                    "description": "Application VAT rate as a percentage (e.g. 15.00 = 15%).",
                    "updated_by": request.user,
                },
            )

            log_action(
                user=request.user,
                action="VAT_RATE_UPDATED",
                module="system_tools",
                description=f"VAT rate updated from {old_rate}% to {new_rate}%.",
                metadata={"old_rate": str(old_rate), "new_rate": str(new_rate)},
                request=request,
            )

            messages.success(
                request,
                _("VAT rate updated to %(rate)s%%.") % {"rate": new_rate},
            )
            return redirect("system_tools:system_settings")

        return render(request, self.template_name, {
            "form": form,
            "current_rate": AppSetting.get_vat_rate(),
        })


# Backward-compat alias so any bookmarked /system-tools/vat-settings/ still works
VATSettingsView = SystemSettingsView


# ---------------------------------------------------------------------------
# App Settings (user-specific) — redirects to the users app
# ---------------------------------------------------------------------------

class AppSettingsView(LoginRequiredMixin, View):
    """Redirect to users:app_settings (backward-compat for existing bookmarks)."""

    def get(self, request):
        from django.shortcuts import redirect as _redirect
        return _redirect("users:app_settings")

    def post(self, request):
        from django.shortcuts import redirect as _redirect
        return _redirect("users:app_settings")



# ---------------------------------------------------------------------------
# Admin Control Center
# ---------------------------------------------------------------------------

class ControlCenterView(AdminRequiredMixin, View):
    """Executive system health cockpit. Admin/superuser only, read-only."""

    template_name = "system_tools/control_center.html"

    def get(self, request):
        setup_health           = get_setup_health()
        paint_quality          = get_paint_catalogue_quality()
        quotation_quality      = get_quotation_quality()
        staff_readiness        = get_staff_readiness()
        pdf_health             = get_pdf_export_health()
        recent_activity        = get_recent_system_activity()

        # Aggregate severity counts for the header
        all_statuses = (
            [c["status"]   for c in setup_health]
            + [i["severity"] for i in paint_quality["items"]]
            + [i["severity"] for i in quotation_quality["items"]]
            + [i["severity"] for i in staff_readiness["items"]]
        )
        summary = {
            "ready":   all_statuses.count("ready"),
            "warning": all_statuses.count("warning"),
            "info":    all_statuses.count("info"),
        }

        return render(request, self.template_name, {
            "setup_health":       setup_health,
            "paint_quality":      paint_quality,
            "quotation_quality":  quotation_quality,
            "staff_readiness":    staff_readiness,
            "pdf_health":         pdf_health,
            "recent_activity":    recent_activity,
            "summary":            summary,
        })


# ---------------------------------------------------------------------------
# Audit log CSV export (admin-only, honours existing filters)
# ---------------------------------------------------------------------------

class AuditLogCsvExportView(AdminRequiredMixin, View):
    """Stream a CSV of the audit log, applying the same filters as the list page."""

    MAX_ROWS = 5000

    def get(self, request):
        from django.db.models import Q
        import csv

        qs = AuditLog.objects.select_related("user").order_by("-created_at")

        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(action__icontains=q)
                | Q(module__icontains=q)
                | Q(description__icontains=q)
                | Q(user__username__icontains=q)
                | Q(user__email__icontains=q)
            )
        module = request.GET.get("module", "")
        if module:
            qs = qs.filter(module=module)
        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        qs = qs[: self.MAX_ROWS]

        log_action(
            user=request.user,
            action="AUDIT_LOG_EXPORTED",
            module="system_tools",
            description=f"Admin {request.user} exported audit log CSV.",
            metadata={
                "filters": {
                    "q": q, "module": module,
                    "date_from": date_from, "date_to": date_to,
                },
            },
            request=request,
        )

        class _Echo:
            def write(self, value):
                return value

        writer = csv.writer(_Echo())
        header = ["timestamp", "user", "module", "action", "description", "ip"]

        def _rows():
            yield writer.writerow(header)
            for log in qs.iterator(chunk_size=200):
                yield writer.writerow([
                    log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    (log.user.username if log.user else "system"),
                    log.module,
                    log.action,
                    (log.description or "").replace("\n", " ")[:500],
                    log.ip_address or "",
                ])

        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        response = StreamingHttpResponse(_rows(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="audit-log-{ts}.csv"'
        return response
