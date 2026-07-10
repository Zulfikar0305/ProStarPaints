/* ProStar Paints — Sidebar Collapse Controller (sidebar.js)
   Priority 1: Desktop icon-rail collapse with localStorage persistence.
   Mobile/tablet off-canvas is handled by the inline script in base.html.
   Keyboard shortcut: [ (left bracket) toggles the sidebar.
*/
(function () {
  'use strict';

  var STORAGE_KEY = 'psp_sidebar_collapsed';
  var BREAKPOINT  = 992;

  var body       = document.body;
  var sidebar    = document.getElementById('pspSidebar');
  var collapseBtn = document.getElementById('pspSidebarCollapseBtn');

  if (!sidebar || !collapseBtn) return;

  /* ── Tooltip helpers ───────────────────────────────────────── */
  function addTooltips() {
    if (!window.bootstrap || !bootstrap.Tooltip) return;
    sidebar.querySelectorAll('.psp-sidebar-link').forEach(function (link) {
      var spanEl = link.querySelector('span');
      var label  = spanEl ? spanEl.textContent.trim() : '';
      if (!label) return;
      var existing = bootstrap.Tooltip.getInstance(link);
      if (existing) existing.dispose();
      link.setAttribute('title', label);
      try { new bootstrap.Tooltip(link, { container: 'body', placement: 'right', trigger: 'hover focus' }); } catch (e) {}
    });
  }

  function removeTooltips() {
    if (!window.bootstrap || !bootstrap.Tooltip) return;
    sidebar.querySelectorAll('.psp-sidebar-link').forEach(function (link) {
      var existing = bootstrap.Tooltip.getInstance(link);
      if (existing) existing.dispose();
      link.removeAttribute('title');
    });
  }

  /* ── State management ──────────────────────────────────────── */
  function isCollapsed() {
    return localStorage.getItem(STORAGE_KEY) === '1';
  }

  function applyState(collapsed) {
    if (collapsed) {
      body.setAttribute('data-sidebar-collapsed', '');
      localStorage.setItem(STORAGE_KEY, '1');
      addTooltips();
    } else {
      body.removeAttribute('data-sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, '0');
      removeTooltips();
    }
  }

  function toggle() {
    if (window.innerWidth < BREAKPOINT) return;
    applyState(!isCollapsed());
  }

  /* ── Toggle button ─────────────────────────────────────────── */
  collapseBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    toggle();
  });

  /* ── Keyboard shortcut: [ key ──────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    if (window.innerWidth < BREAKPOINT) return;
    var tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === '[') {
      e.preventDefault();
      toggle();
    }
  });

  /* ── On resize: restore or clear ──────────────────────────── */
  var resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (window.innerWidth < BREAKPOINT) {
        body.removeAttribute('data-sidebar-collapsed');
        removeTooltips();
      } else if (isCollapsed()) {
        body.setAttribute('data-sidebar-collapsed', '');
        addTooltips();
      }
    }, 120);
  });

  /* ── Init on load ──────────────────────────────────────────── */
  if (window.innerWidth >= BREAKPOINT && isCollapsed()) {
    body.setAttribute('data-sidebar-collapsed', '');
    /* Tooltips will be added after Bootstrap initialises (after DOMContentLoaded) */
    document.addEventListener('DOMContentLoaded', function () {
      if (body.hasAttribute('data-sidebar-collapsed')) addTooltips();
    });
  }

}());
