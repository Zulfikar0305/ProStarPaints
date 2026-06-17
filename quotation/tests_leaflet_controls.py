from html.parser import HTMLParser

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Quotation, QuotationSection
from .services import ALL_SUBSECTIONS


class LeafletControlsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ctl", email="ctl@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="Ctl", customer_email="", customer_phone="")
        self.client.login(username="ctl", password="pass")

    # -----------------
    # Rendering: Add control
    # -----------------
    def test_active_leaflet_shows_one_add_form_with_csrf_and_post(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        url = reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls'
        resp = self.client.get(url)
        html = resp.content.decode('utf-8')

        action = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'interior_walls'})
        block = self._extract_form_block(html, action)
        self.assertIsNotNone(block, 'Add form not present')
        self.assertIn('method="post"', block)
        self.assertIn('name="csrfmiddlewaretoken"', block)
        self.assertIn('+ Add another', block)
        # label should include canonical display name
        self.assertIn(ALL_SUBSECTIONS['interior_walls'].display_name, block)

    def test_add_form_absent_for_unselected_and_unknown_keys(self):
        # Unselected category: ceilings not selected
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        html = resp.content.decode('utf-8')
        ceilings_action = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'ceilings'})
        self.assertNotIn(ceilings_action, html)

        # Unknown/historical key: present as a selection but not canonical
        QuotationSection.objects.create(quotation=self.q, subsection_key='legacy_xyz', display_name='Legacy 1', sort_order=9, selection_order=1)
        resp2 = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        html2 = resp2.content.decode('utf-8')
        legacy_action = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'legacy_xyz'})
        # Add action should not be present for unknown key
        self.assertNotIn(legacy_action, html2)

    # -----------------
    # Rendering: Remove controls
    # -----------------
    def test_remove_forms_count_and_attributes(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", sort_order=0, selection_order=2)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')

        # Two remove forms should be present
        self.assertGreaterEqual(html.count('data-confirm-remove-selection'), 2)

        # Each remove form targets exact section PK and contains csrf and method
        for s in (s1, s2):
            action = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s.pk})
            block = self._extract_form_block(html, action)
            self.assertIsNotNone(block, f'Remove form for section {s.pk} not found')
            self.assertIn('method="post"', block)
            self.assertIn('name="csrfmiddlewaretoken"', block)
            # Accessible label contains selection label
            self.assertIn(f'aria-label="Remove', block)

    def test_final_and_nonfinal_remove_forms_expose_warning_state(self):
        # One selection (final)
        q2 = Quotation.objects.create(created_by=self.user, customer_name='Q2', customer_email='', customer_phone='')
        s_only = QuotationSection.objects.create(quotation=q2, subsection_key='interior_walls', display_name='Only', sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q2.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')
        block = self._extract_form_block(html, reverse('quotation:section_delete', kwargs={'pk': q2.pk, 'section_pk': s_only.pk}))
        self.assertIsNotNone(block)
        self.assertIn('data-is-final="1"', block)

        # Two selections -> non-final form should have data-is-final=0
        q3 = Quotation.objects.create(created_by=self.user, customer_name='Q3', customer_email='', customer_phone='')
        a = QuotationSection.objects.create(quotation=q3, subsection_key='interior_walls', display_name='A1', sort_order=0, selection_order=1)
        b = QuotationSection.objects.create(quotation=q3, subsection_key='interior_walls', display_name='A2', sort_order=0, selection_order=2)
        resp2 = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q3.pk}) + '?leaflet=interior_walls')
        html2 = resp2.content.decode('utf-8')
        b_block = self._extract_form_block(html2, reverse('quotation:section_delete', kwargs={'pk': q3.pk, 'section_pk': b.pk}))
        self.assertIsNotNone(b_block)
        self.assertIn('data-is-final="0"', b_block)

    # -----------------
    # Structure: no nested forms
    # -----------------
    def test_no_nested_forms_in_builder_html(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", sort_order=0, selection_order=2)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')
        self.assertFalse(self._has_nested_forms(html), 'Nested <form> tags detected')

    # -----------------
    # Integration: add and remove endpoints via visible actions
    # -----------------
    def test_posting_add_form_creates_new_selection_and_redirects_with_anchor(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)
        add_url = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'interior_walls'})
        resp = self.client.post(add_url)
        self.assertEqual(resp.status_code, 302)
        loc = resp['Location']
        self.assertIn('?leaflet=interior_walls', loc)
        self.assertIn('#section-', loc)
        self.assertTrue(QuotationSection.objects.filter(quotation=self.q, subsection_key='interior_walls').count() >= 2)

    def test_posting_delete_removes_only_target_and_renumbers(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I2', selection_order=2)
        delete_url = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s2.pk})
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(QuotationSection.objects.filter(pk=s2.pk).exists())
        # Remaining selection exists and retains its PK
        self.assertTrue(QuotationSection.objects.filter(pk=s1.pk).exists())

    # -----------------
    # Category-generic / final-deletion behaviors
    # -----------------
    def test_ceilings_add_label_and_integration(self):
        # Ensure the Add control is dynamic for a non-Interior category (ceilings)
        QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)
        QuotationSection.objects.create(quotation=self.q, subsection_key='ceilings', display_name='C1', selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')

        add_action = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'ceilings'})
        block = self._extract_form_block(html, add_action)
        self.assertIsNotNone(block, 'Ceilings add form not present')
        self.assertIn('+ Add another', block)
        self.assertIn(ALL_SUBSECTIONS['ceilings'].display_name, block)

        # Posting the visible add endpoint should create another ceilings selection
        resp2 = self.client.post(add_action)
        self.assertEqual(resp2.status_code, 302)
        loc = resp2['Location']
        self.assertIn('?leaflet=ceilings', loc)
        self.assertIn('#section-', loc)

        ceilings = list(QuotationSection.objects.filter(quotation=self.q, subsection_key='ceilings').order_by('selection_order'))
        self.assertGreaterEqual(len(ceilings), 2)
        self.assertEqual(ceilings[-1].selection_order, 2)

        # Interior walls count must remain unchanged by creating a ceilings section
        self.assertEqual(QuotationSection.objects.filter(quotation=self.q, subsection_key='interior_walls').count(), 1)

    def test_remove_controls_render_only_for_active_leaflet(self):
        # Remove controls should only appear for active leaflet selections
        s_walls = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)
        s_ceil = QuotationSection.objects.create(quotation=self.q, subsection_key='ceilings', display_name='C1', selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')

        # Ceiling delete action present
        ceil_action = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s_ceil.pk})
        self.assertIsNotNone(self._extract_form_block(html, ceil_action))

        # Walls delete action must not be present because walls are not the active leaflet
        walls_action = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s_walls.pk})
        self.assertIsNone(self._extract_form_block(html, walls_action))

    def test_deleting_only_selection_removes_category_and_empty_state(self):
        # Deleting the sole selection in a category removes that category from the builder
        q2 = Quotation.objects.create(created_by=self.user, customer_name='Q2', customer_email='', customer_phone='')
        s_only = QuotationSection.objects.create(quotation=q2, subsection_key='ceilings', display_name='Only', selection_order=1)
        delete_url = reverse('quotation:section_delete', kwargs={'pk': q2.pk, 'section_pk': s_only.pk})
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 302)

        # After deletion, the builder lists no leaflet groups for that quotation
        resp2 = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q2.pk}))
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.context.get('leaflet_groups', []), [])
        self.assertIsNone(resp2.context.get('default_leaflet_key'))
        self.assertIsNone(resp2.context.get('active_leaflet_key'))

    # -----------------
    # Additional Pack 5B5 focused tests
    # -----------------
    def test_existing_section_edit_form_remains(self):
        # Ensure the per-section edit/save form is still present alongside Add/Remove controls
        s = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')

        # The dedicated interior walls save action must be present as its own form
        save_action = reverse('quotation:interior_walls_save', kwargs={'pk': self.q.pk, 'section_pk': s.pk})
        save_block = self._extract_form_block(html, save_action)
        self.assertIsNotNone(save_block, 'Interior walls save form missing')
        self.assertIn('method="post"', save_block)
        self.assertIn('name="csrfmiddlewaretoken"', save_block)
        self.assertIn('Save Interior Walls', save_block)

        # Add and Remove forms must also exist and must not be inside the edit form
        add_action = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'interior_walls'})
        remove_action = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s.pk})
        add_block = self._extract_form_block(html, add_action)
        remove_block = self._extract_form_block(html, remove_action)
        self.assertIsNotNone(add_block, 'Add form missing')
        self.assertIsNotNone(remove_block, 'Remove form missing')
        self.assertNotIn(add_action, save_block)
        self.assertNotIn('data-confirm-remove-selection', save_block)

    def test_summary_renders_once_and_no_forms_inside(self):
        # Multiple sections -> summary should render exactly once and not contain Add/Remove forms
        QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)
        QuotationSection.objects.create(quotation=self.q, subsection_key='ceilings', display_name='C1', selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        html = resp.content.decode('utf-8')

        # Summary partial marker should appear exactly once
        self.assertEqual(html.count('psp-summary-panel'), 1)

        # Ensure Add/Remove controls are present somewhere in the page
        self.assertIn('data-confirm-remove-selection', html)
        add_action = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'interior_walls'})
        self.assertIn(add_action, html)

        # The summary panel must come after the last Add/Remove control (i.e., forms are not inside it)
        idx_summary = html.find('psp-summary-panel')
        idx_last_remove = html.rfind('data-confirm-remove-selection')
        idx_last_add = html.rfind(add_action)
        self.assertGreater(idx_summary, idx_last_remove)
        self.assertGreater(idx_summary, idx_last_add)

    def test_deleting_final_selection_falls_back_to_other_leaflet(self):
        # Setup: one walls and one ceilings selection
        s_w = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)
        s_c = QuotationSection.objects.create(quotation=self.q, subsection_key='ceilings', display_name='C1', selection_order=1)

        # Active leaflet = ceilings; delete the sole ceilings section and follow redirect
        delete_url = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s_c.pk})
        resp = self.client.post(delete_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Ceilings gone
        self.assertFalse(QuotationSection.objects.filter(quotation=self.q, subsection_key='ceilings').exists())

        # Builder context should have leaflet_groups only for remaining category and active_leaflet_key set
        lgroups = resp.context.get('leaflet_groups') or []
        keys = [g['key'] for g in lgroups]
        self.assertNotIn('ceilings', keys)
        self.assertIn('interior_walls', keys)
        self.assertEqual(resp.context.get('active_leaflet_key'), 'interior_walls')

        # No placeholder section should have been created for the deleted category
        self.assertEqual(QuotationSection.objects.filter(quotation=self.q, subsection_key='ceilings').count(), 0)

    def test_unauthorized_add_and_delete_are_rejected(self):
        # Ensure another authenticated user cannot add or delete on quotations they don't own
        other = get_user_model().objects.create_user(username='otherx', email='otherx@example.test', password='pass')
        # Owner has one section
        s = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', selection_order=1)

        # Switch to other user
        self.client.logout()
        self.client.login(username='otherx', password='pass')

        add_url = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'interior_walls'})
        resp_add = self.client.post(add_url)
        self.assertEqual(resp_add.status_code, 404)
        # No new sections created
        self.assertEqual(QuotationSection.objects.filter(quotation=self.q, subsection_key='interior_walls').count(), 1)

        delete_url = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s.pk})
        resp_del = self.client.post(delete_url)
        self.assertEqual(resp_del.status_code, 404)
        # Section still exists
        self.assertTrue(QuotationSection.objects.filter(pk=s.pk).exists())

    # -----------------
    # Helpers
    # -----------------
    def _extract_form_block(self, html, action_value):
        """Return the <form>...</form> block that contains the given action value, or None."""
        idx = html.find(f'action="{action_value}"')
        if idx == -1:
            return None
        start = html.rfind('<form', 0, idx)
        if start == -1:
            return None
        end = html.find('</form>', idx)
        if end == -1:
            end = len(html)
        return html[start:end+7]

    def _has_nested_forms(self, html):
        """Return True if any nested <form> tags exist in the HTML."""
        depth = 0
        pos = 0
        while True:
            next_open = html.find('<form', pos)
            next_close = html.find('</form>', pos)
            if next_open == -1 and next_close == -1:
                break
            if next_open != -1 and (next_open < next_close or next_close == -1):
                depth += 1
                if depth > 1:
                    return True
                pos = next_open + 5
            else:
                depth = max(0, depth - 1)
                pos = next_close + 7
        return False
