from django.contrib import admin

from .models import Paint


@admin.register(Paint)
class PaintAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "paint_type", "base_type", "finish",
        "colour", "price_excl_vat", "price_incl_vat", "is_active", "created_at",
    )
    list_filter = ("category", "paint_type", "base_type", "finish", "is_active")
    search_fields = ("name", "colour", "description")
    ordering = ("category", "name")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Product Details", {
            "fields": ("name", "description", "category", "paint_type", "base_type", "finish", "colour", "image"),
        }),
        ("Pricing", {
            "fields": ("price_excl_vat", "price_incl_vat", "priced_volume_litres", "spread_rate_per_litre"),
        }),
        ("Status & Timestamps", {
            "fields": ("is_active", "created_at", "updated_at"),
        }),
    )
