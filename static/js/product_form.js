/* product_form.js
   Controls category-driven visibility and normalization on the Product form.
   - Runs on page load and when the category select changes
   - Shows/hides field wrappers with data-field attributes
   - Sets read-only badges for pricing_method and package_unit
   - Preserves existing values on load; only normalizes when category requires
*/
(function () {
  'use strict';

  function $(s, ctx) { return (ctx || document).querySelector(s); }
  function $all(s, ctx) { return Array.from((ctx || document).querySelectorAll(s)); }

  // Map categories to the UI behaviour described in Pack 3B2
  const Category = {
    INTERIOR: 'INTERIOR', EXTERIOR: 'EXTERIOR', PRIMER: 'PRIMER', WATERPROOFING: 'WATERPROOFING',
    CRACKS: 'CRACKS', MOULD: 'MOULD', CLEANING: 'CLEANING', SANDING: 'SANDING', EFFLORESCENCE: 'EFFLORESCENCE', OLD_PAINT_REMOVAL: 'OLD_PAINT_REMOVAL'
  };

  // Helpers to find wrapper elements. Use data-field attributes on wrappers.
  function showField(name) { const el = document.querySelector('[data-field="'+name+'"]'); if (el) el.style.display = ''; }
  function hideField(name) { const el = document.querySelector('[data-field="'+name+'"]'); if (el) el.style.display = 'none'; }
  function setInputValue(name, value) { const inp = document.querySelector('[name="'+name+'"]'); if (inp) inp.value = value; }
  function hideControl(name) { const inp = document.querySelector('[name="'+name+'"]'); if (!inp) return; inp.style.display='none'; inp.setAttribute('aria-hidden','true'); try{ inp.tabIndex = -1; }catch(e){} }
  function showControl(name) { const inp = document.querySelector('[name="'+name+'"]'); if (!inp) return; inp.style.display=''; inp.removeAttribute('aria-hidden'); try{ inp.tabIndex = 0; }catch(e){} let bd = document.querySelector('[data-badge-for="'+name+'"]'); if (bd) bd.innerHTML=''; }
  function setReadOnlyBadge(name, text) {
    const container = document.querySelector('[data-badge-for="'+name+'"]');
    if (!container) return;
    container.innerHTML = '<span class="badge bg-secondary text-white">'+text+'</span>';
  }

  function clearIfExists(name) {
    const inp = document.querySelector('[name="'+name+'"]');
    if (!inp) return;
    if (inp.tagName === 'INPUT' || inp.tagName === 'SELECT' || inp.tagName === 'TEXTAREA') inp.value = '';
  }

  function init() {
    const catSel = $('select[name="category"]');
    if (!catSel) return;

    function applyForCategory(cat, isLoad) {
      // Default: show common fields
      const common = ['name','description','category','image','is_active','price_excl_vat','price_incl_vat'];
      const allFields = ['finish','base_type','colour','spread_rate_per_litre','priced_volume_litres','package_size','package_unit','variant_label','predetermined_note','standard_coats'];
      allFields.forEach(f=>hideField(f));
      common.concat([]).forEach(f=>showField(f));

      // Pricing method badge text map
      const pmBadges = {
        AREA_COATING: 'Area-based coating',
        FIXED_PACK: 'Fixed package',
        PER_METRE: 'Per metre',
        NOTE_ONLY: 'Note only'
      };

      if (cat === Category.INTERIOR || cat === Category.EXTERIOR) {
        ['finish','base_type','colour','spread_rate_per_litre','priced_volume_litres'].forEach(showField);
        // package unit not applicable (model keys: NA, kg, L, m)
        setInputValue('pricing_method', 'AREA_COATING');
        setInputValue('package_unit', 'NA');
        // Ensure wrappers visible and hide the editable controls while showing read-only badges
        showField('package_unit'); showField('pricing_method');
        hideControl('pricing_method'); hideControl('package_unit');
        setReadOnlyBadge('pricing_method', pmBadges.AREA_COATING);
        setReadOnlyBadge('package_unit', 'Not applicable');
        ['package_size','variant_label','predetermined_note','standard_coats'].forEach(clearIfExists);
      }

      else if (cat === Category.PRIMER || cat === Category.WATERPROOFING) {
        ['spread_rate_per_litre','priced_volume_litres','standard_coats'].forEach(showField);
        setInputValue('pricing_method', 'AREA_COATING');
        setInputValue('finish', 'NOT_APPLICABLE');
        setInputValue('base_type', 'NOT_APPLICABLE');
        setInputValue('package_unit', 'NA');
        setInputValue('standard_coats', '1');
        showField('package_unit'); showField('pricing_method');
        hideControl('pricing_method'); hideControl('package_unit');
        setReadOnlyBadge('pricing_method', pmBadges.AREA_COATING);
        setReadOnlyBadge('package_unit', 'Not applicable');
      }

      else if (cat === Category.CRACKS) {
        ['package_size'].forEach(showField);
        setInputValue('pricing_method', 'FIXED_PACK');
        // package_unit model key: 'kg'
        setInputValue('package_unit', 'kg');
        setInputValue('finish', 'NOT_APPLICABLE');
        setInputValue('base_type', 'NOT_APPLICABLE');
        showField('pricing_method'); showField('package_unit');
        hideControl('pricing_method'); hideControl('package_unit');
        setReadOnlyBadge('pricing_method', pmBadges.FIXED_PACK);
        setReadOnlyBadge('package_unit', 'kg');
        // limit package_size to the allowed set using a select if present
        const pkg = document.querySelector('[name="package_size"]');
        if (pkg && pkg.tagName === 'INPUT') {
          // preserve existing value where possible
          const existing = pkg.value;
          const sel = document.createElement('select'); sel.name = pkg.name; sel.className = pkg.className;
          ['2.00','5.00','10.00'].forEach(v=>{ const o=document.createElement('option'); o.value=v; o.text=v+' kg'; sel.appendChild(o); });
          if (existing) try { sel.value = existing; } catch(e) {}
          pkg.parentNode.replaceChild(sel, pkg);
        }
      }

      else if (cat === Category.MOULD || cat === Category.CLEANING) {
        ['package_size'].forEach(showField);
        setInputValue('pricing_method', 'FIXED_PACK');
        // package_unit model key for litre: 'L'
        setInputValue('package_unit', 'L');
        setInputValue('finish', 'NOT_APPLICABLE');
        setInputValue('base_type', 'NOT_APPLICABLE');
        showField('pricing_method'); showField('package_unit');
        hideControl('pricing_method'); hideControl('package_unit');
        setReadOnlyBadge('pricing_method', pmBadges.FIXED_PACK);
        setReadOnlyBadge('package_unit', 'L');
        const pkg = document.querySelector('[name="package_size"]');
        if (pkg && pkg.tagName === 'INPUT') {
          const existing = pkg.value;
          const sel = document.createElement('select'); sel.name = pkg.name; sel.className = pkg.className;
          ['1.00','5.00'].forEach(v=>{ const o=document.createElement('option'); o.value=v; o.text=v+' L'; sel.appendChild(o); });
          if (existing) try { sel.value = existing; } catch(e) {}
          pkg.parentNode.replaceChild(sel, pkg);
        }
      }

      else if (cat === Category.SANDING) {
        ['variant_label'].forEach(showField);
        setInputValue('pricing_method', 'PER_METRE');
        // model key for metre: 'm'
        setInputValue('package_unit', 'm');
        setInputValue('finish', 'NOT_APPLICABLE');
        setInputValue('base_type', 'NOT_APPLICABLE');
        showField('pricing_method'); showField('package_unit');
        hideControl('pricing_method'); hideControl('package_unit');
        setReadOnlyBadge('pricing_method', pmBadges.PER_METRE);
        setReadOnlyBadge('package_unit', 'm');
        // ensure variant select and preserve existing value
        const varEl = document.querySelector('[name="variant_label"]');
        if (varEl && varEl.tagName !== 'SELECT') {
          const existing = varEl.value;
          const sel = document.createElement('select'); sel.name = varEl.name; sel.className = varEl.className;
          ['40 grit','60 grit','80 grit','100 grit'].forEach(v=>{ const o=document.createElement('option'); o.value=v; o.text=v; sel.appendChild(o); });
          if (existing) try { sel.value = existing; } catch(e) {}
          varEl.parentNode.replaceChild(sel, varEl);
        }
      }

      else if (cat === Category.EFFLORESCENCE || cat === Category.OLD_PAINT_REMOVAL) {
        ['predetermined_note'].forEach(showField);
        setInputValue('pricing_method', 'NOTE_ONLY');
        setInputValue('finish', 'NOT_APPLICABLE');
        setInputValue('base_type', 'NOT_APPLICABLE');
        setInputValue('package_unit', 'NA');
        setInputValue('price_excl_vat', '0.00');
        setInputValue('price_incl_vat', '0.00');
        showField('pricing_method'); showField('package_unit');
        hideControl('pricing_method'); hideControl('package_unit');
        setReadOnlyBadge('pricing_method', pmBadges.NOTE_ONLY);
        setReadOnlyBadge('package_unit', 'Not applicable');
      }

      // show helper texts for primer/waterproofing and sanding and note-only
      hideField('category_helper');
      if (cat === Category.PRIMER || cat === Category.WATERPROOFING) {
        showField('primer_helper');
      } else if (cat === Category.SANDING) {
        showField('sanding_helper');
      } else if (cat === Category.EFFLORESCENCE || cat === Category.OLD_PAINT_REMOVAL) {
        showField('note_helper');
      }
    }

    // Init: add badges containers if not present
    ['pricing_method','package_unit'].forEach(function (name) {
      const elt = document.querySelector('[name="'+name+'"]');
      if (!elt) return;
      let wrap = elt.closest('.col-sm-3') || elt.parentNode;
      if (!wrap) return;
      if (!wrap.querySelector('[data-badge-for="'+name+'"]')) {
        const bd = document.createElement('div'); bd.setAttribute('data-badge-for', name); bd.style.marginTop='6px'; wrap.appendChild(bd);
      }
    });

    // Initial apply
    applyForCategory(catSel.value, true);

    // Bind change
    catSel.addEventListener('change', function () { applyForCategory(this.value, false); });
  }

  // Run on DOMContentLoaded
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

})();
