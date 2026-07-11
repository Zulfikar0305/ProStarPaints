from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("specifications", "0002_add_config_field"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgeentry",
            name="kind",
            field=models.CharField(choices=[('note', 'Note'), ('clause', 'Clause')], default='note', max_length=20),
        ),
        migrations.AddField(
            model_name="knowledgeentry",
            name="is_default",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="knowledgeentry",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="knowledgeentry",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='ClauseTrigger',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('clause', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='triggers', to='specifications.knowledgeentry')),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name': 'Clause Trigger',
                'verbose_name_plural': 'Clause Triggers',
            },
        ),
        migrations.AlterUniqueTogether(
            name='clausetrigger',
            unique_together={('content_type', 'object_id', 'clause')},
        ),
    ]
