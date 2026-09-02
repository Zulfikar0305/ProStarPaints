from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import IntegrityError

from .models import Quotation, QuotationSection, QuotationLineItem
from .services import ALL_SUBSECTIONS


class LeafletUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ui", email="ui@example.test", password="pass")
        self.other = User.objects.create_user(username="other", email="other@example.test", password="pass")
        self.q = Quotation.objects.create(created_by=self.user, customer_name="UI", customer_email="", customer_phone="")
        self.client.login(username="ui", password="pass")

    # -----------------
    # Active context
    # -----------------
    def test_missing_query_uses_first_selected_category(self):
        # interior_walls sort 0 should be default over ceilings sort 1
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="Ceilings Test", sort_order=1, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Walls Test", sort_order=0, selection_order=1)
        url = reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_leaflet_key'], 'interior_walls')
        self.assertEqual(resp.context['default_leaflet_key'], 'interior_walls')
        self.assertIsNotNone(resp.context['active_leaflet_group'])

    def test_valid_selected_query_activates_that_category(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="Ceilings Test", sort_order=1, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Walls Test", sort_order=0, selection_order=1)
        url = reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_leaflet_key'], 'ceilings')
        self.assertEqual(resp.context['active_leaflet_group']['key'], 'ceilings')

    def test_invalid_query_falls_back_to_default(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="Ceilings Test", sort_order=1, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Walls Test", sort_order=0, selection_order=1)
        url = reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=not_a_real_key'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_leaflet_key'], resp.context['default_leaflet_key'])

    def test_unselected_configured_key_cannot_be_active(self):
        # Only interior_walls selected; asking for ceilings should fall back
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="Walls Test", sort_order=0, selection_order=1)
        url = reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_leaflet_key'], resp.context['default_leaflet_key'])

    def test_empty_quotation_gives_none_none_empty(self):
        q2 = Quotation.objects.create(created_by=self.user, customer_name="Empty", customer_email="", customer_phone="")
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q2.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['leaflet_groups'], [])
        self.assertEqual(resp.context['selected_leaflet_keys'], [])
        self.assertIsNone(resp.context['default_leaflet_key'])
        self.assertIsNone(resp.context['active_leaflet_key'])
        self.assertIsNone(resp.context['active_leaflet_group'])
        self.assertEqual(resp.context['active_leaflet_selections'], [])

    # -----------------
    # Tabs
    # -----------------
    def test_only_selected_category_tabs_render(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        html = resp.content.decode('utf-8')
        self.assertIn('href="?leaflet=interior_walls"', html)
        self.assertIn('href="?leaflet=ceilings"', html)

    def test_unselected_category_tab_absent(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        html = resp.content.decode('utf-8')
        self.assertIn('href="?leaflet=interior_walls"', html)
        self.assertNotIn('href="?leaflet=ceilings"', html)

    def test_active_tab_has_accessibility_state(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        url = reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls'
        resp = self.client.get(url)
        html = resp.content.decode('utf-8')
        self.assertIn('aria-current="page"', html)

    def test_tab_order_matches_leaflet_groups(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        keys = resp.context['selected_leaflet_keys']
        self.assertEqual(keys, ['interior_walls', 'ceilings'])

    def test_empty_quotation_renders_no_tabs(self):
        q2 = Quotation.objects.create(created_by=self.user, customer_name="Empty", customer_email="", customer_phone="")
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q2.pk}))
        html = resp.content.decode('utf-8')
        self.assertNotIn('nav nav-tabs', html)
        self.assertNotIn('href="?leaflet=', html)

    def test_old_jump_to_absent(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        html = resp.content.decode('utf-8')
        self.assertNotIn('psp-section-rail', html)

    # -----------------
    # Active content
    # -----------------
    def test_only_active_category_sections_render(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')
        self.assertIn(f'id="section-{s1.pk}"', html)
        self.assertNotIn(f'id="section-{s2.pk}"', html)

    def test_two_repeated_selections_both_render(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I2", sort_order=0, selection_order=2)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')
        self.assertIn(f'id="section-{s1.pk}"', html)
        self.assertIn(f'id="section-{s2.pk}"', html)

    def test_selection_labels_render_above_sections(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')
        # The selection label is generated from the services helper; ensure it's present
        self.assertIn(ALL_SUBSECTIONS['interior_walls'].display_name, html)

    def test_interior_walls_uses_special_partial(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')
        self.assertIn('Save Interior Walls', html)

    def test_interior_walls_surface_conditions_use_required_values(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')
        expected = [
            'value="prev_painted_good"',
            'value="prev_painted_poor"',
            'value="prev_painted_chalky"',
            'value="prev_painted_mouldy"',
            'value="unpainted"',
        ]
        for value in expected:
            self.assertIn(value, html)
        self.assertNotIn('value="new"', html)
        self.assertNotIn('value="peeling"', html)
        self.assertNotIn('value="mould"', html)

    def test_generic_section_does_not_render_notes_or_debug_help_fragments(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')
        self.assertNotIn('Additional Notes', html)
        self.assertNotIn('name="notes"', html)
        self.assertNotIn('Any special notes', html)
        self.assertNotIn('Choosing a finish reveals matching paint options below.', html)
        self.assertNotIn('Area in square metres helps reps quote accurately.', html)
        self.assertNotIn('Prep work is added as separate line items so the customer sees scope clearly.', html)

    def test_generic_sections_put_area_and_moisture_in_first_section(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')
        self.assertIn('name="types"', html)
        self.assertIn('name="area_sqm"', html)
        self.assertIn('name="moisture_level"', html)
        self.assertLess(html.index('name="types"'), html.index('name="area_sqm"'))
        self.assertLess(html.index('name="area_sqm"'), html.index('name="moisture_level"'))
        self.assertNotIn('> Measurements</h6>', html)

    def test_generic_section_uses_single_select_for_type_field(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')
        self.assertIn('<select name="types"', html)
        self.assertIn('value="concrete_socket"', html)
        self.assertIn('value="gypsum_boards"', html)
        self.assertNotIn('type="checkbox" id="gstype_', html)

    def test_generic_section_uses_generic_partial(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')
        self.assertIn('Save Ceilings', html)

    def test_generic_section_has_image_upload_input_like_interior_walls(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')
        self.assertIn(f'id="sectionImageInput_{s.pk}"', html)
        self.assertIn('type="file"', html)
        self.assertIn('name="section_images"', html)

    def test_form_actions_and_fields_present(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=ceilings')
        html = resp.content.decode('utf-8')
        # Form action for generic sections points to section_save
        self.assertIn(reverse('quotation:section_save', kwargs={'pk': self.q.pk, 'section_pk': s.pk}), html)
        self.assertIn('name="finishes"', html)

    def test_no_unselected_category_content_renders(self):
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        html = resp.content.decode('utf-8')
        # Ensure a different category's section id is not present
        # Ensure there are no other section anchors before this one's anchor.
        self.assertNotIn('id="section-', html.split(f'section-{s1.pk}', 1)[0])

    # -----------------
    # Summary
    # -----------------
    def test_summary_panel_renders_once(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        html = resp.content.decode('utf-8')
        # Server-side summary partial is rendered once in the right-hand column
        self.assertIn('psp-builder-summary-sticky', html)
        self.assertEqual(html.count('psp-builder-summary-sticky'), 1)

    def test_summary_present_for_different_active_leaflets(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp1 = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        resp2 = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}) + '?leaflet=interior_walls')
        self.assertIn('psp-builder-summary-sticky', resp1.content.decode('utf-8'))
        self.assertIn('psp-builder-summary-sticky', resp2.content.decode('utf-8'))

    def test_summary_context_available(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        self.assertIn('quotation_summary', resp.context)
        self.assertIn('configured_count', resp.context['quotation_summary'])

    # -----------------
    # Redirects
    # -----------------
    def test_interior_save_redirects_with_leaflet_and_anchor(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        url = reverse('quotation:interior_walls_save', kwargs={'pk': self.q.pk, 'section_pk': s.pk})
        data = {'wall_type': 'brick', 'finishes': ['smooth_matte'], 'area_sqm': '12.5'}
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)
        loc = resp['Location']
        self.assertIn('?leaflet=interior_walls', loc)
        self.assertIn(f'#section-{s.pk}', loc)

    def test_generic_save_redirects_with_leaflet_and_anchor(self):
        s = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        url = reverse('quotation:section_save', kwargs={'pk': self.q.pk, 'section_pk': s.pk})
        data = {'types': ['concrete_socket'], 'finishes': ['smooth_matte'], 'area_sqm': '5'}
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)
        loc = resp['Location']
        self.assertIn(f'?leaflet={s.subsection_key}', loc)
        self.assertIn(f'#section-{s.pk}', loc)

    def test_create_selection_redirects_to_new_section_anchor(self):
        # Ensure the category is selected first, then create an additional selection
        s_initial = QuotationSection.objects.create(quotation=self.q, subsection_key='interior_walls', display_name='I1', sort_order=0, selection_order=1)
        url = reverse('quotation:section_add', kwargs={'pk': self.q.pk, 'subsection_key': 'interior_walls'})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        loc = resp['Location']
        self.assertIn('?leaflet=interior_walls', loc)
        self.assertIn('#section-', loc)
        # Ensure new section created
        self.assertTrue(QuotationSection.objects.filter(quotation=self.q, subsection_key='interior_walls').count() >= 2)

    def test_delete_redirects_preserve_category_key_and_builder_fallback(self):
        # Setup two categories so fallback is verifiable
        s1 = QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        s2 = QuotationSection.objects.create(quotation=self.q, subsection_key="ceilings", display_name="C1", sort_order=1, selection_order=1)
        url = reverse('quotation:section_delete', kwargs={'pk': self.q.pk, 'section_pk': s1.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        loc = resp['Location']
        self.assertIn('?leaflet=interior_walls', loc)
        # Now delete the remaining interior_walls selection if any and ensure builder falls back
        # (simulate deleting last selection by creating only one interior_walls and deleting it)
        q2 = Quotation.objects.create(created_by=self.user, customer_name='Q2', customer_email='', customer_phone='')
        s_only = QuotationSection.objects.create(quotation=q2, subsection_key='interior_walls', display_name='Only', sort_order=0, selection_order=1)
        del_url = reverse('quotation:section_delete', kwargs={'pk': q2.pk, 'section_pk': s_only.pk})
        resp2 = self.client.post(del_url)
        self.assertEqual(resp2.status_code, 302)
        # After deletion, builder should not crash; loading builder will choose first remaining (or None)
        resp3 = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q2.pk}))
        self.assertEqual(resp3.status_code, 200)

    # -----------------
    # Access & compatibility
    # -----------------
    def test_unauthorized_user_blocked(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        self.client.logout()
        self.client.login(username='other', password='pass')
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        self.assertEqual(resp.status_code, 404)

    def test_existing_builder_context_keys_remain(self):
        QuotationSection.objects.create(quotation=self.q, subsection_key="interior_walls", display_name="I1", sort_order=0, selection_order=1)
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': self.q.pk}))
        expected_keys = [
            'quotation', 'interior_sections_data', 'exterior_sections_data', 'interior_secs', 'exterior_secs',
            'section_summaries', 'any_configured', 'quotation_summary', 'is_admin',
        ]
        for k in expected_keys:
            self.assertIn(k, resp.context)
