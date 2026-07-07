#!/usr/bin/env python3
"""Pack B3 verification script.

Run from the repository root with the project virtualenv Python.
Example:
  .venv/Scripts/python.exe scripts/verify_pack_b3.py
"""
from decimal import Decimal
import os
import sys
import uuid
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

# Ensure the test client host is allowed (prevents DisallowedHost on testserver)
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
from quotation.pdf_service import build_pdf_context

print('Pack B3 verification script starting')

User = get_user_model()
username = 'packb3_verifier'
password = 'pass'
# Ensure a test user exists and can be reused safely across runs.
# Do NOT overwrite other users' emails; reuse existing user if present.
try:
    user = User.objects.get(username=username)
    created = False
    user.set_password(password)
    user.save()
except User.DoesNotExist:
    # Prefer a fixed email but fall back to a unique one if already used.
    base_email = 'packb3_verifier@example.test'
    if User.objects.filter(email=base_email).exists():
        base_email = f'packb3_verifier+{uuid.uuid4().hex[:8]}@example.test'
    user = User.objects.create_user(username=username, email=base_email, password=password)
    created = True

client = Client()
if not client.login(username=username, password=password):
    print('ERROR: client login failed')
    sys.exit(1)
print('Client logged in as', username)

# Create a uniquely identified temporary quotation for this run.
run_marker = 'verify_pack_b3'
# Remove any previous temporary quotations created by this script for this user.
old_qs = Quotation.objects.filter(created_by=user, customer_name__icontains=run_marker)
if old_qs.exists():
    print('Deleting previous temporary quotations created by this script:', old_qs.count())
    old_qs.delete()

run_id = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
customer_name = f'PackB3 Manual ({run_marker}-{run_id})'
q = Quotation.objects.create(created_by=user, customer_name=customer_name, customer_email='', customer_phone='')
sec = QuotationSection.objects.create(quotation=q, subsection_key='interior_walls', display_name='Manual Walls', substrate_type='INTERIOR')
print('Created temporary quotation', q.pk, 'section', sec.pk, 'name=', customer_name)

# Ensure catalogue products exist for tests
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

crack2 = ensure_crack('2.00', price_excl='20.00')
crack5 = ensure_crack('5.00', price_excl='45.00')
crack10 = ensure_crack('10.00', price_excl='85.00')

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

mould1 = ensure_mould('1.00', price_excl='3.00')
mould5 = ensure_mould('5.00', price_excl='12.00')

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

# Efflorescence / removal
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

print('Catalogue products ensured')

# Helper to post save for interior walls
def post_interior_save(section_pk, quotation_pk, data):
    url = f'/quotations/{quotation_pk}/sections/{section_pk}/interior-walls/save/'
    resp = client.post(url, data, follow=True)
    return resp


# Utility: clear any existing PREP_WORK items for this quotation/section
def clear_prep_items(quotation, section):
    qs = QuotationLineItem.objects.filter(quotation=quotation, section=section, item_type=QuotationLineItem.ItemType.PREP_WORK)
    if qs.exists():
        qs.delete()


# Utility: get the most recent PREP_WORK item for this quotation/section
def latest_prep_item(quotation, section):
    return QuotationLineItem.objects.filter(quotation=quotation, section=section, item_type=QuotationLineItem.ItemType.PREP_WORK).order_by('-pk').first()

