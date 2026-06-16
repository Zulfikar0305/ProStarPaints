from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import IntegrityError

from .models import Quotation, QuotationSection, QuotationLineItem
from .services import (
    create_repeatable_section,
    delete_repeatable_section,
    ALL_SUBSECTIONS,
)


class RepeatableSectionServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="svcuser", email="svcuser@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")

    def test_create_adds_one_section_and_orders(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        new = create_repeatable_section(quotation=self.q, subsection_key="interior_walls")
        secs = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").order_by("selection_order"))
        self.assertEqual(len(secs), 2)
        self.assertEqual(new.selection_order, 2)

    def test_new_section_uses_max_plus_one(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=2)
        new = create_repeatable_section(quotation=self.q, subsection_key="interior_walls")
        self.assertEqual(new.selection_order, 3)

    def test_existing_pks_and_lineitems_preserved(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        li = QuotationLineItem.objects.create(quotation=self.q, section=s1, item_type=QuotationLineItem.ItemType.NOTE, description="note")
        pk_before = s1.pk
        li_pk_before = li.pk
        new = create_repeatable_section(quotation=self.q, subsection_key="interior_walls")
        s1.refresh_from_db()
        li.refresh_from_db()
        self.assertEqual(s1.pk, pk_before)
        self.assertEqual(li.pk, li_pk_before)

    def test_new_section_is_placeholder_and_copies_cfg(self):
        cfg = ALL_SUBSECTIONS["interior_walls"]
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name=cfg.display_name)
        new = create_repeatable_section(quotation=self.q, subsection_key="interior_walls")
        self.assertTrue(new.is_placeholder)
        self.assertEqual(new.substrate_type, cfg.substrate)
        self.assertTrue(new.display_name.startswith(cfg.display_name))
        self.assertEqual(new.sort_order, cfg.sort_order)

    def test_create_rejects_unselected_category(self):
        # No existing "ceilings" selection
        with self.assertRaises(ValueError):
            create_repeatable_section(quotation=self.q, subsection_key="ceilings")

    def test_create_rejects_invalid_key(self):
        with self.assertRaises(ValueError):
            create_repeatable_section(quotation=self.q, subsection_key="no_such_key")

    def test_create_atomic_failure_rolls_back(self):
        # Ensure that if create() raises IntegrityError nothing is created
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        from quotation import models as qm

        with patch.object(qm.QuotationSection.objects, "create", side_effect=IntegrityError()):
            with self.assertRaises(IntegrityError):
                create_repeatable_section(quotation=self.q, subsection_key="interior_walls")
        # count remains 1
        self.assertEqual(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").count(), 1)

    def test_create_uses_select_for_update(self):
        # Ensure the service attempts to lock existing sibling rows
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        from quotation import models as qm

        with patch.object(qm.QuotationSection.objects, "select_for_update", wraps=qm.QuotationSection.objects.select_for_update) as mocked:
            create_repeatable_section(quotation=self.q, subsection_key="interior_walls")
            self.assertTrue(mocked.called)


class RepeatableSectionEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="webuser", email="webuser@example.test", password="pass")
        self.other = User.objects.create_user(username="other", email="other@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="C", customer_email="", customer_phone="")
        self.client.login(username="webuser", password="pass")

    def test_post_add_creates_and_redirects(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        url = reverse("quotation:section_add", kwargs={"pk": self.q.pk, "subsection_key": "interior_walls"})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        # New section exists and belongs to the quotation
        secs = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").order_by("selection_order"))
        self.assertEqual(len(secs), 2)
        # Location header should be a relative builder URL with fragment for the new section
        new_pk = secs[-1].pk
        expected_prefix = reverse("quotation:quotation_builder", kwargs={"pk": self.q.pk})
        self.assertTrue(resp["Location"].startswith(expected_prefix))
        self.assertTrue(resp["Location"].endswith(f"#section-{new_pk}"))

    def test_get_add_rejected(self):
        url = reverse("quotation:section_add", kwargs={"pk": self.q.pk, "subsection_key": "interior_walls"})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)

    def test_other_user_cannot_add(self):
        # Owner has a selection
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        self.client.logout()
        self.client.login(username="other", password="pass")
        url = reverse("quotation:section_add", kwargs={"pk": self.q.pk, "subsection_key": "interior_walls"})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)

    def test_unexpected_exceptions_not_swallowed(self):
        # If the underlying service raises an unexpected error it should propagate
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        url = reverse("quotation:section_add", kwargs={"pk": self.q.pk, "subsection_key": "interior_walls"})
        with patch("quotation.views.create_repeatable_section", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(url)


class RepeatableSectionDeletionServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="deluser", email="deluser@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="D", customer_email="", customer_phone="")

    def test_delete_middle_removes_only_that_and_renumbers(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=2)
        s3 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I3", selection_order=3)
        li1 = QuotationLineItem.objects.create(quotation=self.q, section=s1, item_type=QuotationLineItem.ItemType.NOTE, description="n1")
        li2 = QuotationLineItem.objects.create(quotation=self.q, section=s2, item_type=QuotationLineItem.ItemType.NOTE, description="n2")
        li3 = QuotationLineItem.objects.create(quotation=self.q, section=s3, item_type=QuotationLineItem.ItemType.NOTE, description="n3")

        delete_repeatable_section(quotation=self.q, section_pk=s2.pk)

        # s2 removed
        with self.assertRaises(QuotationSection.DoesNotExist):
            QuotationSection.objects.get(pk=s2.pk)

        # s1 and s3 still exist with same PKs
        s1_db = QuotationSection.objects.get(pk=s1.pk)
        s3_db = QuotationSection.objects.get(pk=s3.pk)
        self.assertEqual(s1_db.pk, s1.pk)
        self.assertEqual(s3_db.pk, s3.pk)

        # lineitems still reference same section PKs
        self.assertEqual(QuotationLineItem.objects.get(pk=li1.pk).section_id, s1.pk)
        self.assertEqual(QuotationLineItem.objects.get(pk=li3.pk).section_id, s3.pk)

        # Renumbered contiguous
        orders = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").order_by("selection_order").values_list("selection_order", flat=True))
        self.assertEqual(orders, [1, 2])

    def test_delete_last_removes_category(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1")
        delete_repeatable_section(quotation=self.q, section_pk=s1.pk)
        self.assertEqual(QuotationSection.objects.filter(quotation=self.q, subsection_key="ceilings").count(), 0)

    def test_unusual_prior_orders_handled(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=100)
        s3 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I3", selection_order=101)
        delete_repeatable_section(quotation=self.q, section_pk=s2.pk)
        orders = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").order_by("selection_order").values_list("selection_order", flat=True))
        self.assertEqual(orders, [1, 2])

    def test_delete_atomic_rollback_on_failure(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=2)
        s3 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I3", selection_order=3)

        from django.db.models.query import QuerySet

        real_update = QuerySet.update
        call_count = {"n": 0}

        def flaky_update(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise Exception("simulated failure")
            return real_update(self, *args, **kwargs)

        with patch.object(QuerySet, "update", new=flaky_update):
            with self.assertRaises(Exception):
                delete_repeatable_section(quotation=self.q, section_pk=s2.pk)

        # Verify original ordering preserved after rollback
        orders = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").order_by("selection_order").values_list("selection_order", flat=True))
        self.assertEqual(orders, [1, 2, 3])


class RepeatableSectionDeletionEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="delweb", email="delweb@example.test", password="pass")
        self.other = User.objects.create_user(username="otherdel", email="otherdel@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="DW", customer_email="", customer_phone="")
        self.client.login(username="delweb", password="pass")

    def test_post_delete_removes_and_redirects(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=2)
        s3 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I3", selection_order=3)
        url = reverse("quotation:section_delete", kwargs={"pk": self.q.pk, "section_pk": s2.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(QuotationSection.objects.filter(pk=s2.pk).exists())

    def test_get_delete_rejected(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        url = reverse("quotation:section_delete", kwargs={"pk": self.q.pk, "section_pk": s1.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)

    def test_other_user_cannot_delete(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        self.client.logout()
        self.client.login(username="otherdel", password="pass")
        url = reverse("quotation:section_delete", kwargs={"pk": self.q.pk, "section_pk": s1.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)

    def test_section_from_other_quotation_rejected(self):
        other_q = Quotation.objects.create(created_by=self.other, customer_name="X", customer_email="", customer_phone="")
        s_other = QuotationSection.objects.create(quotation=other_q, subsection_key="interior_walls", display_name="OX")
        url = reverse("quotation:section_delete", kwargs={"pk": self.q.pk, "section_pk": s_other.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)

    def test_unexpected_exceptions_not_swallowed_on_delete(self):
        # If the underlying service raises an unexpected error it should propagate
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        url = reverse("quotation:section_delete", kwargs={"pk": self.q.pk, "section_pk": s1.pk})
        with patch("quotation.views.delete_repeatable_section", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(url)


class SubstrateSelectionPreservationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="preserve", email="preserve@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="P", customer_email="", customer_phone="")
        self.client.login(username="preserve", password="pass")

    def test_resubmitting_preserves_duplicates_and_lineitems(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=2)
        li1 = QuotationLineItem.objects.create(quotation=self.q, section=s1, item_type=QuotationLineItem.ItemType.NOTE, description="n1")
        li2 = QuotationLineItem.objects.create(quotation=self.q, section=s2, item_type=QuotationLineItem.ItemType.NOTE, description="n2")

        url = reverse("quotation:quotation_sections", kwargs={"pk": self.q.pk})
        resp = self.client.post(url, data={"subsections": ["interior_walls"]})
        self.assertEqual(resp.status_code, 302)
        # duplicates preserved
        secs = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").order_by("pk"))
        self.assertEqual(len(secs), 2)
        self.assertEqual(secs[0].pk, s1.pk)
        self.assertEqual(secs[1].pk, s2.pk)
        # lineitems preserved
        self.assertEqual(QuotationLineItem.objects.get(pk=li1.pk).section_id, s1.pk)
        self.assertEqual(QuotationLineItem.objects.get(pk=li2.pk).section_id, s2.pk)

    def test_selecting_new_category_creates_one_selection_order_1(self):
        url = reverse("quotation:quotation_sections", kwargs={"pk": self.q.pk})
        resp = self.client.post(url, data={"subsections": ["ceilings"]})
        self.assertEqual(resp.status_code, 302)
        secs = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="ceilings").order_by("selection_order"))
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0].selection_order, 1)

    def test_resubmitting_does_not_create_extra_sections(self):
        url = reverse("quotation:quotation_sections", kwargs={"pk": self.q.pk})
        # first select
        self.client.post(url, data={"subsections": ["ceilings"]})
        # re-submit same selection
        resp = self.client.post(url, data={"subsections": ["ceilings"]})
        self.assertEqual(resp.status_code, 302)
        secs = list(QuotationSection.objects.filter(quotation=self.q, subsection_key="ceilings").order_by("selection_order"))
        self.assertEqual(len(secs), 1)

    def test_unselecting_removes_all_for_category(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", selection_order=2)
        url = reverse("quotation:quotation_sections", kwargs={"pk": self.q.pk})
        # submit empty selection
        resp = self.client.post(url, data={})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(QuotationSection.objects.filter(quotation=self.q, subsection_key="interior_walls").exists())

    def test_other_selected_categories_untouched(self):
        a1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1")
        b1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1")
        url = reverse("quotation:quotation_sections", kwargs={"pk": self.q.pk})
        resp = self.client.post(url, data={"subsections": ["interior_walls"]})
        self.assertEqual(resp.status_code, 302)
        # ceilings removed, interior preserved
        self.assertTrue(QuotationSection.objects.filter(pk=a1.pk).exists())
        self.assertFalse(QuotationSection.objects.filter(pk=b1.pk).exists())
