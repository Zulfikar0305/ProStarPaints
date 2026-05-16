from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from audit.services import log_action
from users.mixins import AdminRequiredMixin

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

