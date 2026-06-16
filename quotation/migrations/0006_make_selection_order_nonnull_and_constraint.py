from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quotation', '0005_backfill_selection_order'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quotationsection',
            name='selection_order',
            field=models.PositiveSmallIntegerField(verbose_name='selection order', default=1),
        ),
        migrations.AddConstraint(
            model_name='quotationsection',
            constraint=models.UniqueConstraint(fields=['quotation', 'subsection_key', 'selection_order'], name='uniq_quotation_subsection_selection_order'),
        ),
    ]
