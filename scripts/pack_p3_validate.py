#!/usr/bin/env python3
"""PACK P3 - Real catalogue pricing validation

Creates a clean test database, populates a realistic catalogue, runs several
pricing scenarios, computes manual expected results and compares against the
application pricing engine. Produces PASS/FAIL output and a summary.

This script does NOT modify pricing code.
"""

from decimal import Decimal, ROUND_HALF_UP
import os
import sys
import importlib
import shutil


def quantize(d: Decimal) -> Decimal:
    return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def setup_django_with_clean_db(db_path: str):
    # Remove any existing test DB
    if os.path.exists(db_path):
        os.remove(db_path)

    # Ensure settings module is mutable before django.setup()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    settings_mod = importlib.import_module('config.settings')
    settings_mod.DATABASES['default']['NAME'] = db_path

    import django
    django.setup()

    from django.core.management import call_command
    call_command('migrate', '--noinput')


def create_catalogue():
    from paints.models import Paint

    def mk(**kwargs):
        name = kwargs.pop('name')
        obj, created = Paint.objects.update_or_create(name=name, defaults=kwargs)
        return obj

    products = {}

    # Area coatings
    products['interior_acrylic'] = mk(
        name='Interior Acrylic',
        category=Paint.Category.INTERIOR,
        pricing_method=Paint.PricingMethod.AREA_COATING,
        finish=Paint.Finish.SMOOTH_MATTE,
        spread_rate_per_litre=Decimal('12.00'),
        priced_volume_litres=Decimal('1.00'),
        price_excl_vat=Decimal('140.00'),
        price_incl_vat=quantize(Decimal('140.00') * Decimal('1.15')),
    )

    products['exterior_acrylic'] = mk(
        name='Exterior Acrylic',
        category=Paint.Category.EXTERIOR,
        pricing_method=Paint.PricingMethod.AREA_COATING,
        finish=Paint.Finish.SMOOTH_SHEEN,
        spread_rate_per_litre=Decimal('10.00'),
        priced_volume_litres=Decimal('1.00'),
        price_excl_vat=Decimal('160.00'),
        price_incl_vat=quantize(Decimal('160.00') * Decimal('1.15')),
    )

    products['plaster_primer'] = mk(
        name='Plaster Primer',
        category=Paint.Category.PRIMER,
        pricing_method=Paint.PricingMethod.AREA_COATING,
        finish=Paint.Finish.NOT_APPLICABLE,
        spread_rate_per_litre=Decimal('8.00'),
        priced_volume_litres=Decimal('1.00'),
        standard_coats=1,
        price_excl_vat=Decimal('80.00'),
        price_incl_vat=quantize(Decimal('80.00') * Decimal('1.15')),
    )

    products['waterproofing'] = mk(
        name='Waterproof Membrane',
        category=Paint.Category.WATERPROOFING,
        pricing_method=Paint.PricingMethod.AREA_COATING,
        finish=Paint.Finish.NOT_APPLICABLE,
        spread_rate_per_litre=Decimal('6.00'),
        priced_volume_litres=Decimal('1.00'),
        standard_coats=1,
        price_excl_vat=Decimal('220.00'),
        price_incl_vat=quantize(Decimal('220.00') * Decimal('1.15')),
    )

    products['roof_paint'] = mk(
        name='Roof Paint',
        category=Paint.Category.EXTERIOR,
        pricing_method=Paint.PricingMethod.AREA_COATING,
        finish=Paint.Finish.DECO_PLAST,
        spread_rate_per_litre=Decimal('8.00'),
        priced_volume_litres=Decimal('1.00'),
        price_excl_vat=Decimal('180.00'),
        price_incl_vat=quantize(Decimal('180.00') * Decimal('1.15')),
    )

    products['ceiling_paint'] = mk(
        name='Ceiling Paint',
        category=Paint.Category.INTERIOR,
        pricing_method=Paint.PricingMethod.AREA_COATING,
        finish=Paint.Finish.SMOOTH_MATTE,
        spread_rate_per_litre=Decimal('14.00'),
        priced_volume_litres=Decimal('1.00'),
        price_excl_vat=Decimal('110.00'),
        price_incl_vat=quantize(Decimal('110.00') * Decimal('1.15')),
    )

    # Fixed packs: Crack filler (2/5/10 kg)
    products['crack_2'] = mk(
        name='Crack Filler 2kg',
        category=Paint.Category.CRACKS,
        pricing_method=Paint.PricingMethod.FIXED_PACK,
        package_unit=Paint.PackageUnit.KILOGRAM,
        package_size=Decimal('2.00'),
        price_excl_vat=Decimal('20.00'),
        price_incl_vat=quantize(Decimal('20.00') * Decimal('1.15')),
    )
    products['crack_5'] = mk(
        name='Crack Filler 5kg',
        category=Paint.Category.CRACKS,
        pricing_method=Paint.PricingMethod.FIXED_PACK,
        package_unit=Paint.PackageUnit.KILOGRAM,
        package_size=Decimal('5.00'),
        price_excl_vat=Decimal('45.00'),
        price_incl_vat=quantize(Decimal('45.00') * Decimal('1.15')),
    )
    products['crack_10'] = mk(
        name='Crack Filler 10kg',
        category=Paint.Category.CRACKS,
        pricing_method=Paint.PricingMethod.FIXED_PACK,
        package_unit=Paint.PackageUnit.KILOGRAM,
        package_size=Decimal('10.00'),
        price_excl_vat=Decimal('85.00'),
        price_incl_vat=quantize(Decimal('85.00') * Decimal('1.15')),
    )

    # Mould / Cleaning
    products['mould_1'] = mk(
        name='Mould Treatment 1L',
        category=Paint.Category.MOULD,
        pricing_method=Paint.PricingMethod.FIXED_PACK,
        package_unit=Paint.PackageUnit.LITRE,
        package_size=Decimal('1.00'),
        price_excl_vat=Decimal('3.00'),
        price_incl_vat=quantize(Decimal('3.00') * Decimal('1.15')),
    )
    products['mould_5'] = mk(
        name='Mould Treatment 5L',
        category=Paint.Category.MOULD,
        pricing_method=Paint.PricingMethod.FIXED_PACK,
        package_unit=Paint.PackageUnit.LITRE,
        package_size=Decimal('5.00'),
        price_excl_vat=Decimal('12.00'),
        price_incl_vat=quantize(Decimal('12.00') * Decimal('1.15')),
    )

    products['clean_1'] = mk(
        name='Cleaner 1L',
        category=Paint.Category.CLEANING,
        pricing_method=Paint.PricingMethod.FIXED_PACK,
        package_unit=Paint.PackageUnit.LITRE,
        package_size=Decimal('1.00'),
        price_excl_vat=Decimal('2.00'),
        price_incl_vat=quantize(Decimal('2.00') * Decimal('1.15')),
    )
    products['clean_5'] = mk(
        name='Cleaner 5L',
        category=Paint.Category.CLEANING,
        pricing_method=Paint.PricingMethod.FIXED_PACK,
        package_unit=Paint.PackageUnit.LITRE,
        package_size=Decimal('5.00'),
        price_excl_vat=Decimal('8.00'),
        price_incl_vat=quantize(Decimal('8.00') * Decimal('1.15')),
    )

    # Sanding variants
    for grit, price in [('40 grit', '0.60'), ('60 grit', '0.55'), ('80 grit', '0.50'), ('100 grit', '0.45')]:
        obj = mk(
            name=f'Sanding {grit}',
            category=Paint.Category.SANDING,
            pricing_method=Paint.PricingMethod.PER_METRE,
            package_unit=Paint.PackageUnit.METRE,
            variant_label=grit,
            price_excl_vat=Decimal(price),
            price_incl_vat=quantize(Decimal(price) * Decimal('1.15')),
        )
        products[f'sanding_{grit.replace(" ","_")}'] = obj

    # Note-only
    products['eff_removal'] = mk(
        name='Eff Removal',
        category=Paint.Category.EFFLORESCENCE,
        pricing_method=Paint.PricingMethod.NOTE_ONLY,
        predetermined_note='Remove efflorescence',
        price_excl_vat=Decimal('0.00'),
        price_incl_vat=Decimal('0.00'),
    )

    products['old_paint_strip'] = mk(
        name='Old Paint Strip',
        category=Paint.Category.OLD_PAINT_REMOVAL,
        pricing_method=Paint.PricingMethod.NOTE_ONLY,
        predetermined_note='Strip old paint',
        price_excl_vat=Decimal('0.00'),
        price_incl_vat=Decimal('0.00'),
    )

    return products


