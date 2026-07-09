from django.db import migrations, models


def populate_group_key(apps, schema_editor):
    Paint = apps.get_model('paints', 'Paint')
    try:
        # Import current paint groups mapping to preserve existing group assignments
        from quotation.config import PAINT_GROUPS
    except Exception:
        PAINT_GROUPS = {}

    for p in Paint.objects.all():
        name_lower = (p.name or '').lower()
        assigned = None
        for k, g in PAINT_GROUPS.items():
            try:
                paint_name = getattr(g, 'paint_name', '') or ''
                if paint_name.lower() in name_lower:
                    assigned = k
                    break
            except Exception:
                continue
        if assigned:
            p.group_key = assigned
            p.save(update_fields=['group_key'])


class Migration(migrations.Migration):

    dependencies = [
        ('paints', '0004_cleanup_pack_3b1'),
    ]

    operations = [
        migrations.AddField(
            model_name='paint',
            name='group_key',
            field=models.CharField(blank=True, help_text='Machine key linking this product to a PAINT_GROUPS entry for UI grouping', max_length=50, null=True),
        ),
        migrations.RunPython(populate_group_key, reverse_code=migrations.RunPython.noop),
    ]
