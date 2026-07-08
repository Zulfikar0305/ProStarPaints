#!/usr/bin/env python3
"""Detailed trace of verify_pack_b3 flow with per-step totals logging.

This reproduces the verify script sequence but prints Quotation totals and
per-line details after each POST/delete so we can identify where totals end up zero.

DO NOT MODIFY PROJECT CODE.
"""

from decimal import Decimal
import os, sys, uuid, datetime, traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

# Allow testserver host
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
    print('Quotation.subtotal_excl_vat=', getattr(quotation, 'subtotal_excl_vat', None),
          'vat_amount=', getattr(quotation, 'vat_amount', None),
          'total_incl_vat=', getattr(quotation, 'total_incl_vat', None))
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
    try:
        s_excl = sum([Decimal(li.total_excl_vat or 0) for li in items])
        s_incl = sum([Decimal(li.total_incl_vat or 0) for li in items])
        print('Computed sums from line items -> subtotal_excl:', s_excl, 'total_incl:', s_incl, 'derived_vat:', (s_incl - s_excl))
    except Exception:
        print('Failed to compute sums')


def ensure_catalogue_products():
    # Ensure catalogue products exist for tests (mirrors verify_pack_b3)
    def ensure_crack(ps, name=None, price_excl='20.00'):
        psd = Decimal(str(ps))
        p = Paint.objects.filter(category=Paint.Category.CRACKS, package_size=psd).first()
        if p:
            return p
        return Paint.objects.create(
            name=name or f'Crack Filler {ps}kg',
            category=Paint.Category.CRACKS,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.KILOGRAM,
            package_size=psd,
            price_excl_vat=Decimal(price_excl),
            price_incl_vat=(Decimal(price_excl) * Decimal('1.15')).quantize(Decimal('0.01')),
        )

    def ensure_mould(ps, name=None, price_excl='3.00'):
        psd = Decimal(str(ps))
        p = Paint.objects.filter(category=Paint.Category.MOULD, package_size=psd).first()
        if p:
            return p
        return Paint.objects.create(
            name=name or f'Mould T {ps}L',
            category=Paint.Category.MOULD,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.LITRE,
            package_size=psd,
            price_excl_vat=Decimal(price_excl),
            price_incl_vat=(Decimal(price_excl) * Decimal('1.15')).quantize(Decimal('0.01')),
        )

    def ensure_clean(ps, name=None, price_excl='2.00'):
        psd = Decimal(str(ps))
        p = Paint.objects.filter(category=Paint.Category.CLEANING, package_size=psd).first()
        if p:
            return p
        return Paint.objects.create(
            name=name or f'Cleaner {ps}L',
            category=Paint.Category.CLEANING,
            pricing_method=Paint.PricingMethod.FIXED_PACK,
            package_unit=Paint.PackageUnit.LITRE,
            package_size=psd,
            price_excl_vat=Decimal(price_excl),
            price_incl_vat=(Decimal(price_excl) * Decimal('1.15')).quantize(Decimal('0.01')),
        )

    crack2 = ensure_crack('2.00', price_excl='20.00')
    crack5 = ensure_crack('5.00', price_excl='45.00')
    crack10 = ensure_crack('10.00', price_excl='85.00')
    mould1 = ensure_mould('1.00', price_excl='3.00')
    mould5 = ensure_mould('5.00', price_excl='12.00')
    clean1 = ensure_clean('1.00', price_excl='2.00')
    clean5 = ensure_clean('5.00', price_excl='8.00')

    # Sanding variants
    for grit, price in [('40 grit', '0.60'), ('60 grit', '0.55'), ('80 grit', '0.50'), ('100 grit', '0.45')]:
        if not Paint.objects.filter(category=Paint.Category.SANDING, variant_label=grit).exists():
            Paint.objects.create(
                name=f'Sanding {grit}',
                category=Paint.Category.SANDING,
                pricing_method=Paint.PricingMethod.PER_METRE,
                package_unit=Paint.PackageUnit.METRE,
                variant_label=grit,
                price_excl_vat=Decimal(price),
                price_incl_vat=(Decimal(price) * Decimal('1.15')).quantize(Decimal('0.01')),
            )

    if not Paint.objects.filter(category=Paint.Category.EFFLORESCENCE).exists():
        Paint.objects.create(
            name='Eff Removal',
            category=Paint.Category.EFFLORESCENCE,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            price_excl_vat=Decimal('0.00'),
            price_incl_vat=Decimal('0.00'),
            predetermined_note='Remove efflorescence',
        )
    if not Paint.objects.filter(category=Paint.Category.OLD_PAINT_REMOVAL).exists():
        Paint.objects.create(
            name='Old Paint Strip',
            category=Paint.Category.OLD_PAINT_REMOVAL,
            pricing_method=Paint.PricingMethod.NOTE_ONLY,
            price_excl_vat=Decimal('0.00'),
            price_incl_vat=Decimal('0.00'),
            predetermined_note='Strip old paint',
        )


