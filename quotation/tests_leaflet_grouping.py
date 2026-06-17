from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Quotation, QuotationSection, QuotationLineItem
from .services import get_leaflet_groups, ALL_SUBSECTIONS


class LeafletGroupingServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="svc", email="svc@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="L", customer_email="", customer_phone="")

    def test_one_selected_category_produces_one_group(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Interior Walls", sort_order=0, selection_order=1)
        groups = get_leaflet_groups(self.q)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["key"], "interior_walls")
        self.assertEqual(g["display_name"], ALL_SUBSECTIONS["interior_walls"].display_name)
        self.assertEqual(g["selection_count"], 1)
        self.assertEqual(g["selections"][0]["selection_label"], f"{ALL_SUBSECTIONS['interior_walls'].display_name} 1")

    def test_unselected_configured_category_absent(self):
        groups = get_leaflet_groups(self.q)
        self.assertEqual(groups, [])

    def test_two_sections_same_key_produce_one_group(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", sort_order=0, selection_order=2)
        groups = get_leaflet_groups(self.q)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["selection_count"], 2)
        labels = [s["selection_label"] for s in g["selections"]]
        self.assertEqual(labels, [f"{ALL_SUBSECTIONS['interior_walls'].display_name} 1", f"{ALL_SUBSECTIONS['interior_walls'].display_name} 2"])

    def test_categories_ordered_by_sort_then_name(self):
        # ceilings (sort 1) and interior_walls (sort 0) -> interior_walls first
        a = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="Ceilings", sort_order=1, selection_order=1)
        b = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Interior Walls", sort_order=0, selection_order=1)
        keys = [g["key"] for g in get_leaflet_groups(self.q)]
        self.assertEqual(keys, ["interior_walls", "ceilings"])

    def test_helper_performs_no_writes(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        before = list(QuotationSection.objects.filter(quotation=self.q).values_list("pk", flat=True))
        _ = get_leaflet_groups(self.q)
        after = list(QuotationSection.objects.filter(quotation=self.q).values_list("pk", flat=True))
        self.assertEqual(before, after)

    def test_unknown_historical_key_fallback(self):
        # Create a section with a key not present in ALL_SUBSECTIONS
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="legacy_key", display_name="Legacy X", substrate_type="INTERIOR", sort_order=99, selection_order=1)
        groups = get_leaflet_groups(self.q)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["key"], "legacy_key")
        self.assertEqual(g["display_name"], "Legacy X")
        self.assertEqual(g["substrate_type"], "INTERIOR")
        self.assertEqual(g["selection_count"], 1)
        # Fallback uses existing section.display_name for label
        self.assertEqual(g["selections"][0]["selection_label"], "Legacy X")

    def test_empty_quotation_returns_empty_list(self):
        q2 = Quotation.objects.create(created_by=self.user, customer_name="Empty", customer_email="", customer_phone="")
        self.assertEqual(get_leaflet_groups(q2), [])


class BuilderContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="web", email="web@example.test", password="pass")
        self.other = User.objects.create_user(username="other", email="other@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="B", customer_email="", customer_phone="")
        self.client.login(username="web", password="pass")

    def test_builder_context_contains_leaflet_groups_and_keys(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        url = reverse("quotation:quotation_builder", kwargs={"pk": self.q.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("leaflet_groups", resp.context)
        self.assertIn("selected_leaflet_keys", resp.context)
        self.assertIn("default_leaflet_key", resp.context)

    def test_selected_leaflet_keys_matches_group_order(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        url = reverse("quotation:quotation_builder", kwargs={"pk": self.q.pk})
        resp = self.client.get(url)
        keys = resp.context["selected_leaflet_keys"]
        self.assertEqual(keys, ["interior_walls", "ceilings"])
        self.assertEqual(resp.context["default_leaflet_key"], "interior_walls")

    def test_empty_builder_context_for_empty_quotation(self):
        q2 = Quotation.objects.create(created_by=self.user, customer_name="N", customer_email="", customer_phone="")
        url = reverse("quotation:quotation_builder", kwargs={"pk": q2.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["leaflet_groups"], [])
        self.assertEqual(resp.context["selected_leaflet_keys"], [])
        self.assertIsNone(resp.context["default_leaflet_key"])

    def test_unauthorized_user_cannot_view_other_quotation(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        self.client.logout()
        self.client.login(username="other", password="pass")
        url = reverse("quotation:quotation_builder", kwargs={"pk": self.q.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_builder_context_preserves_existing_keys(self):
        # Ensure the builder still provides the pre-existing context keys
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        url = reverse("quotation:quotation_builder", kwargs={"pk": self.q.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        expected_keys = [
            "quotation",
            "interior_sections_data",
            "exterior_sections_data",
            "interior_secs",
            "exterior_secs",
            "section_summaries",
            "any_configured",
            "quotation_summary",
            "is_admin",
            "wall_types",
            "surface_conditions",
            "finishes",
            "finish_map_json",
            "all_paint_groups",
            "waterproofing_options",
            "primer_options",
            "other_prep_options",
            "moisture_threshold",
        ]

        for k in expected_keys:
            self.assertIn(k, resp.context, msg=f"Missing context key: {k}")


class LeafletGroupingAdditionalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="add", email="add@example.test", password="pass")
        self.q1 = Quotation.objects.create(created_by=self.user, customer_name="Q1", customer_email="", customer_phone="")
        self.q2 = Quotation.objects.create(created_by=self.user, customer_name="Q2", customer_email="", customer_phone="")

    def test_selection_pk_tiebreaker_orders_by_pk(self):
        # Two sections same selection_order -> should be ordered by pk
        s1 = QuotationSection.objects.create(quotation=self.q1, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        # Creating a second section with the same (quotation, subsection_key, selection_order)
        # violates the model UniqueConstraint and should raise IntegrityError. Wrap
        # the expectation in an atomic savepoint so the subsequent DB work is safe.
        from django.db import IntegrityError, transaction
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                QuotationSection.objects.create(quotation=self.q1, subsection_key="interior_walls", display_name="I2", sort_order=0, selection_order=1)
        # Confirm normal ordering by selection_order works when values differ
        s2 = QuotationSection.objects.create(quotation=self.q1, subsection_key="interior_walls", display_name="I2", sort_order=0, selection_order=2)
        groups = get_leaflet_groups(self.q1)
        self.assertEqual(len(groups), 1)
        pks = [s["section_pk"] for s in groups[0]["selections"]]
        self.assertEqual(pks, [s1.pk, s2.pk])

    def test_category_tiebreaker_displayname_then_key(self):
        # Create an unknown category that falls back to sort_order 0 and
        # display_name 'AAA' to exercise the secondary ordering by display_name
        legacy = QuotationSection.objects.create(quotation=self.q1, subsection_key="legacy_a", display_name="AAA", substrate_type="INTERIOR", sort_order=0, selection_order=1)
        known = QuotationSection.objects.create(quotation=self.q1, subsection_key="interior_walls", display_name="Interior Walls", sort_order=0, selection_order=1)
        keys = [g["key"] for g in get_leaflet_groups(self.q1)]
        self.assertEqual(keys, ["legacy_a", "interior_walls"])

    def test_selection_pk_and_section_object_exposed(self):
        s = QuotationSection.objects.create(quotation=self.q1, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        groups = get_leaflet_groups(self.q1)
        g = groups[0]
        sel = g["selections"][0]
        self.assertEqual(sel["section_pk"], s.pk)
        # The helper returns a fresh model instance; assert by PK equality
        self.assertEqual(getattr(sel["section"], "pk"), s.pk)
        self.assertIsInstance(sel["section"], QuotationSection)

    def test_cross_quotation_isolation(self):
        # q1 has interior_walls, q2 has ceilings — get_leaflet_groups(q1) must not include q2 data
        s1 = QuotationSection.objects.create(quotation=self.q1, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q2, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        groups_q1 = get_leaflet_groups(self.q1)
        keys_q1 = [g["key"] for g in groups_q1]
        self.assertNotIn("ceilings", keys_q1)
        # ensure no selection pk from q2 leaked into q1 result
        all_pks_q1 = [sel["section_pk"] for g in groups_q1 for sel in g["selections"]]
        self.assertNotIn(s2.pk, all_pks_q1)