def build_and_price_line(quotation, section, paint, area=None, coats=1, package_count=None, roll_count=None, item_type=None, desc=None):
    from quotation.models import QuotationLineItem
    from quotation.pricing import apply_paint_pricing_to_line_item

    li = QuotationLineItem.objects.create(
        quotation=quotation,
        section=section,
        item_type=item_type or (QuotationLineItem.ItemType.PAINT if paint.category in (paint.Category.INTERIOR, paint.Category.EXTERIOR) else QuotationLineItem.ItemType.PREP_WORK),
        description=desc or paint.name,
        paint=paint,
        coats=coats,
        area_sqm=Decimal(area) if area is not None else None,
        price_excl_vat=paint.price_excl_vat,
        price_incl_vat=paint.price_incl_vat,
        metadata={},
    )

    # For fixed pack and per-metre, set metadata input fields
    if package_count is not None:
        li.metadata['package_count'] = package_count
    if roll_count is not None:
        li.metadata['roll_count'] = roll_count

    li.save()
    apply_paint_pricing_to_line_item(li)
    return li


def run_scenarios(products):
    from quotation.models import Quotation, QuotationSection
    from quotation.pricing import recalculate_quotation_totals

    scenarios = []

    # Scenario 1: Interior Walls 40m², 2 coats (Primer + Top Coat)
    q1 = Quotation.objects.create(created_by_id=1, customer_name='Scenario 1')
    s1 = QuotationSection.objects.create(quotation=q1, subsection_key='interior_walls', display_name='Interior Walls', substrate_type='INTERIOR')
    # Primer (plaster_primer) - enforced 1 coat by pricing
    li1a = build_and_price_line(q1, s1, products['plaster_primer'], area=Decimal('40.00'), coats=1, desc='Primer')
    # Top coat (interior acrylic)
    li1b = build_and_price_line(q1, s1, products['interior_acrylic'], area=Decimal('40.00'), coats=2, desc='Top Coat')
    recalculate_quotation_totals(q1)
    scenarios.append(('Scenario 1 - Interior 40m2 2 coats', q1, [li1a, li1b]))

    # Scenario 2: Exterior Walls 85m²: Primer, Waterproof, 2 finish coats
    q2 = Quotation.objects.create(created_by_id=1, customer_name='Scenario 2')
    s2 = QuotationSection.objects.create(quotation=q2, subsection_key='exterior_walls', display_name='Exterior Walls', substrate_type='EXTERIOR')
    li2a = build_and_price_line(q2, s2, products['plaster_primer'], area=Decimal('85.00'), coats=1, desc='Primer')
    li2b = build_and_price_line(q2, s2, products['waterproofing'], area=Decimal('85.00'), coats=1, desc='Waterproofing')
    li2c = build_and_price_line(q2, s2, products['exterior_acrylic'], area=Decimal('85.00'), coats=2, desc='Finish Coats')
    recalculate_quotation_totals(q2)
    scenarios.append(('Scenario 2 - Exterior 85m2 primer+waterproof+2 finish', q2, [li2a, li2b, li2c]))

    # Scenario 3: Roof 50m², 2 coats roof paint
    q3 = Quotation.objects.create(created_by_id=1, customer_name='Scenario 3')
    s3 = QuotationSection.objects.create(quotation=q3, subsection_key='roof', display_name='Roof', substrate_type='EXTERIOR')
    li3 = build_and_price_line(q3, s3, products['roof_paint'], area=Decimal('50.00'), coats=2, desc='Roof Paint 2 coats')
    recalculate_quotation_totals(q3)
    scenarios.append(('Scenario 3 - Roof 50m2 2 coats', q3, [li3]))

    # Scenario 4: Ceilings 30m², 1 coat
    q4 = Quotation.objects.create(created_by_id=1, customer_name='Scenario 4')
    s4 = QuotationSection.objects.create(quotation=q4, subsection_key='ceiling', display_name='Ceiling', substrate_type='INTERIOR')
    li4 = build_and_price_line(q4, s4, products['ceiling_paint'], area=Decimal('30.00'), coats=1, desc='Ceiling Paint')
    recalculate_quotation_totals(q4)
    scenarios.append(('Scenario 4 - Ceiling 30m2 1 coat', q4, [li4]))

    # Scenario 5: Large residential (multiple sections)
    q5 = Quotation.objects.create(created_by_id=1, customer_name='Scenario 5')
    # Living interior
    s5a = QuotationSection.objects.create(quotation=q5, subsection_key='living_interior', display_name='Living Interior', substrate_type='INTERIOR')
    li5a1 = build_and_price_line(q5, s5a, products['plaster_primer'], area=Decimal('120.00'), coats=1, desc='Living Primer')
    li5a2 = build_and_price_line(q5, s5a, products['interior_acrylic'], area=Decimal('120.00'), coats=2, desc='Living Finish')
    # Exterior facade
    s5b = QuotationSection.objects.create(quotation=q5, subsection_key='facade', display_name='Facade', substrate_type='EXTERIOR')
    li5b1 = build_and_price_line(q5, s5b, products['plaster_primer'], area=Decimal('200.00'), coats=1, desc='Facade Primer')
    li5b2 = build_and_price_line(q5, s5b, products['waterproofing'], area=Decimal('200.00'), coats=1, desc='Facade Waterproof')
    li5b3 = build_and_price_line(q5, s5b, products['exterior_acrylic'], area=Decimal('200.00'), coats=2, desc='Facade Finish')
    # Roof
    s5c = QuotationSection.objects.create(quotation=q5, subsection_key='roof_large', display_name='Roof', substrate_type='EXTERIOR')
    li5c = build_and_price_line(q5, s5c, products['roof_paint'], area=Decimal('150.00'), coats=2, desc='Roof Large')

    # Include some prep fixed packs: crack filler 5kg x 2
    s5d = QuotationSection.objects.create(quotation=q5, subsection_key='prep', display_name='Prep', substrate_type='INTERIOR')
    li5d = build_and_price_line(q5, s5d, products['crack_5'], area=None, coats=1, package_count=2, desc='Crack filler 5kg x2')

    recalculate_quotation_totals(q5)
    scenarios.append(('Scenario 5 - Large residential', q5, [li5a1, li5a2, li5b1, li5b2, li5b3, li5c, li5d]))

    return scenarios


