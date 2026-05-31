from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import BrandingSetting, SystemToolRun


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


@admin.register(BrandingSetting)
class BrandingSettingAdmin(admin.ModelAdmin):
    list_display = ["company_name", "support_email", "updated_at", "updated_by"]
    readonly_fields = ["updated_at", "updated_by"]

    def has_add_permission(self, request):
        # Singleton: only allow adding if the row doesn't exist yet
        return not BrandingSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
