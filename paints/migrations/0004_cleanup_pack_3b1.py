"""
Cleanup legacy paint_type and remove unused category/base choices (Pack 3B1)

Operations:
- RemoveField paint_type
- AlterField category to remove TEXTURE and SPECIALIST
- AlterField base_type to remove MEDIUM and NATURAL
"""
from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("paints", "0003_product_catalogue_pack_3a"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="paint",
            name="paint_type",
        ),
        migrations.AlterField(
            model_name="paint",
            name="category",
            field=models.CharField(
                verbose_name='category',
                max_length=20,
                choices=[
                    ("INTERIOR", "Interior"),
                    ("EXTERIOR", "Exterior"),
                    ("PRIMER", "Primer"),
                    ("WATERPROOFING", "Waterproofing"),
                    ("CRACKS", "Cracks"),
                    ("MOULD", "Mould"),
                    ("CLEANING", "Cleaning"),
                    ("SANDING", "Sanding"),
                    ("EFFLORESCENCE", "Efflorescence"),
                    ("OLD_PAINT_REMOVAL", "Old Paint Removal"),
                ],
                default="INTERIOR",
            ),
        ),
        migrations.AlterField(
            model_name="paint",
            name="base_type",
            field=models.CharField(
                verbose_name='base type',
                max_length=20,
                choices=[
                    ("WHITE", "White"),
                    ("PASTEL", "Pastel Base"),
                    ("DEEP", "Deep Base"),
                    ("CLEAR", "Clear Base"),
                    ("TRANSPARENT", "Transparent Base"),
                    ("NOT_APPLICABLE", "Not Applicable"),
                ],
                default="WHITE",
            ),
        ),
    ]
