/**
 * quotation_builder.js
 * Live UX feedback for the Quotation Builder.
 *
 * What this does:
 *   1. Reads the moisture warning threshold from the container's
 *      data-moisture-threshold attribute.
 *   2. Listens for moisture input changes and immediately shows/hides
 *      the high-moisture badge in the section card header.
 *   3. Marks a section card as "Unsaved" when any form field changes,
 *      and clears that mark when the form is submitted.
 *
 * What this does NOT do:
 *   - No AJAX / server calls.
 *   - No pricing calculation.
 *   - It does not replace the server-rendered summary (source of truth).
 *   - Gracefully degrades if any element is missing (null-safe guards everywhere).
 */

(function () {
  'use strict';

  /* ── Read config ────────────────────────────────────────────── */
  var container = document.getElementById('pspBuilderContainer');
  var THRESHOLD = container
    ? parseInt(container.getAttribute('data-moisture-threshold') || '15', 10)
    : 15;

  /* ── Helpers ────────────────────────────────────────────────── */
  /**
   * Walk up the DOM from `el` and return the nearest ancestor
   * that has a `data-section-pk` attribute, or null.
   */
  function findSectionCard(el) {
    while (el && el !== document.body) {
      if (el.dataset && el.dataset.sectionPk) return el;
      el = el.parentElement;
    }
    return null;
  }

  /* Find substrate type for a section card (INTERIOR/EXTERIOR) */
  function getSectionSubstrate(card) {
    if (!card) return null;
    // server templates include substrate on section card as data-substrate-type
    return card.dataset.substrateType || null;
  }

  /* Get quotation PK from current pathname, if present (e.g. /123/builder/) */
  function getQuotationPk() {
    try {
      var m = window.location.pathname.match(/\/(\d+)\/builder/);
      return m ? m[1] : null;
    } catch (e) { return null; }
  }

  /* ── 1. Moisture live badge ─────────────────────────────────── */
  document.addEventListener('input', function (e) {
    var target = e.target;
    if (!target.name || target.name !== 'moisture_level') return;

    var card = findSectionCard(target);
    if (!card) return;
    var pk = card.dataset.sectionPk;

    var val = parseInt(target.value || '0', 10);
    if (isNaN(val) || val < 0) val = 0;

    /* Update the inline moisture warning div already in the form */
    var warnDiv = (
      document.getElementById('gsMoistureWarnDiv_' + pk) ||
      document.getElementById('iwMoistureWarnDiv_' + pk)
    );
    if (warnDiv) {
      warnDiv.style.display = val > THRESHOLD ? 'block' : 'none';
    }

    /* Update the header badge */
    var badge = card.querySelector('.psp-moisture-badge');
    if (badge) {
      badge.style.display = val > THRESHOLD ? 'inline-flex' : 'none';
      var valEl = badge.querySelector('.psp-moisture-val');
      if (valEl) valEl.textContent = val;
    }
  });

  /* ── 2. Unsaved-changes indicator ───────────────────────────── */
  document.addEventListener('change', function (e) {
    var card = findSectionCard(e.target);
    if (!card) return;
    /* Only flag forms that are section configurator forms
       (they all POST to a save URL and sit inside a card with data-section-pk) */
    var form = e.target.form || e.target.closest('form');
    if (!form) return;
    var badge = card.querySelector('.psp-unsaved-badge');
    if (badge) badge.style.display = 'inline-flex';
    card.dataset.unsaved = '1';
  });

  document.addEventListener('submit', function (e) {
    var card = findSectionCard(e.target);
    if (!card) return;
    var badge = card.querySelector('.psp-unsaved-badge');
    if (badge) badge.style.display = 'none';
    delete card.dataset.unsaved;
    try {
      // Clear any transient backup when a section save is submitted so
      // a subsequent redirect cannot cause stale restores.
      sessionStorage.removeItem('psp_section_state_backup_v1');
    } catch (ex) { /* ignore */ }
  });

  /* Also mark as unsaved on input events (captures typing without blur) */
  document.addEventListener('input', function (e) {
    try {
      var card = findSectionCard(e.target);
      if (!card) return;
      var form = e.target.form || e.target.closest('form');
      if (!form) return;
      var badge = card.querySelector('.psp-unsaved-badge');
      if (badge) badge.style.display = 'inline-flex';
      card.dataset.unsaved = '1';
    } catch (ex) { /* ignore */ }
  });

  /* ── 3. Section navigation rail ─────────────────────────────── */
  var prefersReducedMotion =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var scrollBehavior = prefersReducedMotion ? 'auto' : 'smooth';

  function scrollToCard(card) {
    if (!card) return;
    card.scrollIntoView({ behavior: scrollBehavior, block: 'start' });
    /* Flash highlight for orientation */
    card.classList.remove('psp-section-flash');
    /* Force reflow so re-adding the class re-triggers the animation */
    void card.offsetWidth;
    card.classList.add('psp-section-flash');
  }

  /* Old Jump-To rail removed — server-controlled tabs handle navigation. */

  /* Prev / Next buttons */
  function listSectionCards() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-section-pk]'));
  }
  function moveSection(currentPk, direction) {
    var cards = listSectionCards();
    var idx = cards.findIndex(function (c) { return c.dataset.sectionPk === String(currentPk); });
    if (idx < 0) return;
    var target = cards[idx + direction];
    if (target) scrollToCard(target);
  }
  document.addEventListener('click', function (e) {
    var prev = e.target.closest && e.target.closest('.psp-section-prev');
    if (prev) {
      e.preventDefault();
      moveSection(prev.dataset.sectionPrev, -1);
      return;
    }
    var next = e.target.closest && e.target.closest('.psp-section-next');
    if (next) {
      e.preventDefault();
      moveSection(next.dataset.sectionNext, +1);
    }
  });

  /* ── 6. Edit button: open the exact section and handle cross-leaflet cases ── */
  (function () {
    var builder = document.getElementById('pspBuilderContainer');
    var activeLeaflet = builder && builder.dataset.activeLeaflet;

    function collapseAllSections() {
      var collapseEls = Array.prototype.slice.call(document.querySelectorAll('[data-section-pk] .collapse'));
      collapseEls.forEach(function (el) {
        try {
          if (window.bootstrap && window.bootstrap.Collapse) {
            var inst = window.bootstrap.Collapse.getOrCreateInstance(el);
            if (inst && typeof inst.hide === 'function') inst.hide();
          } else {
            // Best-effort fallback if Bootstrap is not available
            el.classList.remove('show');
          }
        } catch (e) { /* ignore */ }
        // also mark toggler aria state
        try {
          var card = el.closest('[data-section-pk]');
          if (card) {
            var t = card.querySelector('[data-bs-toggle="collapse"]');
            if (t) {
              t.setAttribute('aria-expanded', 'false');
              t.classList.add('collapsed');
            }
          }
        } catch (e) { /* ignore */ }
      });
    }

    function openOnlySectionCard(card) {
      if (!card) return;
      var toggler = card.querySelector('[data-bs-toggle="collapse"]');
      if (!toggler) return;
      var target = toggler.getAttribute('data-bs-target');
      if (!target) return;
      var el = document.querySelector(target);
      if (!el) return;

      // Collapse others first
      collapseAllSections();

      // Show requested using Bootstrap Collapse API
      try {
        if (window.bootstrap && window.bootstrap.Collapse) {
          var inst = window.bootstrap.Collapse.getOrCreateInstance(el);
          if (inst && typeof inst.show === 'function') inst.show();
        } else {
          el.classList.add('show');
        }
      } catch (e) { /* ignore */ }

      // Update toggler state (aria) for the opened card
      try { toggler.setAttribute('aria-expanded', 'true'); toggler.classList.remove('collapsed'); } catch (e) { /* ignore */ }

      // Focus and scroll into view
      try {
        // Prefer focusing the first focusable control inside the collapse
        var focusable = el.querySelector('input,button,select,textarea,a,[tabindex]:not([tabindex="-1"])');
        if (focusable && typeof focusable.focus === 'function') {
          focusable.focus();
        } else {
          // Make card focusable briefly
          var prev = card.getAttribute('tabindex');
          card.setAttribute('tabindex', '-1');
          card.focus();
          if (prev === null) {
            // restore after a short delay
            setTimeout(function () { try { card.removeAttribute('tabindex'); } catch (e) {} }, 500);
          } else {
            card.setAttribute('tabindex', prev);
          }
        }
      } catch (e) { /* ignore */ }

      scrollToCard(card);
    }

    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest && ev.target.closest('a,button');
      if (!btn) return;

      // Let external anchors with leaflet query navigate normally
      if (btn.tagName.toLowerCase() === 'a' && btn.getAttribute('href') && btn.getAttribute('href').indexOf('?leaflet=') >= 0) {
        return;
      }

      // Only intercept header collapse togglers; allow body togglers (e.g. Cancel) to behave normally
      var headerToggler = null;
      if (btn.matches('[data-bs-toggle="collapse"]')) {
        // if the toggle is inside a card header, treat as header toggler
        if (btn.closest('.card-header')) headerToggler = btn;
      } else {
        // if clicked element is inside the header and contains a toggler
        var possible = btn.closest('[data-section-pk]');
        if (possible) {
          var h = possible.querySelector('.card-header [data-bs-toggle="collapse"]');
          if (h && (btn.closest('.card-header') || btn === h)) headerToggler = h;
        }
      }

      if (!headerToggler) return; // not a header toggler; ignore

      var sectionCard = headerToggler.closest('[data-section-pk]');
      if (!sectionCard) return;

      var cardLeaflet = sectionCard.dataset.leafletKey || '';
      if (activeLeaflet && cardLeaflet && cardLeaflet !== activeLeaflet) {
        if (anyUnsaved()) {
          var ok = window.confirm('You have unsaved changes in one or more sections. Switch to the target leaflet and lose unsaved changes?');
          if (!ok) return ev.preventDefault();
        }
        var base = window.location.pathname;
        var q = '?leaflet=' + encodeURIComponent(cardLeaflet) + '#section-' + encodeURIComponent(sectionCard.dataset.sectionPk || '');
        window.location.href = base + q;
        ev.preventDefault();
        return;
      }

      // Toggle behaviour: if target is open, hide it; otherwise open via central controller
      try {
        var target = headerToggler.getAttribute('data-bs-target');
        var collapseEl = target ? document.querySelector(target) : null;
        var isOpen = collapseEl && collapseEl.classList && collapseEl.classList.contains('show');
        if (isOpen) {
          // collapse this one
          if (window.bootstrap && window.bootstrap.Collapse) {
            var inst = window.bootstrap.Collapse.getOrCreateInstance(collapseEl);
            if (inst && typeof inst.hide === 'function') inst.hide();
          } else {
            collapseEl.classList.remove('show');
          }
        } else {
          openOnlySectionCard(sectionCard);
        }
      } catch (e) { /* ignore */ }

      ev.preventDefault();
    });
  })();

  /* Auto-open section if URL contains a #section- fragment */
  // Auto-open section on full window load (after inline partial scripts and images)
  window.addEventListener('load', function () {
    try {
      var h = window.location.hash || '';
      if (h.indexOf('#section-') === 0) {
        var card = document.querySelector(h);
        if (card) {
          // Use central controller to collapse others and open target
          try {
            // openOnlySectionCard is defined in the IIFE above; call via lookup
            // Find the function by reference (scoped) — recreate minimal open logic here
            var toggler = card.querySelector('[data-bs-toggle="collapse"]');
            if (toggler) {
              // collapse others
              var collapseEls = Array.prototype.slice.call(document.querySelectorAll('[data-section-pk] .collapse'));
              collapseEls.forEach(function (el) {
                try {
                  if (window.bootstrap && window.bootstrap.Collapse) {
                    var inst = window.bootstrap.Collapse.getOrCreateInstance(el);
                    if (inst && typeof inst.hide === 'function') inst.hide();
                  } else {
                    el.classList.remove('show');
                  }
                } catch (e) { /* ignore */ }
                try {
                  var c = el.closest('[data-section-pk]');
                  if (c) {
                    var t = c.querySelector('[data-bs-toggle="collapse"]');
                    if (t) { t.setAttribute('aria-expanded', 'false'); t.classList.add('collapsed'); }
                  }
                } catch (e) { /* ignore */ }
              });

              var target = toggler.getAttribute('data-bs-target');
              var el = document.querySelector(target);
              if (el) {
                try {
                  if (window.bootstrap && window.bootstrap.Collapse) {
                    var inst2 = window.bootstrap.Collapse.getOrCreateInstance(el);
                    if (inst2 && typeof inst2.show === 'function') inst2.show();
                  } else {
                    el.classList.add('show');
                  }
                } catch (e) { /* ignore */ }
                try { toggler.setAttribute('aria-expanded', 'true'); toggler.classList.remove('collapsed'); } catch (e) { /* ignore */ }
              }
            }
          } catch (e) { /* ignore */ }
          // Scroll into view and flash
          scrollToCard(card);
        }
      }
    } catch (e) { /* ignore */ }
  });

  /* ── 7. Preserve unsaved state when server 'Add another' form is submitted ── */
  (function () {
    var STORAGE_KEY = 'psp_section_state_backup_v1';

    function serializeSection(card) {
      var pk = card.dataset.sectionPk;
      var form = card.querySelector('form');
      if (!form) return null;

      var data = { pk: pk, fields: {}, paint_rows: [], waterproof_rows: [], primer_rows: [] };

      // Top-level fields (exclude row-contained inputs)
      Array.from(form.querySelectorAll('input[name],select[name],textarea[name]')).forEach(function (el) {
        if (el.closest('.paint-row') || el.closest('.waterproof-row') || el.closest('.primer-row')) return;
        if (!el.name) return;
        if (el.type === 'file') return; // cannot persist files

        if (el.type === 'checkbox') {
          // collect all checked values for this name
          if (!data.fields[el.name]) data.fields[el.name] = [];
          if (el.checked) data.fields[el.name].push(el.value);
          return;
        }
        if (el.type === 'radio') {
          if (el.checked) data.fields[el.name] = el.value;
          return;
        }
        if (el.tagName.toLowerCase() === 'select' && el.multiple) {
          data.fields[el.name] = Array.from(el.options).filter(function (o) { return o.selected; }).map(function (o) { return o.value; });
          return;
        }
        // default
        data.fields[el.name] = el.value;
      });

      // Repeatable rows: paint, waterproof, primer — capture per-row values in order
      function collectRows(containerId, rowClass, targetArray) {
        var container = card.querySelector('#' + containerId);
        if (!container) return;
        Array.from(container.querySelectorAll('.' + rowClass)).forEach(function (row) {
          var rowObj = {};
          Array.from(row.querySelectorAll('input[name],select[name],textarea[name]')).forEach(function (el) {
            if (!el.name) return;
            if (el.type === 'file') return;
            if (el.type === 'checkbox') {
              rowObj[el.name] = rowObj[el.name] || [];
              if (el.checked) rowObj[el.name].push(el.value);
              return;
            }
            if (el.type === 'radio') {
              if (el.checked) rowObj[el.name] = el.value;
              return;
            }
            if (el.tagName.toLowerCase() === 'select' && el.multiple) {
              rowObj[el.name] = Array.from(el.options).filter(function (o) { return o.selected; }).map(function (o) { return o.value; });
              return;
            }
            rowObj[el.name] = el.value;
          });
          targetArray.push(rowObj);
        });
      }

      collectRows('paintRows_' + pk, 'paint-row', data.paint_rows);
      collectRows('waterproofRows_' + pk, 'waterproof-row', data.waterproof_rows);
      collectRows('primerRows_' + pk, 'primer-row', data.primer_rows);

      return data;
    }

    function restoreSection(card, data) {
      if (!card || !data) return;
      var pk = data.pk;
      var form = card.querySelector('form');
      if (!form) return;

      // Restore top-level fields
      Object.keys(data.fields || {}).forEach(function (name) {
        var val = data.fields[name];
        var els = Array.from(form.querySelectorAll('[name="' + name + '"]'));
        if (!els || els.length === 0) return;
        // checkboxes group
        if (els[0].type === 'checkbox') {
          els.forEach(function (ch) { ch.checked = (Array.isArray(val) && val.indexOf(ch.value) !== -1); });
          return;
        }
        if (els[0].type === 'radio') {
          els.forEach(function (r) { r.checked = (r.value === val); });
          return;
        }
        if (els[0].tagName.toLowerCase() === 'select' && els[0].multiple) {
          els[0] && Array.from(els[0].options).forEach(function (o) { o.selected = Array.isArray(val) && val.indexOf(o.value) !== -1; });
          return;
        }
        // default: set first element's value
        els[0].value = val;
      });

      // Helper to ensure rows count and set per-row values
      function ensureAndRestoreRows(containerId, rowClass, rowsData) {
        var container = card.querySelector('#' + containerId);
        if (!container || !rowsData) return;
        var tpl = document.getElementById(containerId.replace(/Rows_/, 'RowTemplate_') + pk) || document.getElementById(containerId.replace(/Rows_/, 'RowTemplate_'));
        var existing = Array.from(container.querySelectorAll('.' + rowClass));
        // Add missing rows by cloning template if needed
        var need = rowsData.length - existing.length;
        while (need > 0 && tpl) {
          try {
            var html = tpl.innerHTML.replace(/__IDX__/g, Date.now());
            var div = document.createElement('div');
            div.innerHTML = html;
            container.insertBefore(div.firstElementChild, tpl);
            existing = Array.from(container.querySelectorAll('.' + rowClass));
          } catch (e) { break; }
          need -= 1;
        }
        // Now set values for each row
        existing = Array.from(container.querySelectorAll('.' + rowClass));
        rowsData.forEach(function (rowData, idx) {
          var row = existing[idx];
          if (!row) return;
          Object.keys(rowData).forEach(function (name) {
            var els = Array.from(row.querySelectorAll('[name="' + name + '"]'));
            if (!els || els.length === 0) return;
            if (els[0].type === 'checkbox') {
              els.forEach(function (ch) { ch.checked = Array.isArray(rowData[name]) && rowData[name].indexOf(ch.value) !== -1; });
              return;
            }
            if (els[0].type === 'radio') {
              els.forEach(function (r) { r.checked = (r.value === rowData[name]); });
              return;
            }
            if (els[0].tagName.toLowerCase() === 'select' && els[0].multiple) {
              els[0] && Array.from(els[0].options).forEach(function (o) { o.selected = Array.isArray(rowData[name]) && rowData[name].indexOf(o.value) !== -1; });
              return;
            }
            // default: set first
            els[0].value = rowData[name];
          });
        });
        // After restoring values, trigger change events on restored selects so delegated
        // handlers (per-section inline scripts) populate dependent controls (bases, spreads)
        existing.forEach(function (row) {
          try {
            if (rowClass === 'paint-row') {
              var ps = row.querySelector('.paint-row-paint-select');
              if (ps) ps.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (rowClass === 'primer-row') {
              var prs = row.querySelector('[name="primer_row_key"]');
              if (prs) prs.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (rowClass === 'waterproof-row') {
              var wfs = row.querySelector('[name="waterproof_row_key"]');
              if (wfs) wfs.dispatchEvent(new Event('change', { bubbles: true }));
            }
          } catch (e) { /* ignore dispatch errors */ }
        });
      }

      ensureAndRestoreRows('paintRows_' + pk, 'paint-row', data.paint_rows);
      ensureAndRestoreRows('waterproofRows_' + pk, 'waterproof-row', data.waterproof_rows);
      ensureAndRestoreRows('primerRows_' + pk, 'primer-row', data.primer_rows);

      // Show unsaved badge
      card.dataset.unsaved = '1';
      var b = card.querySelector('.psp-unsaved-badge'); if (b) b.style.display = 'inline-flex';
    }

    // Attach serialize-on-submit to server add forms
    document.querySelectorAll('form.psp-add-section-form').forEach(function (form) {
      form.addEventListener('submit', function (ev) {
        try {
          var payload = {
            ts: Date.now(),
            path: window.location.pathname,
            search: window.location.search || '',
            sections: {},
            leaflet: (container && container.dataset && container.dataset.activeLeaflet) ? container.dataset.activeLeaflet : '',
            quotation_pk: getQuotationPk(),
          };
          Array.from(document.querySelectorAll('[data-section-pk]')).forEach(function (card) {
            if (card.dataset.unsaved === '1') {
              var s = serializeSection(card);
              if (s) payload.sections[s.pk] = s;
            }
          });
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
        } catch (e) { /* ignore */ }
        // allow submit to proceed
      });
    });

    // On load, restore any saved payload — but only if it is recent.
    // Prevent stale Add-another backups from overwriting fresh server HTML.
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        var payload = JSON.parse(raw);
        var restoredAny = false;
        if (payload && payload.path && payload.sections && Object.prototype.hasOwnProperty.call(payload, 'ts')) {
          var now = Date.now();
          var ts = payload.ts;
          var RESTORE_MAX_AGE_MS = 2 * 60 * 1000; // 2 minutes
          if (now - ts <= RESTORE_MAX_AGE_MS) {
            // Validate quotation PK and leaflet to avoid cross-quotation/leaflet restores
            var currentPk = getQuotationPk();
            if (!payload.quotation_pk || (currentPk && String(payload.quotation_pk) === String(currentPk))) {
              var currentLeaflet = (container && container.dataset && container.dataset.activeLeaflet) ? container.dataset.activeLeaflet : '';
              if (!payload.leaflet || payload.leaflet === currentLeaflet) {
                Object.keys(payload.sections).forEach(function (pk) {
                  var card = document.querySelector('[data-section-pk="' + pk + '"]');
                  if (card) {
                    restoreSection(card, payload.sections[pk]);
                    restoredAny = true;
                  }
                });
              }
            }
          }
        }
        // Remove payload after attempting restore to avoid re-applying stale data
        try { sessionStorage.removeItem(STORAGE_KEY); } catch (ex) { /* ignore */ }
      }
    } catch (e) { /* ignore */ }
  })();

  /* ── 8. Smart catalogue filtering for paint/primer/waterproof selects ── */
  (function () {
    // Global catalogue exported by server in template as ALL_PAINTS
    var CATALOGUE = window.ALL_PAINTS || [];

    function _filterCatalogueBySectionCategory(cat, desiredCategories) {
      if (!CATALOGUE || !CATALOGUE.length) return [];
      return CATALOGUE.filter(function (p) {
        if (!p) return false;
        if (desiredCategories.length && desiredCategories.indexOf(p.category) === -1) return false;
        return true;
      });
    }

    function rebuildPaintOptions(selectEl, finishKey, substrate, rowType) {
      if (!selectEl) return;
      // preserve current selection if present
      var cur = selectEl.value || '';
      // clear
      selectEl.innerHTML = '';
      var empty = document.createElement('option');
      empty.value = '';
      empty.textContent = '-- Select ' + (rowType === 'paint' ? 'paint' : 'product') + ' --';
      selectEl.appendChild(empty);

      // Determine desired category for rowType
      var desiredCategories = [];
      if (rowType === 'paint') {
        // Mirror server-side behaviour: choose INTERIOR or EXTERIOR based on section substrate
        if (substrate && substrate === 'EXTERIOR') {
          desiredCategories = ['EXTERIOR'];
        } else {
          desiredCategories = ['INTERIOR'];
        }
      } else if (rowType === 'primer') {
        desiredCategories = ['PRIMER'];
      } else if (rowType === 'waterproof') {
        desiredCategories = ['WATERPROOFING'];
      }

      // Filter catalogue by desired categories and substrate
      var catFiltered = _filterCatalogueBySectionCategory(null, desiredCategories);
      var matched = catFiltered.filter(function (p) {
        if (!p) return false;
        if (rowType === 'paint' && finishKey && p.finish && p.finish !== finishKey) return false;
        // substrate constraint: if section is EXTERIOR, prefer EXTERIOR category only
        if (substrate && substrate === 'EXTERIOR' && p.category !== 'EXTERIOR') return false;
        return true;
      });

      if (!matched.length) {
        var opt = document.createElement('option');
        opt.value = '';
        opt.disabled = true;
        opt.textContent = 'No compatible products found.';
        selectEl.appendChild(opt);
        return;
      }

      matched.forEach(function (p) {
        var o = document.createElement('option');
        o.value = p.pk;
        o.textContent = p.name;
        if (String(p.pk) === String(cur)) o.selected = true;
        o.dataset.base = p.base_type || '';
        selectEl.appendChild(o);
      });
    }

    // Delegate change handler to finishes and row-type toggles
    document.addEventListener('change', function (ev) {
      var t = ev.target;
      // Finish change inside section -> update all paint-row selects in that section
      if (t.name === 'paint_row_finish') {
        var row = t.closest('.paint-row');
        var card = findSectionCard(t);
        var substrate = getSectionSubstrate(card);
        // For this row, rebuild its paint select to only include paints matching finish
        var paintSelect = row && row.querySelector('.paint-row-paint-select');
        rebuildPaintOptions(paintSelect, t.value, substrate, 'paint');
        return;
      }

      // If a primer or waterproof row product select is present, nothing to do here.
    });

    // Also run on initial page load to prune existing empty rows
    document.addEventListener('DOMContentLoaded', function () {
      Array.from(document.querySelectorAll('.paint-row')).forEach(function (r) {
        var finishSel = r.querySelector('[name="paint_row_finish"]');
        var paintSel = r.querySelector('.paint-row-paint-select');
        var card = findSectionCard(r);
        var substrate = getSectionSubstrate(card);
        if (finishSel && paintSel) rebuildPaintOptions(paintSel, finishSel.value, substrate, 'paint');
      });
      Array.from(document.querySelectorAll('.primer-row')).forEach(function (r) {
        var sel = r.querySelector('[name="primer_row_key"]');
        var card = findSectionCard(r);
        var substrate = getSectionSubstrate(card);
        if (sel) rebuildPaintOptions(sel, null, substrate, 'primer');
      });
      Array.from(document.querySelectorAll('.waterproof-row')).forEach(function (r) {
        var sel = r.querySelector('[name="waterproof_row_key"]');
        var card = findSectionCard(r);
        var substrate = getSectionSubstrate(card);
        if (sel) rebuildPaintOptions(sel, null, substrate, 'waterproof');
      });

      // When user clicks to add a new row, the per-section scripts clone the template.
      // Listen for add-row button clicks and populate the newly-inserted select.
      document.addEventListener('click', function (ev) {
        var btn = ev.target.closest && ev.target.closest('.add-paint-row, .add-primer-row, .add-waterproof-row');
        if (!btn) return;
        var sectionPk = btn.dataset.sectionPk || btn.getAttribute('data-section-pk');
        // Allow the per-section add handler to run first, then populate the select
        setTimeout(function () {
          if (btn.classList.contains('add-paint-row')) {
            var container = document.getElementById('paintRows_' + sectionPk);
            if (!container) return;
            var rows = container.querySelectorAll('.paint-row');
            var row = rows[rows.length - 1];
            if (!row) return;
            var finishSel = row.querySelector('[name="paint_row_finish"]');
            var paintSel = row.querySelector('.paint-row-paint-select');
            var card = findSectionCard(row);
            var substrate = getSectionSubstrate(card);
            if (paintSel) rebuildPaintOptions(paintSel, finishSel ? finishSel.value : '', substrate, 'paint');
          }
          if (btn.classList.contains('add-primer-row')) {
            var container = document.getElementById('primerRows_' + sectionPk);
            if (!container) return;
            var rows = container.querySelectorAll('.primer-row');
            var row = rows[rows.length - 1];
            if (!row) return;
            var sel = row.querySelector('[name="primer_row_key"]');
            var card = findSectionCard(row);
            var substrate = getSectionSubstrate(card);
            if (sel) rebuildPaintOptions(sel, null, substrate, 'primer');
          }
          if (btn.classList.contains('add-waterproof-row')) {
            var container = document.getElementById('waterproofRows_' + sectionPk);
            if (!container) return;
            var rows = container.querySelectorAll('.waterproof-row');
            var row = rows[rows.length - 1];
            if (!row) return;
            var sel = row.querySelector('[name="waterproof_row_key"]');
            var card = findSectionCard(row);
            var substrate = getSectionSubstrate(card);
            if (sel) rebuildPaintOptions(sel, null, substrate, 'waterproof');
          }
        }, 20);
      });
    });
  })();

  /* ── 4. Gentle confirm when leaving with unsaved work ───────── */
  function anyUnsaved() {
    return !!document.querySelector('[data-section-pk][data-unsaved="1"]');
  }
  document.querySelectorAll('[data-psp-review-link="true"]').forEach(function (link) {
    link.addEventListener('click', function (e) {
      if (!anyUnsaved()) return;
      var ok = window.confirm(
        'You have unsaved changes in one or more sections. Continue to Review without saving?'
      );
      if (!ok) e.preventDefault();
    });
  });
  window.addEventListener('beforeunload', function (e) {
    if (anyUnsaved()) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  /* Clone desktop summary into mobile offcanvas to avoid server-side duplication
     The summary partial is rendered once (desktop). For mobile we clone its
     HTML into the offcanvas when opened so the server doesn't render it twice. */
  (function () {
    var offcanvas = document.getElementById('builderSummaryOffcanvas');
    var offBody = document.getElementById('builderSummaryOffcanvasBody');
    var desktopSummary = document.querySelector('.psp-builder-summary-sticky');
    if (!offcanvas || !offBody || !desktopSummary) return;

    try {
      offcanvas.addEventListener('show.bs.offcanvas', function () {
        offBody.innerHTML = desktopSummary.innerHTML;
      });
      offcanvas.addEventListener('hidden.bs.offcanvas', function () {
        offBody.innerHTML = '';
      });
    } catch (e) {
      /* Fallback: copy on button click if bootstrap events unavailable */
      var btn = document.getElementById('pspSummaryFloatBtn');
      if (btn) btn.addEventListener('click', function () { offBody.innerHTML = desktopSummary.innerHTML; });
    }
  }());

  /* ── 5. Confirm removal of repeatable selections (progressive enhancement) ── */
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.dataset) return;
    /* data-confirm-remove-selection -> dataset.confirmRemoveSelection */
    if (!form.dataset.confirmRemoveSelection) return;

    var submitBtn = form.querySelector('button[type="submit"]');
    var label = (submitBtn && submitBtn.getAttribute('aria-label')) || 'Remove selection';
    var isFinal = form.dataset.isFinal === '1';

    var message = '';
    if (isFinal) {
      message = label + '. This is the final selection in this leaflet. Removing it will remove the leaflet from the quotation. Are you sure?';
    } else {
      message = label + '. Are you sure you want to remove this selection?';
    }

    if (!window.confirm(message)) {
      e.preventDefault();
      return false;
    }
    return true;
  });

}());