def manual_calculate_area(price_excl, price_incl, priced_volume, spread_rate, area, coats, category=None):
    # Apply primer/waterproofing coat rule
    if category in ('PRIMER', 'WATERPROOFING'):
        used_coats = 1
    else:
        used_coats = int(coats)

    price_per_l_ex = Decimal(price_excl) / Decimal(priced_volume)
    price_per_l_in = Decimal(price_incl) / Decimal(priced_volume)
    required_litres = (Decimal(area) * Decimal(used_coats)) / Decimal(spread_rate)
    total_excl = required_litres * price_per_l_ex
    total_incl = required_litres * price_per_l_in
    return {
        'required_litres': required_litres,
        'price_per_l_ex': quantize(price_per_l_ex),
        'price_per_l_in': quantize(price_per_l_in),
        'total_excl': quantize(total_excl),
        'total_incl': quantize(total_incl),
        'vat': quantize(total_incl - total_excl),
    }


def validate_and_report(scenarios):
    overall_pass = True
    print('\n' + '='*80)
    print('PACK P3 Validation Report')
    print('='*80 + '\n')

    for name, q, items in scenarios:
        print('---', name, 'Quotation PK=', q.pk, '---')
        q.refresh_from_db()
        calc_sub = Decimal('0.00')
        calc_tot = Decimal('0.00')
        manual_sub = Decimal('0.00')
        manual_tot = Decimal('0.00')

        for li in items:
            li.refresh_from_db()
            meta = li.metadata or {}
            # Determine manual expected depending on pricing method
            pm = meta.get('pricing_method') or (li.paint.pricing_method if li.paint else None)
            if pm == 'AREA_COATING' or (li.paint and li.paint.pricing_method == li.paint.PricingMethod.AREA_COATING):
                snapshot = li.metadata.get('product_snapshot') or {}
                price_excl = snapshot.get('price_excl_vat') or str(li.price_excl_vat)
                price_incl = snapshot.get('price_incl_vat') or str(li.price_incl_vat)
                priced_vol = snapshot.get('priced_volume_litres') or li.paint.priced_volume_litres
                spread = snapshot.get('spread_rate_per_litre') or li.paint.spread_rate_per_litre
                cat = snapshot.get('category') or li.paint.category
                manual = manual_calculate_area(price_excl, price_incl, priced_vol, spread, li.area_sqm, li.coats, category=cat)
                print('Line:', li.description)
                print('  App total_excl:', li.total_excl_vat, 'total_incl:', li.total_incl_vat)
                print('  Manual total_excl:', manual['total_excl'], 'total_incl:', manual['total_incl'], 'vat:', manual['vat'])
                calc_sub += Decimal(li.total_excl_vat or 0)
                calc_tot += Decimal(li.total_incl_vat or 0)
                manual_sub += manual['total_excl']
                manual_tot += manual['total_incl']

            elif pm == 'FIXED_PACK' or (li.paint and li.paint.pricing_method == li.paint.PricingMethod.FIXED_PACK):
                # Manual fixed pack calc: package_count * package price
                pack_count = meta.get('package_count') or li.metadata.get('package_count') or None
                price_per_pack = li.price_excl_vat
                price_per_pack_in = li.price_incl_vat
                if pack_count is None:
                    print('  Skipping fixed-pack manual calc due to missing package_count metadata')
                    continue
                total_excl = Decimal(pack_count) * Decimal(price_per_pack)
                total_incl = Decimal(pack_count) * Decimal(price_per_pack_in)
                print('Line:', li.description)
                print('  App total_excl:', li.total_excl_vat, 'total_incl:', li.total_incl_vat)
                print('  Manual total_excl:', quantize(total_excl), 'total_incl:', quantize(total_incl))
                calc_sub += Decimal(li.total_excl_vat or 0)
                calc_tot += Decimal(li.total_incl_vat or 0)
                manual_sub += quantize(total_excl)
                manual_tot += quantize(total_incl)

            elif pm == 'PER_METRE' or (li.paint and li.paint.pricing_method == li.paint.PricingMethod.PER_METRE):
                # Per-metre uses roll_count metadata
                rc = meta.get('roll_count') or li.metadata.get('roll_count') or None
                price_per_m = meta.get('price_per_metre_excl_vat') or li.price_excl_vat
                price_per_m_in = meta.get('price_per_metre_incl_vat') or li.price_incl_vat
                if rc is None:
                    print('  Skipping per-metre manual calc due to missing roll_count')
                    continue
                total_excl = Decimal(rc) * Decimal(price_per_m)
                total_incl = Decimal(rc) * Decimal(price_per_m_in)
                print('Line:', li.description)
                print('  App total_excl:', li.total_excl_vat, 'total_incl:', li.total_incl_vat)
                print('  Manual total_excl:', quantize(total_excl), 'total_incl:', quantize(total_incl))
                calc_sub += Decimal(li.total_excl_vat or 0)
                calc_tot += Decimal(li.total_incl_vat or 0)
                manual_sub += quantize(total_excl)
                manual_tot += quantize(total_incl)

            elif pm == 'NOTE_ONLY' or (li.paint and li.paint.pricing_method == li.paint.PricingMethod.NOTE_ONLY):
                print('Line:', li.description, '(note-only)')
                calc_sub += Decimal(li.total_excl_vat or 0)
                calc_tot += Decimal(li.total_incl_vat or 0)
                manual_sub += Decimal('0.00')
                manual_tot += Decimal('0.00')

            else:
                print('Line:', li.description, 'Unrecognised pricing method; skipping manual calc')

        q.refresh_from_db()
        app_sub = quantize(Decimal(q.subtotal_excl_vat))
        app_tot = quantize(Decimal(q.total_incl_vat))
        manual_sub = quantize(manual_sub)
        manual_tot = quantize(manual_tot)

        passed = (app_sub == manual_sub and app_tot == manual_tot)
        print('\nScenario totals:')
        print('  App subtotal:', app_sub, 'App total:', app_tot)
        print('  Manual subtotal:', manual_sub, 'Manual total:', manual_tot)
        print('  Result:', 'PASS' if passed else 'FAIL')
        print('\n')

        if not passed:
            overall_pass = False
            print('DISCREPANCY FOUND in', name)
            print('Stopping further scenarios for investigation.')
            return False

    print('All scenarios processed. Overall result:', 'PASS' if overall_pass else 'FAIL')
    return overall_pass


def main():
    base = os.getcwd()
    test_db = os.path.join(base, 'db_pack_p3_test.sqlite3')
    print('Setting up clean test DB at', test_db)
    setup_django_with_clean_db(test_db)

    # Create a minimal test user with id=1 for created_by references
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if not User.objects.filter(username='pack_p3_user').exists():
        u = User.objects.create_user('pack_p3_user', email='pack_p3@example.test', password='pass')
    else:
        u = User.objects.get(username='pack_p3_user')

    products = create_catalogue()
    print('Catalogue created with products:', ', '.join(products.keys()))

    scenarios = run_scenarios(products)
    success = validate_and_report(scenarios)

    print('\nFinished. Test DB left at', test_db)
    if success:
        sys.exit(0)
    else:
        sys.exit(2)


if __name__ == '__main__':
    main()
