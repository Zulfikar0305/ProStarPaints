from django.contrib import admin

from .models import QuotationPdfExport


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
