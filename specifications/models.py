from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class SpecificationTemplate(TimeStampedModel):
    name = models.CharField(max_length=200)
    key = models.SlugField(max_length=200, unique=True)
    content = models.TextField(blank=True)
    # Flexible configuration storage for document template sections
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class KnowledgeCategory(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class KnowledgeEntry(TimeStampedModel):
    title = models.CharField(max_length=200)
    category = models.ForeignKey(
        KnowledgeCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entries",
    )
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class KnowledgeRule(TimeStampedModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    rule_type = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class MoistureRule(TimeStampedModel):
    name = models.CharField(max_length=200)
    min_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
