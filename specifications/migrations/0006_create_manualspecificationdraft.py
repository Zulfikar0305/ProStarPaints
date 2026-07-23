from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("specifications", "0005_add_specificationrule"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManualSpecificationDraft",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, blank=True)),
                ("data", models.JSONField(default=dict, blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("status", models.CharField(default="DRAFT", max_length=20, choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published")])),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "quotation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="spec_drafts",
                        to="quotation.Quotation",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
