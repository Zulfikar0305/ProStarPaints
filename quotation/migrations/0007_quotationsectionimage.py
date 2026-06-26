from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("quotation", "0006_make_selection_order_nonnull_and_constraint"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuotationSectionImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="quotation/images/", verbose_name="image")),
                ("sort_order", models.PositiveSmallIntegerField(default=0, verbose_name="sort order")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="quotation.quotationsection", verbose_name="section")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="quotation_section_images", to=settings.AUTH_USER_MODEL, verbose_name="uploaded by")),
            ],
            options={
                "ordering": ["section__pk", "sort_order", "pk"],
                "verbose_name": "quotation section image",
                "verbose_name_plural": "quotation section images",
            },
        ),
    ]
