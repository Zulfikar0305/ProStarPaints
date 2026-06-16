# Generated safe migration: add nullable selection_order
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quotation', '0003_quotationpin'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotationsection',
            name='selection_order',
            field=models.PositiveSmallIntegerField(null=True, blank=True),
        ),
    ]
