"""
Add product catalogue pack 3A: pricing_method, package fields, variant, notes, standard_coats
and extend Category choices.
"""
from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("paints", "0002_pricing_pack_1a"),
    ]

    operations = [
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
                    ("TEXTURE", "Texture"),
                    ("SPECIALIST", "Specialist"),
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
        migrations.AddField(
            model_name="paint",
            name="pricing_method",
            field=models.CharField(
                verbose_name='pricing method',
                max_length=20,
                choices=[
                    ("AREA_COATING", "Area-based coating"),
                    ("FIXED_PACK", "Fixed package"),
                    ("PER_METRE", "Per metre"),
                    ("NOTE_ONLY", "Note only"),
                ],
                default="AREA_COATING",
            ),
        ),
        migrations.AddField(
            model_name="paint",
            name="package_size",
            field=models.DecimalField(
                verbose_name='package size',
                max_digits=7,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="paint",
            name="package_unit",
            field=models.CharField(
                verbose_name='package unit',
                max_length=10,
                choices=[
                    ("L", "L"),
                    ("kg", "kg"),
                    ("m", "m"),
                    ("NA", "Not Applicable"),
                ],
                default="NA",
            ),
        ),
        migrations.AddField(
            model_name="paint",
            name="variant_label",
            field=models.CharField(verbose_name='variant label', max_length=50, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="paint",
            name="predetermined_note",
            field=models.TextField(verbose_name='predetermined note', blank=True, default=""),
        ),
        migrations.AddField(
            model_name="paint",
            name="standard_coats",
            field=models.PositiveSmallIntegerField(verbose_name='standard coats', null=True, blank=True, validators=[django.core.validators.MinValueValidator(1)]),
        ),
    ]
