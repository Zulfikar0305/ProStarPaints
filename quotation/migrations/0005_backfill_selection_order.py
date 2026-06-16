from django.db import migrations


def backfill_selection_order(apps, schema_editor):
    QuotationSection = apps.get_model('quotation', 'QuotationSection')
    from django.db import transaction

    with transaction.atomic():
        # Group by (quotation_id, subsection_key) and enumerate by sort_order, pk
        qs = QuotationSection.objects.all().order_by('quotation_id', 'subsection_key', 'sort_order', 'pk')
        last_key = None
        counter = 0
        for sec in qs:
            key = (sec.quotation_id, sec.subsection_key)
            if key != last_key:
                counter = 1
                last_key = key
            else:
                counter += 1
            sec.selection_order = counter
            sec.save(update_fields=['selection_order'])


class Migration(migrations.Migration):

    dependencies = [
        ('quotation', '0004_add_selection_order_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill_selection_order, migrations.RunPython.noop),
    ]
