from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import SalesRepProfile, User, UserAppSettings


class SalesRepProfileInline(admin.StackedInline):
    model = SalesRepProfile
    can_delete = False
    verbose_name_plural = _("Sales Rep Profile")
    fk_name = "user"
    extra = 0
    fields = (
        "job_title", "department", "branch_location", "sales_region",
        "company_phone", "whatsapp_number", "business_email", "employee_code",
        "years_experience", "specialities", "bio",
        "signature_name", "signature_title",
        "default_quote_intro", "default_quote_footer",
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [SalesRepProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active", "is_staff", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "phone_number")
    ordering = ("last_name", "first_name")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email", "phone_number", "profile_image")}),
        (_("Role & permissions"), {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )


@admin.register(SalesRepProfile)
class SalesRepProfileAdmin(admin.ModelAdmin):
    list_display  = ("user", "job_title", "department", "branch_location", "updated_at")
    search_fields = ("user__username", "user__email", "job_title", "department")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserAppSettings)
class UserAppSettingsAdmin(admin.ModelAdmin):
    list_display  = ("user", "appearance", "accent_style", "table_density", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = ("updated_at",)
