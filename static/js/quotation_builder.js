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
  });

  document.addEventListener('submit', function (e) {
    var card = findSectionCard(e.target);
    if (!card) return;
    var badge = card.querySelector('.psp-unsaved-badge');
    if (badge) badge.style.display = 'none';
  });

}());
