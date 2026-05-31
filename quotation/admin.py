from django.contrib import admin

from .models import QuotationPdfExport, QuotationPin


@admin.register(QuotationPdfExport)
class QuotationPdfExportAdmin(admin.ModelAdmin):
    list_display  = ("quotation", "generated_by", "template_key", "status", "created_at")
    list_filter   = ("status", "template_key")
    ordering      = ("-created_at",)
    readonly_fields = (
        "quotation",
        "generated_by",
        "template_key",
        "file",
        "status",
        "error_message",
        "created_at",
    )


@admin.register(QuotationPin)
class QuotationPinAdmin(admin.ModelAdmin):
    list_display = ("user", "quotation", "created_at")
    list_filter  = ("user",)
    search_fields = ("user__username", "quotation__reference", "quotation__customer_name")
    ordering = ("-created_at",)