/* ------------------------------------------------------------------
   Image upload queue: persistent DataTransfer-backed queue for
   `input[name="section_images"]` across all sections.

   Behaviour:
   - Uses DataTransfer to maintain queued files per section.
   - Appends new selections to the queue (multiple picks supported).
   - Prevents duplicates (name+size+lastModified) and enforces max 3
     images taking existing DB images into account.
   - Rebuilds `input.files` from the queue so native form submit sends
     exactly queued files.
   - Creates a separate pending-preview container (runtime DOM) so
     existing DB images remain distinct from queued images.
   - Removal of a pending thumbnail removes it from the queue and
     updates `input.files`.
   - This code runs in-page and does not modify server templates.
------------------------------------------------------------------ */
(function () {
  'use strict';

  function fingerprintOfFile(f) {
    return (f && f.name ? f.name : '') + '|' + (f && f.size ? f.size : 0) + '|' + (f && f.lastModified ? f.lastModified : 0);
  }

  function initImageQueueForInput(input) {
    if (!input || input._pspQueueInit) return;
    input._pspQueueInit = true;

    // Derive section PK from input id (expected: sectionImageInput_<pk>)
    var match = (input.id || '').match(/sectionImageInput_(\d+)/);
    var sectionPk = match ? match[1] : null;
    if (!sectionPk) return;

    var container = document.getElementById('sectionImages_' + sectionPk);
    if (!container) return;

    // Create an inner wrapper for existing DB images and a pending uploads wrapper
    var existingWrapper = container.querySelector('.psp-existing-images');
    if (!existingWrapper) {
      // Move current element children that contain an <img> into the existing wrapper
      existingWrapper = document.createElement('div');
      existingWrapper.className = 'psp-existing-images d-flex flex-wrap gap-2 mb-2';
      var children = Array.prototype.slice.call(container.childNodes || []);
      children.forEach(function (n) {
        if (n.nodeType === 1 && n.querySelector && n.querySelector('img')) {
          existingWrapper.appendChild(n);
        }
      });
      // Insert existingWrapper at the start of container so server-rendered images remain first
      container.insertBefore(existingWrapper, container.firstChild || null);
    }

    var pendingId = 'sectionPendingImages_' + sectionPk;
    var pendingWrapper = document.getElementById(pendingId) || container.querySelector('#' + pendingId);
    if (!pendingWrapper) {
      pendingWrapper = document.createElement('div');
      pendingWrapper.id = pendingId;
      pendingWrapper.className = 'psp-pending-images d-flex flex-wrap gap-2 mb-2';
      pendingWrapper.setAttribute('aria-label', 'Pending uploads');
      container.appendChild(pendingWrapper);
    }

    // DataTransfer-backed queue
    var dt = (function () {
      try { return new DataTransfer(); } catch (e) { return null; }
    })();
    if (!dt) {
      // DataTransfer not available: graceful degrade (do nothing special)
      return;
    }

    function rebuildInputFiles() {
      try {
        input.files = dt.files;
      } catch (e) {
        // assignment may fail in some environments; log and continue
        console.warn('Unable to assign input.files from DataTransfer', e);
      }
    }

    function rebuildPendingPreview() {
      // Clear pending
      pendingWrapper.innerHTML = '';
      // Collect existing server-rendered image filenames to avoid duplicates
      var existingNames = {};
      try {
        var existingImgs = existingWrapper ? existingWrapper.querySelectorAll('img') : [];
        Array.prototype.slice.call(existingImgs).forEach(function (im) {
          try {
            var src = im.getAttribute('src') || im.src || '';
            var name = (src || '').split('/').pop().split('?')[0] || '';
            name = decodeURIComponent(name || '').toLowerCase();
            if (name) existingNames[name] = true;
          } catch (e) { /* ignore */ }
        });
      } catch (e) { /* ignore */ }

      Array.prototype.slice.call(dt.files).forEach(function (f, idx) {
        // If this queued file matches an existing server image filename, skip rendering
        try {
          if (f && f.name && existingNames && existingNames[f.name.toLowerCase()]) return;
        } catch (e) { /* ignore */ }
        var wrapper = document.createElement('div');
        wrapper.className = 'position-relative';
        wrapper.style.width = '88px';
        wrapper.style.height = '88px';

        var img = document.createElement('img');
        img.className = 'rounded border';
        img.style.width = '88px';
        img.style.height = '88px';
        img.style.objectFit = 'cover';

        // Reader for thumbnail
        try {
          var reader = new FileReader();
          reader.onload = function (ev) { img.src = ev.target.result; };
          reader.readAsDataURL(f);
        } catch (e) {
          // fallback: no preview
          img.alt = f.name || 'preview';
        }

        wrapper.appendChild(img);

        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn btn-sm btn-danger position-absolute top-0 end-0 m-1';
        removeBtn.setAttribute('aria-label', 'Remove pending image');
        removeBtn.innerHTML = '<span aria-hidden="true">&times;</span>';
        removeBtn.addEventListener('click', function () {
          // Rebuild DataTransfer without this index
          var newDt = new DataTransfer();
          Array.prototype.slice.call(dt.files).forEach(function (ff, ii) {
            if (ii === idx) return;
            try { newDt.items.add(ff); } catch (e) { /* ignore */ }
          });
          // Replace dt by copying items (DataTransfer is not clonable, so move items)
          dt = newDt;
          rebuildInputFiles();
          rebuildPendingPreview();
        });

        wrapper.appendChild(removeBtn);
        pendingWrapper.appendChild(wrapper);
      });
    }

    // Capture-phase change handler: intercept native change and make queued behaviour
    input.addEventListener('change', function (e) {
      try {
        // Only handle user-initiated events (avoid recursion from synthetic dispatch)
        if (!e.isTrusted) return;

        // Prevent other input-level change handlers (inline previews) from running
        e.stopImmediatePropagation();
        e.preventDefault();

        var selected = Array.prototype.slice.call(e.target.files || []);

        // existing DB images count
        var existingCount = (existingWrapper && existingWrapper.querySelectorAll && existingWrapper.querySelectorAll('img').length) || 0;
        var maxAllowed = Math.max(0, 3 - existingCount);
        var availableSlots = Math.max(0, maxAllowed - dt.files.length);

        var added = 0;
        selected.forEach(function (f) {
          if (added >= availableSlots) return;
          // duplicate check against queued files
          var dup = false;
          Array.prototype.slice.call(dt.files).forEach(function (qf) {
            if (qf.name === f.name && qf.size === f.size && (qf.lastModified || 0) === (f.lastModified || 0)) {
              dup = true;
            }
          });
          if (dup) return;
          try { dt.items.add(f); added += 1; } catch (err) { /* ignore add error */ }
        });

        if (added < selected.length && selected.length > 0) {
          try { window.alert('Maximum 3 images per section; extras were ignored.'); } catch (ex) { /* ignore */ }
        }

        // Rebuild the file input and preview
        rebuildInputFiles();
        rebuildPendingPreview();

        // Mark section as unsaved (do not dispatch synthetic 'change' which
        // would re-run inline preview handlers and duplicate thumbnails).
        try {
          var card = input && input.closest && input.closest('[data-section-pk]');
          if (card) {
            card.dataset.unsaved = '1';
            var b = card.querySelector && card.querySelector('.psp-unsaved-badge');
            if (b) b.style.display = 'inline-flex';
          }
        } catch (ex) { /* ignore */ }
      } catch (err) {
        console.error('psp image-queue change handler error', err);
      }
    }, true);

    // Ensure the queue is synced immediately before native form submit
    try {
      var form = input.closest && input.closest('form');
      if (form) {
        form.addEventListener('submit', function (ev) {
          try {
            // Rebuild input.files from the DataTransfer queue right before submit
            rebuildInputFiles();
            // Print counts for audit: dataTransfer.files.length and input.files.length
            try {
              var dtLen = dt && dt.files ? dt.files.length : 0;
              var inLen = input && input.files ? input.files.length : 0;
              // store for automated verification and also log
              try {
                var submittedInputSame = false;
                try { submittedInputSame = !!(form && form.querySelector && form.querySelector('input[type="file"][name="section_images"]') === input); } catch (ex) { submittedInputSame = false; }
                window._psp_last_submit_counts = { sectionPk: sectionPk, dt_files_len: dtLen, input_files_len: inLen, input_id: input && input.id, submitted_input_same: submittedInputSame };
                try { localStorage.setItem('_psp_last_submit_counts', JSON.stringify(window._psp_last_submit_counts)); } catch (ex) { /* ignore */ }
              } catch (ex) { /* ignore */ }
              console.log('psp-queue-before-submit', 'sectionPk', sectionPk, 'dt_files_len', dtLen, 'input_files_len', inLen);
            } catch (e) {
              console.log('psp-queue-before-submit', 'error-reading-lengths', e && e.message);
            }
          } catch (err) {
            console.error('psp-queue submit sync error', err);
          }
        }, true);
      }
    } catch (err) {
      /* ignore attach errors */
    }

    // Expose a small API if needed for tests
    input._pspImageQueue = {
      getFiles: function () { return Array.prototype.slice.call(dt.files); },
      clear: function () { dt = new DataTransfer(); rebuildInputFiles(); rebuildPendingPreview(); }
    };
  }

  function initAllQueues() {
    Array.prototype.slice.call(document.querySelectorAll('input[type="file"][name="section_images"]')).forEach(function (inp) {
      initImageQueueForInput(inp);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAllQueues); else initAllQueues();

}());