# 1) Single save with a mix of prep options
clear_prep_items(q, sec)
post_data = {
    'wall_type': 'brick',
    'area_sqm': '20',
    'moisture_level': '0',
    'notes': 'Pack B3 verification',
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

resp = post_interior_save(sec.pk, q.pk, post_data)
print('Posted interior save, status_code', resp.status_code)

# Inspect created PREP_WORK line items
prep_items = list(QuotationLineItem.objects.filter(quotation=q, section=sec, item_type=QuotationLineItem.ItemType.PREP_WORK))
print('Found PREP_WORK items:', len(prep_items))
for li in prep_items:
    print(' -', li.pk, li.description, 'paint_pk=', li.paint.pk if li.paint else None, 'price_excl=', li.price_excl_vat, 'meta=', li.metadata, 'total_excl=', li.total_excl_vat)

# Verify builder page reflects saved prep_work (checkbox checked)
builder_url = f'/quotations/{q.pk}/builder/'
bhtml = client.get(builder_url).content.decode('utf-8')
for key in ['filling','mould_treatment','cleaning','sanding','efflor_removal','remove_paint']:
    id_str = f'id="prep_{sec.pk}_{key}"'
    checked = id_str in bhtml and ('checked' in bhtml.split(id_str,1)[1][:50])
    print(f'Builder checkbox for {key}: present={id_str in bhtml}, checked={checked}')

# Verify review page contains prep work descriptions
review_url = f'/quotations/{q.pk}/review/'
rev_html = client.get(review_url).content.decode('utf-8')
for li in prep_items:
    present = (li.description in rev_html) or (li.metadata and str(li.metadata.get('predetermined_note','')) in rev_html)
    print(f'Review page contains "{li.description}" or note: {present}')

# PDF context check
ctx = build_pdf_context(q)
found = False
for s in ctx.get('sections', []):
    for item in s.get('line_items', []):
        itm = item.get('item')
        if itm.item_type == QuotationLineItem.ItemType.PREP_WORK:
            print('PDF context PREP_WORK:', item.get('description'))
            found = True
print('PDF context includes PREP_WORK items:', found)

# Pricing-specific scripted checks:
print('\n=== Crack Repair pack/quantity checks ===')
for ps in ['2', '5', '10']:
    results = []
    for qty in [1, 2, 3]:
        clear_prep_items(q, sec)
        data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'crack test','prep_work':['filling'],'prep_filling_pack_size':ps,'prep_filling_quantity':str(qty)}
        resp = post_interior_save(sec.pk, q.pk, data)
        li = latest_prep_item(q, sec)
        if li is None:
            results.append((qty, None, None))
        else:
            results.append((qty, li.total_excl_vat, li.metadata))
    print('Pack', ps, 'results:', results)

print('\n=== Mould Treatment checks (1L/5L) ===')
for ps in ['1','5']:
    results = []
    for qty in [1,2]:
        clear_prep_items(q, sec)
        data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'mould test','prep_work':['mould_treatment'],'prep_mould_treatment_pack_size':ps,'prep_mould_treatment_quantity':str(qty)}
        resp = post_interior_save(sec.pk, q.pk, data)
        li = latest_prep_item(q, sec)
        if li is None:
            results.append((qty, None, None))
        else:
            results.append((qty, li.total_excl_vat, li.metadata))
    print('Mould pack', ps, 'results:', results)

print('\n=== Cleaning checks (1L/5L) ===')
for ps in ['1','5']:
    results = []
    for qty in [1,3]:
        clear_prep_items(q, sec)
        data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'clean test','prep_work':['cleaning'],'prep_cleaning_pack_size':ps,'prep_cleaning_quantity':str(qty)}
        resp = post_interior_save(sec.pk, q.pk, data)
        li = latest_prep_item(q, sec)
        if li is None:
            results.append((qty, None, None))
        else:
            results.append((qty, li.total_excl_vat, li.metadata))
    print('Cleaning pack', ps, 'results:', results)

print('\n=== Sanding checks (grit variants, roll counts) ===')
for grit in ['40','60','80','100']:
    clear_prep_items(q, sec)
    data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'sanding test','prep_work':['sanding'],'prep_sanding_grit':grit,'prep_sanding_rolls':'2'}
    resp = post_interior_save(sec.pk, q.pk, data)
    li = latest_prep_item(q, sec)
    if li is None:
        print('Sanding', grit, '-> no PREP_WORK item created')
    else:
        print('Sanding', grit, '-> quantity:', li.quantity, 'unit:', li.unit, 'total_excl:', li.total_excl_vat, 'meta:', li.metadata)

print('\n=== Note-only checks (efflorescence & remove_paint) ===')
for key in ['efflor_removal','remove_paint']:
    clear_prep_items(q, sec)
    data = {'wall_type':'brick','area_sqm':'5','moisture_level':'0','notes':'note test','prep_work':[key]}
    resp = post_interior_save(sec.pk, q.pk, data)
    li = latest_prep_item(q, sec)
    if li is None:
        print(key, '-> no PREP_WORK item created')
    else:
        print(key, '-> pricing_status:', li.metadata.get('pricing_status'), 'predetermined_note:', li.metadata.get('predetermined_note'), 'total_excl:', li.total_excl_vat)

# Recalculate totals and print
recalculate_quotation_totals(q)
q.refresh_from_db()
print('\nQuotation totals after checks: subtotal_excl_vat=', q.subtotal_excl_vat, 'vat_amount=', q.vat_amount, 'total_incl_vat=', q.total_incl_vat)

print('\nPack B3 verification script completed')
