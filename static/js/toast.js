(function () {
  'use strict';
  var DEFAULT_TIMEOUT = 5000; // ms
  var container = document.getElementById('pspToasts');
  if (!container) return;

  var seen = new Set();

  function createToast(type, html, timeout) {
    timeout = typeof timeout === 'number' ? timeout : DEFAULT_TIMEOUT;

    // Deduplicate by text+type
    var key = type + '::' + html;
    if (seen.has(key)) return null;
    seen.add(key);

    var toast = document.createElement('div');
    toast.className = 'psp-toast psp-toast--' + (type || 'info');
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-atomic', 'true');

    var body = document.createElement('div');
    body.className = 'psp-toast-body';

    var icon = document.createElement('div');
    icon.className = 'psp-toast-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = (type === 'success') ? '<i class="bi bi-check-circle-fill" style="color:#10b981"></i>' :
                     (type === 'danger' || type === 'error') ? '<i class="bi bi-x-circle-fill" style="color:#dc2626"></i>' :
                     (type === 'warning') ? '<i class="bi bi-exclamation-triangle-fill" style="color:#f59e0b"></i>' :
                     '<i class="bi bi-info-circle-fill" style="color:#3b82f6"></i>';

    var text = document.createElement('div');
    text.className = 'psp-toast-text';
    text.innerHTML = html;

    var closeBtn = document.createElement('button');
    closeBtn.className = 'psp-toast-close';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.innerHTML = '<i class="bi bi-x-lg"></i>';

    body.appendChild(icon);
    body.appendChild(text);
    body.appendChild(closeBtn);

    var progressWrap = document.createElement('div');
    progressWrap.className = 'psp-toast-progress';
    var progressBar = document.createElement('span');
    progressBar.style.width = '100%';
    progressWrap.appendChild(progressBar);

    toast.appendChild(body);
    toast.appendChild(progressWrap);

    // Insert at top
    if (container.firstChild) container.insertBefore(toast, container.firstChild);
    else container.appendChild(toast);

    // Animate in
    requestAnimationFrame(function () { toast.classList.add('psp-toast--show'); });

    var start = null;
    var remaining = timeout;
    var rafId = null;
    var lastTick = null;
    var paused = false;

    function step(ts) {
      if (paused) { lastTick = ts; rafId = requestAnimationFrame(step); return; }
      if (!start) { start = ts; lastTick = ts; }
      var elapsed = ts - start;
      var pct = Math.max(0, Math.min(1, 1 - (elapsed / timeout)));
      progressBar.style.width = (pct * 100) + '%';
      if (elapsed >= timeout) {
        dismiss();
        return;
      }
      rafId = requestAnimationFrame(step);
    }

    function dismiss() {
      if (rafId) cancelAnimationFrame(rafId);
      toast.classList.remove('psp-toast--show');
      toast.classList.add('psp-toast--hide');
      // small delay to allow transition
      setTimeout(function () { try { container.removeChild(toast); } catch (e) {} }, 260);
    }

    closeBtn.addEventListener('click', function (e) { e.preventDefault(); dismiss(); });

    toast.addEventListener('mouseenter', function () { paused = true; });
    toast.addEventListener('mouseleave', function () { paused = false; });

    // Start animation
    rafId = requestAnimationFrame(step);

    // Return handle
    return {
      el: toast,
      dismiss: dismiss
    };
  }

  // Public helper
  window.PSP_toast = function (type, message, timeout) {
    return createToast(type, message, timeout);
  };

  // Parse server-rendered message data
  document.addEventListener('DOMContentLoaded', function () {
    var data = document.getElementById('pspMessageData');
    if (!data) return;
    var items = Array.prototype.slice.call(data.querySelectorAll('.psp-message'));
    items.forEach(function (it) {
      var level = (it.getAttribute('data-level') || 'info').toLowerCase();
      var msg = it.innerHTML || it.textContent || '';
      // Normalize "danger"/"error"
      if (level === 'danger') level = 'danger';
      if (level === 'error') level = 'danger';
      if (level === 'success') level = 'success';
      if (level === 'warning') level = 'warning';
      if (level === 'info' || !level) level = 'info';
      createToast(level, msg, undefined);
    });

    // Remove the data node so messages aren't re-used
    try { data.parentNode && data.parentNode.removeChild(data); } catch (e) {}
  });

})();
