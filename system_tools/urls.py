from django.urls import path

from .views import (
    AppSettingsView,
    AuditLogCsvExportView,
    BrandingSettingsView,
    ControlCenterView,
    PdfExportsAdminView,
    PdfExportsCsvView,
    RunSystemToolView,
    SystemSettingsView,
    SystemToolsDashboardView,
    ToolResultView,
    VATSettingsView,
)

app_name = "system_tools"

urlpatterns = [
    path("", SystemToolsDashboardView.as_view(), name="dashboard"),
    path("control-center/", ControlCenterView.as_view(), name="control_center"),
    path("control-center/audit-log.csv", AuditLogCsvExportView.as_view(), name="audit_log_csv"),
    path("audit-log.csv", AuditLogCsvExportView.as_view(), name="audit_log_csv_short"),
    path("pdf-exports/", PdfExportsAdminView.as_view(), name="pdf_exports"),
    path("pdf-exports.csv", PdfExportsCsvView.as_view(), name="pdf_exports_csv"),
    path("run/<slug:slug>/", RunSystemToolView.as_view(), name="run_tool"),
    path("result/<int:pk>/", ToolResultView.as_view(), name="tool_result"),
    path("system-settings/", SystemSettingsView.as_view(), name="system_settings"),
    # Legacy route — kept for backward compat; resolves to same view
    path("vat-settings/", VATSettingsView.as_view(), name="vat_settings"),
    path("branding/", BrandingSettingsView.as_view(), name="branding_settings"),
    path("app-settings/", AppSettingsView.as_view(), name="app_settings"),
]
