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

}());
