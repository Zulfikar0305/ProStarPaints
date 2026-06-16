from django.db import connection, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model


class SelectionOrderBackfillMigrationTest(TransactionTestCase):
    """Migration test for quotation 0004 -> 0006 backfill of selection_order.

    Creates historical rows at migration 0004 (selection_order nullable),
    then migrates to 0006 and asserts deterministic backfill and constraint.
    """

    migrate_from = ("quotation", "0004_add_selection_order_nullable")
    migrate_to = ("quotation", "0006_make_selection_order_nonnull_and_constraint")

    def test_backfill_and_constraint(self):
        executor = MigrationExecutor(connection)

        # 1) Migrate to the older state (0004)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Quotation = old_apps.get_model("quotation", "Quotation")
        QuotationSection = old_apps.get_model("quotation", "QuotationSection")
        QuotationLineItem = old_apps.get_model("quotation", "QuotationLineItem")

        # Create a real user (current model) and reference by id in historical models
        User = get_user_model()
        user = User.objects.create_user(username="miguser", password="pass")

        # Historical fixtures at 0004: one quotation with three sections sharing subsection_key
        q1 = Quotation.objects.create(created_by_id=user.pk, customer_name="Q1", customer_email="", customer_phone="")

        # Deliberately non-sequential sort_order values and a duplicate sort_order
        s_a = QuotationSection.objects.create(quotation_id=q1.pk, subsection_key="same", display_name="A", sort_order=10)
        s_b = QuotationSection.objects.create(quotation_id=q1.pk, subsection_key="same", display_name="B", sort_order=5)
        s_c = QuotationSection.objects.create(quotation_id=q1.pk, subsection_key="same", display_name="C", sort_order=5)

        # Another subsection in the same quotation
        s_other = QuotationSection.objects.create(quotation_id=q1.pk, subsection_key="other", display_name="Other", sort_order=1)

        # Optionally a second quotation group
        q2 = Quotation.objects.create(created_by_id=user.pk, customer_name="Q2", customer_email="", customer_phone="")
        s2_a = QuotationSection.objects.create(quotation_id=q2.pk, subsection_key="same", display_name="Q2_A", sort_order=1)

        # Line item attached to one of the duplicate sections
        li = QuotationLineItem.objects.create(quotation_id=q1.pk, section_id=s_c.pk, item_type="NOTE", description="note")

        # Record PKs for later verification
        section_pks = [s_a.pk, s_b.pk, s_c.pk, s_other.pk, s2_a.pk]
        li_pk = li.pk
        q1_pk = q1.pk
        q2_pk = q2.pk

        # 2) Migrate forward to 0006 (backfill + make non-null + add uniqueness constraint)
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state(self.migrate_to).apps

        NewSection = new_apps.get_model("quotation", "QuotationSection")
        NewLineItem = new_apps.get_model("quotation", "QuotationLineItem")

        # 3) Assertions
        # a) Sections in each (quotation_id, subsection_key) group receive selection_order = 1,2,3...
        q1_same = list(NewSection.objects.filter(quotation_id=q1_pk, subsection_key="same").order_by("sort_order", "pk"))
        for expected_order, sec in enumerate(q1_same, start=1):
            self.assertEqual(sec.selection_order, expected_order, f"Section {sec.pk} expected order {expected_order}")

        # b) Different subsection restarts at 1
        other_secs = list(NewSection.objects.filter(quotation_id=q1_pk, subsection_key="other").order_by("sort_order", "pk"))
        self.assertTrue(len(other_secs) >= 1)
        self.assertEqual(other_secs[0].selection_order, 1)

        # c) Different quotation restarts at 1
        q2_same = list(NewSection.objects.filter(quotation_id=q2_pk, subsection_key="same").order_by("sort_order", "pk"))
        self.assertTrue(len(q2_same) >= 1)
        self.assertEqual(q2_same[0].selection_order, 1)

        # d) Every original section PK still exists (no deletion/merge)
        existing_count = NewSection.objects.filter(pk__in=section_pks).count()
        self.assertEqual(existing_count, len(section_pks))

        # e) Line-item's section_id is unchanged
        li_new = NewLineItem.objects.get(pk=li_pk)
        self.assertEqual(li_new.section_id, s_c.pk)

        # f) No section or line-item was deleted, merged, or recreated: verify pk counts remain
        total_sections = NewSection.objects.filter(pk__in=section_pks).count()
        self.assertEqual(total_sections, len(section_pks))
        self.assertTrue(NewLineItem.objects.filter(pk=li_pk).exists())

        # g) Final uniqueness constraint is active: attempting to create a duplicate selection_order should raise IntegrityError
        with self.assertRaises(IntegrityError):
            NewSection.objects.create(quotation_id=q1_pk, subsection_key="same", display_name="dupe", sort_order=99, selection_order=1)

        # 4) Restore DB to latest migration state so other tests are not affected
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
