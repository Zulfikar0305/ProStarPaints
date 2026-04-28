from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import SystemToolRun


@admin.register(SystemToolRun)
class SystemToolRunAdmin(admin.ModelAdmin):
    list_display = ["tool_name", "status", "run_by", "summary", "created_at"]
    list_filter = ["status", "tool_name", "created_at"]
    search_fields = ["tool_name", "summary", "run_by__username"]
    readonly_fields = ["run_by", "tool_name", "status", "summary", "result_data", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

