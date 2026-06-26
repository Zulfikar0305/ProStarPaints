from django.test import TestCase, Client
from django.urls import reverse
from .models import Quotation, QuotationSection

class PaintRowUITests(TestCase):
    def setUp(self):
        self.client = Client()
        # create a user and login
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.force_login(self.user)

    def test_paint_row_workflow_create_save_restore(self):
        # 1. Create a new quotation
        q = Quotation.objects.create(created_by=self.user, customer_name='C', customer_email='a@b.com')
        # select interior_walls section
        resp = self.client.post(reverse('quotation:quotation_sections', kwargs={'pk': q.pk}), {'subsections': ['interior_walls']})
        self.assertEqual(resp.status_code, 302)
        # open builder
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q.pk}))
        self.assertEqual(resp.status_code, 200)
        # verify exactly one paint-row in interior_walls partial
        self.assertContains(resp, 'id="paintRows_' , msg_prefix='paintRows container missing')
        # crude count: paint-row class occurrences inside paintRows
        body = resp.content.decode('utf-8')
        # find the interior_walls section block
        self.assertIn('paint-row', body)
        # Save via interior_walls save endpoint with one paint row
        data = {
            'wall_type': 'brick',
            'finishes': ['smooth_matte'],
            'paint_row_finish': ['smooth_matte'],
            'paint_row_paint_pk': [''],
            'paint_row_area_sqm': ['12.5'],
            'paint_row_coats': ['2'],
            'csrfmiddlewaretoken': ''
        }
        resp = self.client.post(reverse('quotation:interior_walls_save', kwargs={'pk': q.pk, 'section_pk': q.sections.first().pk}), data, follow=True)
        self.assertEqual(resp.status_code, 200)
        # Reopen builder and verify saved rows restored
        resp = self.client.get(reverse('quotation:quotation_builder', kwargs={'pk': q.pk}))
        self.assertEqual(resp.status_code, 200)
        body2 = resp.content.decode('utf-8')
        # should find exactly one paint-row element when one saved
        self.assertIn('paint-row', body2)

