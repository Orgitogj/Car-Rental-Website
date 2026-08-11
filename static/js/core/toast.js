/**
 * Toast notifications.
 */

const ICONS = {
  success:
    '<path d="M20 6 9 17l-5-5"/>',
  danger:
    '<circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>',
  warning:
    '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
};

let region;

function ensureRegion() {
  if (region) return region;
  region = document.querySelector('.toast-region');
  if (!region) {
    region = document.createElement('div');
    region.className = 'toast-region';
    region.setAttribute('role', 'status');
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'false');
    document.body.appendChild(region);
  }
  return region;
}

export function toast(message, { title = '', tone = 'info', duration = 5000 } = {}) {
  const host = ensureRegion();

  const el = document.createElement('div');
  el.className = `toast toast--${tone}`;

  el.innerHTML = `
    <svg class="toast__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      ${ICONS[tone] || ICONS.info}
    </svg>
    <div class="toast__body">
      ${title ? `<div class="toast__title"></div>` : ''}
      <div class="toast__text"></div>
    </div>
    <button type="button" class="toast__close" aria-label="Dismiss">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"
           stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
    </button>`;

  // Assign as text so message content can never inject markup.
  if (title) el.querySelector('.toast__title').textContent = title;
  el.querySelector('.toast__text').textContent = message;

  const dismiss = () => {
    if (!el.isConnected) return;
    el.classList.add('is-leaving');
    el.addEventListener('animationend', () => el.remove(), { once: true });
    // Belt and braces if the animation is suppressed.
    setTimeout(() => el.remove(), 600);
  };

  el.querySelector('.toast__close').addEventListener('click', dismiss);
  host.appendChild(el);

  if (duration > 0) {
    const timer = setTimeout(dismiss, duration);
    el.addEventListener('mouseenter', () => clearTimeout(timer));
  }

  return dismiss;
}

toast.success = (msg, opts) => toast(msg, { ...opts, tone: 'success' });
toast.error = (msg, opts) => toast(msg, { ...opts, tone: 'danger' });
toast.warning = (msg, opts) => toast(msg, { ...opts, tone: 'warning' });
