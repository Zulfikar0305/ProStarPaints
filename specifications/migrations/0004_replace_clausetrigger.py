from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("specifications", "0003_clauses_and_triggers"),
    ]

    operations = [
        # Remove the GenericForeignKey-based ClauseTrigger and recreate a
        # simpler domain-specific ClauseTrigger with (trigger_type, trigger_key).
        migrations.DeleteModel(
            name="ClauseTrigger",
        ),
        migrations.CreateModel(
            name="ClauseTrigger",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ("trigger_type", models.CharField(max_length=100)),
                ("trigger_key", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "clause",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="triggers",
                        to="specifications.knowledgeentry",
                    ),
                ),
            ],
            options={
                "verbose_name": "Clause Trigger",
                "verbose_name_plural": "Clause Triggers",
            },
        ),
        migrations.AlterUniqueTogether(
            name="clausetrigger",
            unique_together={("trigger_type", "trigger_key", "clause")},
        ),
    ]
