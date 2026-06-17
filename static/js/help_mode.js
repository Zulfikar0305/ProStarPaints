/* ProStar Paints — Guided Help Mode
 * Lightweight engine: toggle, demo labels, page walkthroughs.
 * - State persisted in localStorage (psp-help-mode).
 * - Walkthroughs keyed by view name (body[data-psp-page]).
 * - Respects prefers-reduced-motion AND body[data-reduce-motion="true"].
 * - No external libraries.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'psp-help-mode';
  var body        = document.body;
  var banner      = document.getElementById('pspHelpBanner');
  var spotlight   = document.getElementById('pspSpotlight');
  var tour        = document.getElementById('pspWalkthrough');
  if (!body) return;

  var prefersReducedMotion =
    (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) ||
    body.getAttribute('data-reduce-motion') === 'true';

  /* ── Walkthrough catalogue ────────────────────────────────────
     Each entry keyed by `view_name` (resolver_match.view_name).
     Steps: { selector, title, body, role?: 'admin'|'rep' }
     Steps whose selector matches nothing are skipped at runtime,
     so partial pages stay safe across rebuilds.
     ────────────────────────────────────────────────────────────── */
  var WALKTHROUGHS = {
    'dashboard:dashboard': [
      { selector: '.psp-sidebar-nav',          title: 'Main navigation',
        body: 'Everything lives in the left sidebar. Roles filter what you see — admins get more sections than reps.' },
      { selector: '.psp-topbar-right',         title: 'Topbar tools',
        body: 'Search, quick actions (Ctrl+K), help, notifications and your account menu — all reachable from any page.' },
      { selector: '[data-onboarding-key]',     title: 'Onboarding checklist',
        body: 'Step-by-step setup tracker. Items tick themselves automatically as you complete each setup task.' },
      { selector: '.psp-kpi-card, .psp-hero-stat', title: 'Key metrics',
        body: 'At-a-glance counts of quotations, recent activity and pipeline. Use the period filter to scope the window.' }
    ],
    'quotation:quotation_list': [
      { selector: 'form[role="search"], .psp-filters', title: 'Filters',
        body: 'Narrow the workspace by status, owner or date range. Filters are bookmark-friendly via the URL.' },
      { selector: 'a[href*="start"], .btn-primary',    title: 'Start a new quotation',
        body: 'Kicks off the multi-step quotation wizard. You can save as a draft at any point.' },
      { selector: 'table',                              title: 'Quotation list',
        body: 'Drafts open in the builder; completed quotations open in a read-only detail view with re-export.' }
    ],
    'quotation:quotation_builder': [
      { selector: '[data-section-pk]',         title: 'Surface card',
        body: 'Open one card at a time. Choose substrate, finish, paint options and area, then hit Save.' },
      { selector: '.psp-save-bar',             title: 'Sticky save bar',
        body: 'Save, Cancel and Prev/Next stay pinned to the bottom so they\u2019re always in thumb reach on tablets.' },
      { selector: '.psp-bottom-summary-bar, #builderSummaryOffcanvas, .col-lg-4', title: 'Live summary',
        body: 'A running summary of everything you\u2019ve saved. Tap on mobile to expand.' },
      { selector: '[data-psp-review-link]',    title: 'Continue to review',
        body: 'When every section is green, send the quotation to Review and pick a PDF template.' }
    ],
    'quotation:pdf_select': [
      { selector: '.psp-readiness, .alert',    title: 'Readiness banner',
        body: 'Tells you whether the quotation has everything it needs. Missing items disable PDF generation.' },
      { selector: '.psp-pdf-card, .card',      title: 'Template gallery',
        body: 'Each card is a customer-facing layout. The data is the same — the styling differs. You can regenerate later.' }
    ],
    'paints:paint_list': [
      { selector: 'form[role="search"], .psp-filters', title: 'Filter the catalogue',
        body: 'Find paints by brand, finish, type or active status.' },
      { selector: 'a[href*="pricing"]',        title: 'Pricing maintenance',
        body: 'Admin-only inline price editor with audit trail. Bulk-tune your catalogue without leaving the page.', role: 'admin' },
      { selector: 'table',                     title: 'Paint catalogue',
        body: 'Deactivate paints instead of deleting — quotations referencing them stay intact.' }
    ],
    'paints:paint_pricing': [
      { selector: '.psp-quality-scorecard, .card', title: 'Catalogue quality',
        body: 'Quick health metrics: missing prices, stale prices, coverage gaps.' },
      { selector: 'tbody tr',                  title: 'Inline price editor',
        body: 'Click any price to edit. Save writes an audit log row with before/after values.' }
    ],
    'users:user_list': [
      { selector: 'table',                     title: 'Team roster',
        body: 'All users with their role and status. Admins manage everyone; reps see only themselves.' },
      { selector: 'a.btn-primary, a[href*="create"]', title: 'Add a teammate',
        body: 'Invite reps or admins. Deactivating is preferred over deleting — it preserves history.' }
    ],
    'system_tools:control_center': [
      { selector: '.psp-tool-card, .card',     title: 'System health tiles',
        body: 'Each tile is a self-contained health check or maintenance tool. Run, inspect output, walk away.' }
    ],
    'users:app_settings': [
      { selector: 'form',                      title: 'Personalise your workspace',
        body: 'Theme, density, accent and motion live here. Tour and help-tip toggles are nearby.' }
    ]
  };

  /* ── Demo labels — feature tags attached centrally ──────────── */
  var DEMO_LABELS = [
    { selector: '.psp-palette-trigger',  text: 'Command Palette: fast nav for power users (Ctrl+K)' },
    { selector: '.psp-help-trigger',     text: 'Help Center: searchable, role-aware docs' },
    { selector: '[id*="Notify"], .psp-notify', text: 'Notifications: live activity feed' },
    { selector: '.psp-topbar-avatar',    text: 'Account menu: profile, settings, sign out' },
    { selector: '.psp-watermark',        text: 'Brand watermark: subtle, print-safe' },
    { selector: 'a[href*="control-center"]', text: 'Control Center: admin system health' },
    { selector: 'a[href*="paints"]',     text: 'Paint catalogue: the heart of pricing inputs' },
    { selector: 'a[href*="audit"]',      text: 'Audit log: who changed what, when' },
    { selector: '#pspFab',               text: 'Quick Actions: floating shortcut for reps' }
  ];

  /* ── State helpers ────────────────────────────────────────── */
  function isOn() {
    try { return localStorage.getItem(STORAGE_KEY) === 'on'; } catch (e) { return false; }
  }
  function setOn(on) {
    try { localStorage.setItem(STORAGE_KEY, on ? 'on' : 'off'); } catch (e) {}
    body.setAttribute('data-help-mode', on ? 'on' : 'off');
    if (banner) banner.hidden = !on;
    document.querySelectorAll('[data-psp-help-mode-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.classList.toggle('is-on', on);
    });
    if (on) {
      applyHighlights();
      applyDemoLabels();
    } else {
      removeHighlights();
      removeDemoLabels();
      closeTour();
    }
  }

  /* ── Highlight rings around help_tip icons & known anchors ── */
  function highlightTargets() {
    var nodes = [];
    /* All inline help tip icons */
    document.querySelectorAll('.psp-help-tip, [data-bs-toggle="tooltip"]').forEach(function (n) { nodes.push(n); });
    /* All elements with data-help-mode-highlight (opt-in per page) */
    document.querySelectorAll('[data-help-mode-highlight]').forEach(function (n) { nodes.push(n); });
    return nodes;
  }
  function applyHighlights() {
    highlightTargets().forEach(function (n) { n.classList.add('psp-help-glow'); });
  }
  function removeHighlights() {
    document.querySelectorAll('.psp-help-glow').forEach(function (n) { n.classList.remove('psp-help-glow'); });
  }

  /* ── Demo labels — tooltip-style floating chips ───────────── */
  function applyDemoLabels() {
    DEMO_LABELS.forEach(function (def) {
      document.querySelectorAll(def.selector).forEach(function (el) {
        if (el.dataset.pspDemoLabelled === '1') return;
        el.dataset.pspDemoLabelled = '1';
        el.classList.add('psp-demo-tagged');
        if (!el.getAttribute('data-psp-demo-label')) {
          el.setAttribute('data-psp-demo-label', def.text);
        }
      });
    });
  }
  function removeDemoLabels() {
    document.querySelectorAll('.psp-demo-tagged').forEach(function (el) {
      el.classList.remove('psp-demo-tagged');
    });
  }

  /* ── Walkthrough engine ───────────────────────────────────── */
  var tourState = { steps: [], index: 0, active: false };

  function pageKey() {
    return body.getAttribute('data-psp-page') || '';
  }
  function isAdmin() {
    return body.getAttribute('data-user-role') === 'admin' || body.hasAttribute('data-user-admin');
  }
  function loadSteps() {
    var raw = WALKTHROUGHS[pageKey()] || [];
    /* Filter to: steps with at least one matching element AND role-allowed */
    return raw.filter(function (s) {
      if (s.role === 'admin' && !isAdmin()) return false;
      var el = document.querySelector(s.selector);
      return !!el;
    });
  }

  function positionTourFor(target) {
    if (!tour || !spotlight || !target) return;
    var rect = target.getBoundingClientRect();
    var pad = 6;
    /* Spotlight ring */
    spotlight.hidden = false;
    spotlight.style.top    = (rect.top + window.scrollY - pad) + 'px';
    spotlight.style.left   = (rect.left + window.scrollX - pad) + 'px';
    spotlight.style.width  = (rect.width  + pad * 2) + 'px';
    spotlight.style.height = (rect.height + pad * 2) + 'px';

    /* Callout — try below first, then above, clamp to viewport */
    tour.hidden = false;
    /* Force a reflow so size is correct */
    var tw = tour.offsetWidth, th = tour.offsetHeight;
    var vw = window.innerWidth, vh = window.innerHeight;
    var top, left, arrow = 'top';
    if (rect.bottom + th + 16 < vh) {
      top = rect.bottom + window.scrollY + 12; arrow = 'top';
    } else if (rect.top - th - 16 > 0) {
      top = rect.top + window.scrollY - th - 12; arrow = 'bottom';
    } else {
      top = window.scrollY + Math.max(16, (vh - th) / 2); arrow = 'top';
    }
    left = rect.left + window.scrollX + (rect.width / 2) - (tw / 2);
    /* Clamp horizontally */
    var maxLeft = window.scrollX + vw - tw - 12;
    var minLeft = window.scrollX + 12;
    if (left > maxLeft) left = maxLeft;
    if (left < minLeft) left = minLeft;
    tour.style.top = top + 'px';
    tour.style.left = left + 'px';
    tour.setAttribute('data-arrow', arrow);
  }

  function renderStep() {
    var step = tourState.steps[tourState.index];
    if (!step) { closeTour(); return; }
    var target = document.querySelector(step.selector);
    if (!target) { /* skip ahead */ tourState.index++; renderStep(); return; }

    var titleEl = document.getElementById('pspWalkthroughTitle');
    var bodyEl  = document.getElementById('pspWalkthroughBody');
    var numEl   = document.getElementById('pspWalkthroughStepNum');
    var prevBtn = document.getElementById('pspWalkthroughPrev');
    var nextBtn = document.getElementById('pspWalkthroughNext');
    var doneBtn = document.getElementById('pspWalkthroughDone');

    if (titleEl) titleEl.textContent = step.title;
    if (bodyEl)  bodyEl.textContent  = step.body;
    if (numEl)   numEl.textContent   = (tourState.index + 1) + '/' + tourState.steps.length;
    if (prevBtn) prevBtn.disabled    = tourState.index === 0;
    var last = tourState.index === tourState.steps.length - 1;
    if (nextBtn) nextBtn.hidden = last;
    if (doneBtn) doneBtn.hidden = !last;

    /* Scroll target into view (respects reduce-motion) */
    target.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'center' });
    /* Wait a tick for scroll to settle before positioning */
    setTimeout(function () { positionTourFor(target); }, prefersReducedMotion ? 0 : 250);
  }

  function startTour() {
    if (!tour) return;
    tourState.steps = loadSteps();
    if (!tourState.steps.length) {
      /* Fallback toast — nothing to tour on this page */
      flashBanner('No tour defined for this page yet — but Help mode highlights are on.');
      return;
    }
    tourState.index = 0;
    tourState.active = true;
    renderStep();
  }
  function closeTour() {
    tourState.active = false;
    if (tour) tour.hidden = true;
    if (spotlight) spotlight.hidden = true;
  }
  function next() {
    if (tourState.index < tourState.steps.length - 1) {
      tourState.index++;
      renderStep();
    } else {
      closeTour();
    }
  }
  function prev() {
    if (tourState.index > 0) {
      tourState.index--;
      renderStep();
    }
  }

  /* ── Tiny in-banner flash ─────────────────────────────────── */
  function flashBanner(msg) {
    if (!banner) return;
    var txt = banner.querySelector('.psp-help-banner-text');
    if (!txt) return;
    var original = txt.innerHTML;
    txt.innerHTML = '<strong>' + msg + '</strong>';
    setTimeout(function () { txt.innerHTML = original; }, 2400);
  }

  /* ── Wire up event listeners ──────────────────────────────── */
  /* Toggle buttons (in topbar, help drawer, banner X) */
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-psp-help-mode-toggle]');
    if (t) { e.preventDefault(); setOn(!isOn()); return; }

    var s = e.target.closest && e.target.closest('[data-psp-walkthrough-start]');
    if (s) {
      e.preventDefault();
      if (!isOn()) setOn(true);
      /* Close help drawer if open */
      var drawer = document.getElementById('pspHelpDrawer');
      if (drawer && window.bootstrap && bootstrap.Offcanvas) {
        var inst = bootstrap.Offcanvas.getInstance(drawer);
        if (inst) inst.hide();
      }
      setTimeout(startTour, 320);
      return;
    }
  });

  /* Walkthrough buttons */
  var pBtn = document.getElementById('pspWalkthroughPrev');
  var nBtn = document.getElementById('pspWalkthroughNext');
  var dBtn = document.getElementById('pspWalkthroughDone');
  var xBtn = document.getElementById('pspWalkthroughClose');
  if (pBtn) pBtn.addEventListener('click', prev);
  if (nBtn) nBtn.addEventListener('click', next);
  if (dBtn) dBtn.addEventListener('click', closeTour);
  if (xBtn) xBtn.addEventListener('click', closeTour);

  /* Keyboard: ? toggles help mode, arrows step through tour, Esc closes */
  document.addEventListener('keydown', function (e) {
    var typing =
      e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
                   e.target.tagName === 'SELECT' || e.target.isContentEditable);
    if (e.key === 'Escape' && tourState.active) { closeTour(); return; }
    if (typing) return;
    if (e.key === '?') { e.preventDefault(); setOn(!isOn()); return; }
    if (!tourState.active) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
    if (e.key === 'ArrowLeft')  { e.preventDefault(); prev(); }
  });

  /* Reposition on scroll / resize while tour active */
  function reposition() {
    if (!tourState.active) return;
    var step = tourState.steps[tourState.index];
    if (!step) return;
    var t = document.querySelector(step.selector);
    if (t) positionTourFor(t);
  }
  window.addEventListener('scroll',  reposition, { passive: true });
  window.addEventListener('resize',  reposition);

  /* Re-apply highlights / labels if user_app_settings change toggling */
  /* (Not needed for this build — settings change requires a page reload.) */

  /* ── Boot ─────────────────────────────────────────────────── */
  setOn(isOn());

}());