if __name__ == '__main__':
    try:
        User = get_user_model()
        username = 'packb3_verifier'
        password = 'pass'
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
        logged = client.login(username=username, password=password)
        print('Client logged in:', logged)

        # Cleanup old
        marker = 'verify_pack_b3_trace'
        old_qs = Quotation.objects.filter(created_by=user, customer_name__icontains=marker)
        if old_qs.exists():
            print('Deleting previous temporary quotations created by this script:', old_qs.count())
            old_qs.delete()

        run_id = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        customer_name = f'Trace Verify ({marker}-{run_id})'
        q = Quotation.objects.create(created_by=user, customer_name=customer_name, customer_email='', customer_phone='')
        sec = QuotationSection.objects.create(quotation=q, subsection_key='interior_walls', display_name='Manual Walls Trace', substrate_type='INTERIOR')
        print('Created temporary quotation', q.pk, 'section', sec.pk, 'name=', customer_name)

        # Ensure catalogue
        ensure_catalogue_products()
        print('Catalogue products ensured')

        def post_interior_save(data):
            url = f'/quotations/{q.pk}/sections/{sec.pk}/interior-walls/save/'
            resp = client.post(url, data, follow=True)
            return resp

        def clear_prep_items():
            qs = QuotationLineItem.objects.filter(quotation=q, section=sec, item_type=QuotationLineItem.ItemType.PREP_WORK)
            if qs.exists():
                qs.delete()

        def latest_prep_item():
            return QuotationLineItem.objects.filter(quotation=q, section=sec, item_type=QuotationLineItem.ItemType.PREP_WORK).order_by('-pk').first()

        # 1) Single save with a mix of prep options
        clear_prep_items()
        post_data = {
            'wall_type': 'brick',
            'area_sqm': '20',
            'moisture_level': '0',
            'notes': 'Trace run',
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
        resp = post_interior_save(post_data)
        print('Posted interior save, status_code', resp.status_code)
        print_state('After initial POST', q)

        # Pricing-specific scripted checks: Crack Repair
        print('\n=== Crack Repair pack/quantity checks ===')
        for ps in ['2', '5', '10']:
            results = []
            for qty in [1, 2, 3]:
                clear_prep_items()
                data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'crack test','prep_work':['filling'],'prep_filling_pack_size':ps,'prep_filling_quantity':str(qty)}
                resp = post_interior_save(data)
                li = latest_prep_item()
                if li is None:
                    results.append((qty, None, None))
                else:
                    results.append((qty, li.total_excl_vat, li.metadata))
                    # Print Quotation totals after this operation
                    print(f'After filling pack {ps} qty {qty}:')
                    print_state(f'Post filling {ps} qty {qty}', q)
            print('Pack', ps, 'results:', results)

        # Mould Treatment
        print('\n=== Mould Treatment checks (1L/5L) ===')
        for ps in ['1','5']:
            results = []
            for qty in [1,2]:
                clear_prep_items()
                data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'mould test','prep_work':['mould_treatment'],'prep_mould_treatment_pack_size':ps,'prep_mould_treatment_quantity':str(qty)}
                resp = post_interior_save(data)
                li = latest_prep_item()
                if li is None:
                    results.append((qty, None, None))
                else:
                    results.append((qty, li.total_excl_vat, li.metadata))
                    print_state(f'Post mould {ps} qty {qty}', q)
            print('Mould pack', ps, 'results:', results)

        # Cleaning
        print('\n=== Cleaning checks (1L/5L) ===')
        for ps in ['1','5']:
            results = []
            for qty in [1,3]:
                clear_prep_items()
                data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'clean test','prep_work':['cleaning'],'prep_cleaning_pack_size':ps,'prep_cleaning_quantity':str(qty)}
                resp = post_interior_save(data)
                li = latest_prep_item()
                if li is None:
                    results.append((qty, None, None))
                else:
                    results.append((qty, li.total_excl_vat, li.metadata))
                    print_state(f'Post cleaning {ps} qty {qty}', q)
            print('Cleaning pack', ps, 'results:', results)

        # Sanding variants
        print('\n=== Sanding checks (grit variants, roll counts) ===')
        for grit in ['40','60','80','100']:
            clear_prep_items()
            data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'sanding test','prep_work':['sanding'],'prep_sanding_grit':grit,'prep_sanding_rolls':'2'}
            resp = post_interior_save(data)
            li = latest_prep_item()
            if li is None:
                print('Sanding', grit, '-> no PREP_WORK item created')
            else:
                print('Sanding', grit, '-> quantity:', li.quantity, 'unit:', li.unit, 'total_excl:', li.total_excl_vat, 'meta:', li.metadata)
                print_state(f'Post sanding {grit}', q)

        # Note-only checks
        print('\n=== Note-only checks (efflorescence & remove_paint) ===')
        for key in ['efflor_removal','remove_paint']:
            clear_prep_items()
            data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'note test','prep_work':[key]}
            resp = post_interior_save(data)
            li = latest_prep_item()
            if li is None:
                print(key, '-> no PREP_WORK item created')
            else:
                print(key, '-> pricing_status:', li.metadata.get('pricing_status'), 'predetermined_note:', li.metadata.get('predetermined_note'), 'total_excl:', li.total_excl_vat)
                print_state(f'Post note-only {key}', q)

        # Recalculate totals and print
        print('\nCalling recalculate_quotation_totals(q) at script end')
        recalculate_quotation_totals(q)
        print_state('After final recalculate_quotation_totals', q)

        print('\nDetailed trace completed')

    except Exception as exc:
        print('Exception during detailed trace run:')
        traceback.print_exc()
        sys.exit(2)
