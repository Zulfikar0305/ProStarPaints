from django.urls import path

from .views import (
    AppSettingsView,
    RunSystemToolView,
    SystemSettingsView,
    SystemToolsDashboardView,
    ToolResultView,
    VATSettingsView,
)

app_name = "system_tools"

urlpatterns = [
    path("", SystemToolsDashboardView.as_view(), name="dashboard"),
    path("run/<slug:slug>/", RunSystemToolView.as_view(), name="run_tool"),
    path("result/<int:pk>/", ToolResultView.as_view(), name="tool_result"),
    path("system-settings/", SystemSettingsView.as_view(), name="system_settings"),
    # Legacy route — kept for backward compat; resolves to same view
    path("vat-settings/", VATSettingsView.as_view(), name="vat_settings"),
    path("app-settings/", AppSettingsView.as_view(), name="app_settings"),
]
