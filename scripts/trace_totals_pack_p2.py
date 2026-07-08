#!/usr/bin/env python3
"""Trace quotation totals lifecycle for PACK P2.

This script reproduces the sequence: create quotation -> save via builder view ->
inspect line items -> call recalculate_quotation_totals() -> refresh and print.

It prints totals and per-line details at each stage to help root-cause the zero-total anomaly.

DO NOT MODIFY PROJECT CODE. This is read-only instrumentation.
"""

from decimal import Decimal
import os, sys, uuid, datetime, json, traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

# Allow test client host
from django.conf import settings as _dj_settings
try:
    _ah = list(_dj_settings.ALLOWED_HOSTS)
except Exception:
    _ah = []
if 'testserver' not in _ah:
    _ah.append('testserver')
    _dj_settings.ALLOWED_HOSTS = _ah

from django.test import Client
from django.contrib.auth import get_user_model
from paints.models import Paint
from quotation.models import Quotation, QuotationSection, QuotationLineItem
from quotation.pricing import apply_paint_pricing_to_line_item, recalculate_quotation_totals


def print_state(prefix, quotation):
    try:
        quotation.refresh_from_db()
    except Exception:
        pass
    print('\n===', prefix, 'Quotation PK', getattr(quotation, 'pk', None), '===')
    try:
        print('Quotation.subtotal_excl_vat=', getattr(quotation, 'subtotal_excl_vat', None),
              'vat_amount=', getattr(quotation, 'vat_amount', None),
              'total_incl_vat=', getattr(quotation, 'total_incl_vat', None))
    except Exception:
        print('Failed to read quotation totals')

    items = list(QuotationLineItem.objects.filter(quotation=quotation).order_by('pk'))
    print('Number of line items:', len(items))
    for li in items:
        meta = li.metadata or {}
        print(' - LI pk=', li.pk,
              'type=', li.item_type,
              'total_excl=', li.total_excl_vat,
              'total_incl=', li.total_incl_vat,
              "pricing_status=", meta.get('pricing_status'),
              "required_litres=", meta.get('required_litres'))

    # Also print computed sums from DB values
    try:
        s_excl = sum([Decimal(li.total_excl_vat or 0) for li in items])
        s_incl = sum([Decimal(li.total_incl_vat or 0) for li in items])
        print('Computed sums from line items -> subtotal_excl:', s_excl, 'total_incl:', s_incl, 'derived_vat:', (s_incl - s_excl))
    except Exception:
        print('Failed to compute sums')


if __name__ == '__main__':
    try:
        User = get_user_model()
        username = 'packb3_verifier'
        password = 'pass'
        # Ensure a test user exists
        try:
            user = User.objects.get(username=username)
            user.set_password(password)
            user.save()
        except User.DoesNotExist:
            base_email = 'packb3_verifier@example.test'
            if User.objects.filter(email=base_email).exists():
                base_email = f'packb3_verifier+{uuid.uuid4().hex[:8]}@example.test'
            user = User.objects.create_user(username=username, email=base_email, password=password)

        client = Client()
        logged_in = client.login(username=username, password=password)
        print('Client logged in:', logged_in)

        # Create a unique temporary quotation
        marker = 'trace_pack_p2'
        old_qs = Quotation.objects.filter(created_by=user, customer_name__icontains=marker)
        if old_qs.exists():
            print('Cleaning up previous test quotations:', old_qs.count())
            old_qs.delete()

        run_id = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        q = Quotation.objects.create(created_by=user, customer_name=f'Trace Pack P2 ({marker}-{run_id})', customer_email='', customer_phone='')
        sec = QuotationSection.objects.create(quotation=q, subsection_key='interior_walls', display_name='Trace Walls', substrate_type='INTERIOR')

        print_state('Initial (after create)', q)

        # Post a standard Interior Walls save (same data used in verify_pack_b3)
        post_data = {
            'wall_type': 'brick',
            'area_sqm': '20',
            'moisture_level': '0',
            'notes': 'Trace P2 run',
            'prep_work': ['filling', 'mould_treatment', 'cleaning', 'sanding', 'efflor_removal', 'remove_paint'],
            'prep_filling_pack_size': '2',
            'prep_filling_quantity': '3',
            'prep_mould_treatment_pack_size': '1',
            'prep_mould_treatment_quantity': '2',
            'prep_cleaning_pack_size': '1',
            'prep_cleaning_quantity': '1',
            'prep_sanding_grit': '80',
            'prep_sanding_rolls': '2',
        }

        print('\n--- POSTing to builder save view (creating line items) ---')
        url = f'/quotations/{q.pk}/sections/{sec.pk}/interior-walls/save/'
        resp = client.post(url, post_data, follow=True)
        print('POST status_code=', resp.status_code)

        print_state('After POST (client save)', q)

        print('\n--- Calling recalculate_quotation_totals(q) explicitly ---')
        recalculate_quotation_totals(q)
        print_state('After recalculate_quotation_totals(q)', q)

        # Now replicate direct creation path (no client) to compare
        print('\n--- Direct creation + apply_paint_pricing_to_line_item (no client) ---')
        q2 = Quotation.objects.create(created_by=user, customer_name=f'Trace Direct ({marker}-{run_id})', customer_email='', customer_phone='')
        sec2 = QuotationSection.objects.create(quotation=q2, subsection_key='interior_walls', display_name='Trace Direct Walls', substrate_type='INTERIOR')

        # Create a manual PREP_WORK item (matching existing product if possible)
        # Try to match a cleaning product
        cleaning_p = Paint.objects.filter(category=Paint.Category.CLEANING).first()
        li = QuotationLineItem.objects.create(
            quotation=q2,
            section=sec2,
            item_type=QuotationLineItem.ItemType.PREP_WORK,
            description='Manual cleaning',
            paint=cleaning_p,
            price_excl_vat=(cleaning_p.price_excl_vat if cleaning_p else Decimal('2.00')),
            price_incl_vat=(cleaning_p.price_incl_vat if cleaning_p else Decimal('2.30')),
            metadata={'key':'cleaning', 'paint_matched': bool(cleaning_p)},
        )
        print('Before apply_paint_pricing_to_line_item:')
        print_state('Direct before pricing', q2)

        apply_paint_pricing_to_line_item(li)
        print('After apply_paint_pricing_to_line_item:')
        print_state('Direct after pricing', q2)

        print('Calling recalculate_quotation_totals(q2)')
        recalculate_quotation_totals(q2)
        print_state('Direct after recalc', q2)

        print('\nTrace script completed successfully')

    except Exception as exc:
        print('Exception during trace run:')
        traceback.print_exc()
        sys.exit(2)
