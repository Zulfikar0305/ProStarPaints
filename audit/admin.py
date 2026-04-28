from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "module", "action", "description", "ip_address")
    list_filter = ("module", "action")
    search_fields = ("user__username", "user__email", "action", "module", "description")
    readonly_fields = (
        "user", "action", "module", "description",
        "metadata", "ip_address", "user_agent", "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
