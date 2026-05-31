from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from audit.filters import apply_audit_filters
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
from .forms import BrandingSettingForm, VATSettingsForm
from .models import AppSetting, BrandingSetting, SystemToolRun
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
# Branding settings (admin-only)
# ---------------------------------------------------------------------------

class BrandingSettingsView(AdminRequiredMixin, View):
    """Admin form for updating business identity / branding values."""

    template_name = "system_tools/branding_settings.html"

    def _diff(self, before: BrandingSetting, after: BrandingSetting) -> dict:
        fields = [
            "company_name", "company_tagline", "primary_colour", "accent_colour",
            "support_email", "support_phone", "website", "pdf_footer_note",
        ]
        changed = {}
        for f in fields:
            old = getattr(before, f) or ""
            new = getattr(after, f) or ""
            if str(old) != str(new):
                changed[f] = {"old": str(old), "new": str(new)}
        old_logo = getattr(before.company_logo, "name", "") or ""
        new_logo = getattr(after.company_logo, "name", "") or ""
        if old_logo != new_logo:
            changed["company_logo"] = {"old": old_logo, "new": new_logo}
        return changed

    def get(self, request):
        obj = BrandingSetting.load()
        form = BrandingSettingForm(instance=obj)
        return render(request, self.template_name, {"form": form, "branding_obj": obj})

    def post(self, request):
        obj = BrandingSetting.load()
        # Snapshot pre-change values for the audit diff
        snapshot = BrandingSetting.objects.get(pk=obj.pk)
        form = BrandingSettingForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.updated_by = request.user
            saved.save()
            changed = self._diff(snapshot, saved)
            log_action(
                user=request.user,
                action="BRANDING_SETTINGS_UPDATED",
                module="system_tools",
                description=(
                    f"Branding settings updated ({len(changed)} field(s) changed)."
                    if changed else "Branding settings saved (no field changes)."
                ),
                metadata={"changed": changed},
                request=request,
            )
            messages.success(request, _("Branding settings saved."))
            return redirect("system_tools:branding_settings")
        return render(request, self.template_name, {"form": form, "branding_obj": obj})


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
        import csv

        qs = AuditLog.objects.select_related("user").order_by("-created_at")
        qs = apply_audit_filters(qs, request.GET)
        qs = qs[: self.MAX_ROWS]

        log_action(
            user=request.user,
            action="AUDIT_LOG_EXPORTED",
            module="system_tools",
            description=f"Admin {request.user} exported audit log CSV.",
            metadata={
                "filters": {
                    k: request.GET.get(k, "")
                    for k in ("q", "module", "action", "user", "date_from", "date_to")
                },
            },
            request=request,
        )

        class _Echo:
            def write(self, value):
                return value

        writer = csv.writer(_Echo())
        header = [
            "timestamp", "user", "action", "module",
            "description", "ip_address", "user_agent",
        ]

        def _rows():
            yield writer.writerow(header)
            for log in qs.iterator(chunk_size=200):
                yield writer.writerow([
                    log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    (log.user.username if log.user else "system"),
                    log.action,
                    log.module,
                    (log.description or "").replace("\n", " ")[:500],
                    log.ip_address or "",
                    (log.user_agent or "")[:200],
                ])

        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        response = StreamingHttpResponse(_rows(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="audit-log-{ts}.csv"'
        return response


# ---------------------------------------------------------------------------
# PDF Exports admin — list, filter, inspect, CSV
# ---------------------------------------------------------------------------

class PdfExportsAdminView(AdminRequiredMixin, View):
    """Admin-only inspector for QuotationPdfExport rows."""

    template_name = "system_tools/pdf_exports.html"
    PAGE_SIZE = 50

    def get(self, request):
        from django.core.paginator import Paginator
        from django.db.models import Q
        from django.contrib.auth import get_user_model
        from quotation.models import QuotationPdfExport
        from quotation.pdf_templates import PDF_TEMPLATES

        qs = (
            QuotationPdfExport.objects
            .select_related("quotation", "generated_by")
            .order_by("-created_at")
        )

        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(quotation__reference__icontains=q)
                | Q(quotation__customer_name__icontains=q)
                | Q(quotation__project_name__icontains=q)
                | Q(template_key__icontains=q)
                | Q(generated_by__username__icontains=q)
                | Q(generated_by__email__icontains=q)
            )

        status = (request.GET.get("status") or "").strip()
        if status in {"GENERATED", "FAILED"}:
            qs = qs.filter(status=status)

        template_key = (request.GET.get("template") or "").strip()
        if template_key:
            qs = qs.filter(template_key=template_key)

        user_id = (request.GET.get("generated_by") or "").strip()
        if user_id.isdigit():
            qs = qs.filter(generated_by_id=int(user_id))

        date_from = (request.GET.get("date_from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = (request.GET.get("date_to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        total = qs.count()
        paginator = Paginator(qs, self.PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get("page"))

        # Decorate page rows with display name + file size (best-effort)
        rows = []
        for exp in page_obj.object_list:
            tpl = PDF_TEMPLATES.get(exp.template_key, {})
            size = None
            if exp.file:
                try:
                    size = exp.file.size
                except (OSError, ValueError):
                    size = None
            rows.append({
                "obj": exp,
                "template_name": tpl.get("name", exp.template_key),
                "file_size": size,
            })

        User = get_user_model()
        params = request.GET.copy()
        params.pop("page", None)

        return render(request, self.template_name, {
            "rows": rows,
            "page_obj": page_obj,
            "is_paginated": page_obj.has_other_pages(),
            "total": total,
            "q": q,
            "current_status": status,
            "current_template": template_key,
            "current_user": user_id,
            "date_from": date_from,
            "date_to": date_to,
            "template_choices": [
                {"key": k, "name": v.get("name", k)}
                for k, v in PDF_TEMPLATES.items()
            ],
            "user_choices": list(
                User.objects.filter(pdf_exports__isnull=False)
                .distinct()
                .order_by("username")
                .values("id", "username")
            ),
            "status_choices": [
                ("GENERATED", _("Generated")),
                ("FAILED", _("Failed")),
            ],
            "filter_querystring": params.urlencode(),
            "has_active_filters": any(
                [q, status, template_key, user_id, date_from, date_to]
            ),
        })


class PdfExportsCsvView(AdminRequiredMixin, View):
    """CSV export of the PDF Exports admin list, honouring filters."""

    MAX_ROWS = 5000

    def get(self, request):
        import csv
        from django.db.models import Q
        from quotation.models import QuotationPdfExport
        from quotation.pdf_templates import PDF_TEMPLATES

        qs = (
            QuotationPdfExport.objects
            .select_related("quotation", "generated_by")
            .order_by("-created_at")
        )

        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(quotation__reference__icontains=q)
                | Q(quotation__customer_name__icontains=q)
                | Q(quotation__project_name__icontains=q)
                | Q(template_key__icontains=q)
                | Q(generated_by__username__icontains=q)
                | Q(generated_by__email__icontains=q)
            )
        status = (request.GET.get("status") or "").strip()
        if status in {"GENERATED", "FAILED"}:
            qs = qs.filter(status=status)
        template_key = (request.GET.get("template") or "").strip()
        if template_key:
            qs = qs.filter(template_key=template_key)
        user_id = (request.GET.get("generated_by") or "").strip()
        if user_id.isdigit():
            qs = qs.filter(generated_by_id=int(user_id))
        date_from = (request.GET.get("date_from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = (request.GET.get("date_to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        qs = qs[: self.MAX_ROWS]

        log_action(
            user=request.user,
            action="PDF_EXPORTS_EXPORTED",
            module="system_tools",
            description=f"Admin {request.user} exported PDF exports CSV.",
            metadata={
                "filters": {
                    "q": q, "status": status, "template": template_key,
                    "generated_by": user_id,
                    "date_from": date_from, "date_to": date_to,
                },
            },
            request=request,
        )

        class _Echo:
            def write(self, value):
                return value

        writer = csv.writer(_Echo())
        header = [
            "created_at", "quotation_reference", "customer_name",
            "project_name", "template_key", "template_name",
            "generated_by", "status", "error_message", "file",
        ]

        def _rows():
            yield writer.writerow(header)
            for exp in qs.iterator(chunk_size=200):
                tpl = PDF_TEMPLATES.get(exp.template_key, {})
                yield writer.writerow([
                    exp.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    exp.quotation.reference if exp.quotation_id else "",
                    (exp.quotation.customer_name if exp.quotation_id else "") or "",
                    (exp.quotation.project_name if exp.quotation_id else "") or "",
                    exp.template_key,
                    tpl.get("name", exp.template_key),
                    (exp.generated_by.username if exp.generated_by_id else "system"),
                    exp.status,
                    (exp.error_message or "").replace("\n", " ")[:500],
                    (exp.file.name if exp.file else ""),
                ])

        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        response = StreamingHttpResponse(_rows(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="pdf-exports-{ts}.csv"'
        return response
