from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("specifications", "0004_replace_clausetrigger"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SpecificationRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
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
                ("name", models.CharField(max_length=200)),
                (
                    "rule_type",
                    models.CharField(
                        choices=[
                            ("MOISTURE", "Moisture"),
                            ("COVERAGE", "Coverage"),
                            ("AREA", "Area"),
                            ("SPREAD_RATE", "Spread Rate"),
                            ("COATS", "Number of Coats"),
                            ("PRODUCT_WARNING", "Product Warning"),
                            ("TEMPERATURE", "Temperature"),
                            ("CUSTOM", "Custom"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "min_value",
                    models.DecimalField(blank=True, decimal_places=4, max_digits=9, null=True),
                ),
                (
                    "max_value",
                    models.DecimalField(blank=True, decimal_places=4, max_digits=9, null=True),
                ),
                ("unit", models.CharField(blank=True, max_length=30)),
                ("notes", models.TextField(blank=True)),
                ("active", models.BooleanField(default=True)),
                (
                    "priority",
                    models.IntegerField(default=0, help_text="Lower values evaluate first"),
                ),
                (
                    "clauses",
                    models.ManyToManyField(
                        blank=True, related_name="spec_rules", to="specifications.knowledgeentry"
                    ),
                ),
            ],
            options={
                "ordering": ["priority", "pk"],
                "verbose_name": "Specification Rule",
                "verbose_name_plural": "Specification Rules",
            },
        ),
    ]
