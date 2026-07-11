from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("specifications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="specificationtemplate",
            name="config",
            field=models.JSONField(default=dict, blank=True),
        ),
    ]
