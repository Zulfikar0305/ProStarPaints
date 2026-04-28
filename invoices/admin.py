from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "customer_name", "created_by", "status",
        "total_incl_vat", "is_removed", "created_at",
    ]
    list_filter = ["status", "is_removed", "created_at"]
    search_fields = ["reference", "customer_name", "customer_email", "created_by__username"]
    readonly_fields = ["reference", "created_at", "updated_at"]
    raw_id_fields = ["created_by"]

    fieldsets = [
        (_("Customer"), {"fields": ["customer_name", "customer_email", "customer_phone"]}),
        (_("Project"), {"fields": ["project_name", "project_location"]}),
        (_("Invoice"), {"fields": ["reference", "status", "subtotal_excl_vat", "vat_amount", "total_incl_vat", "notes"]}),
        (_("Metadata"), {"fields": ["created_by", "is_removed", "created_at", "updated_at"]}),
    ]

