from django.contrib import admin

from . import models


@admin.register(models.SpecificationTemplate)
class SpecificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "is_active", "created_at")
    search_fields = ("name", "key")


@admin.register(models.KnowledgeCategory)
class KnowledgeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(models.KnowledgeEntry)
class KnowledgeEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "kind", "is_default", "is_active", "sort_order", "created_at")
    list_filter = ("kind", "is_active", "is_published", "category")
    search_fields = ("title", "body")


@admin.register(models.KnowledgeRule)
class KnowledgeRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "rule_type", "active")
    search_fields = ("name", "rule_type")


@admin.register(models.MoistureRule)
class MoistureRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "min_percent", "max_percent", "active")
    search_fields = ("name",)
