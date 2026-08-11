/**
 * Dropdowns, modals and confirm-dialogs.
 */

const focusableSelector =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/* -- Dropdowns ------------------------------------------------------------ */

function closeAllDropdowns(except) {
  document.querySelectorAll('.dropdown__menu:not([hidden])').forEach((menu) => {
    if (menu === except) return;
    menu.hidden = true;
    const trigger = document.querySelector(`[data-dropdown="${menu.id}"]`);
    trigger?.setAttribute('aria-expanded', 'false');
  });
}

export function initDropdowns(root = document) {
  root.querySelectorAll('[data-dropdown]').forEach((trigger) => {
    if (trigger.dataset.bound) return;
    trigger.dataset.bound = '1';

    const menu = document.getElementById(trigger.dataset.dropdown);
    if (!menu) return;

    trigger.setAttribute('aria-haspopup', 'true');
    trigger.setAttribute('aria-expanded', 'false');

    trigger.addEventListener('click', (event) => {
      event.stopPropagation();
      const willOpen = menu.hidden;
      closeAllDropdowns(menu);
      menu.hidden = !willOpen;
      trigger.setAttribute('aria-expanded', String(willOpen));
      if (willOpen) menu.querySelector(focusableSelector)?.focus();
    });

    menu.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        menu.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        trigger.focus();
      }
    });
  });
}

document.addEventListener('click', (event) => {
  if (!event.target.closest('.dropdown')) closeAllDropdowns();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeAllDropdowns();
});

/* -- Modals --------------------------------------------------------------- */

let lastFocused = null;

export function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;

  lastFocused = document.activeElement;
  modal.hidden = false;
  document.body.style.overflow = 'hidden';

  const panel = modal.querySelector('.modal__panel');
  panel?.setAttribute('role', 'dialog');
  panel?.setAttribute('aria-modal', 'true');

  (panel?.querySelector('[data-autofocus]') ||
    panel?.querySelector(focusableSelector))?.focus();
}

export function closeModal(modal) {
  const el = typeof modal === 'string' ? document.getElementById(modal) : modal;
  if (!el || el.hidden) return;

  el.hidden = true;
  document.body.style.overflow = '';
  lastFocused?.focus();
}

function trapFocus(event) {
  const modal = document.querySelector('.modal:not([hidden])');
  if (!modal || event.key !== 'Tab') return;

  const items = [...modal.querySelectorAll(focusableSelector)].filter(
    (el) => el.offsetParent !== null
  );
  if (!items.length) return;

  const first = items[0];
  const last = items[items.length - 1];

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

export function initModals(root = document) {
  root.querySelectorAll('[data-modal-open]').forEach((trigger) => {
    if (trigger.dataset.bound) return;
    trigger.dataset.bound = '1';
    trigger.addEventListener('click', () => openModal(trigger.dataset.modalOpen));
  });

  root.querySelectorAll('[data-modal-close]').forEach((trigger) => {
    if (trigger.dataset.bound) return;
    trigger.dataset.bound = '1';
    trigger.addEventListener('click', () => closeModal(trigger.closest('.modal')));
  });

  root.querySelectorAll('.modal__backdrop').forEach((backdrop) => {
    if (backdrop.dataset.bound) return;
    backdrop.dataset.bound = '1';
    backdrop.addEventListener('click', () => closeModal(backdrop.closest('.modal')));
  });
}

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeModal(document.querySelector('.modal:not([hidden])'));
  trapFocus(event);
});

/* -- Confirm before submit ------------------------------------------------ */

export function initConfirms(root = document) {
  root.querySelectorAll('[data-confirm]').forEach((el) => {
    if (el.dataset.bound) return;
    el.dataset.bound = '1';

    const handler = (event) => {
      if (el.dataset.confirmed === '1') return;
      event.preventDefault();
      // eslint-disable-next-line no-alert
      if (window.confirm(el.dataset.confirm)) {
        el.dataset.confirmed = '1';
        if (el.tagName === 'FORM') el.submit();
        else el.click();
      }
    };

    el.addEventListener(el.tagName === 'FORM' ? 'submit' : 'click', handler);
  });
}

/* -- Submit button loading state ------------------------------------------ */

export function initSubmitStates(root = document) {
  root.querySelectorAll('form[data-loading-form]').forEach((form) => {
    if (form.dataset.bound) return;
    form.dataset.bound = '1';

    form.addEventListener('submit', () => {
      if (!form.checkValidity()) return;
      const button = form.querySelector('[type="submit"]');
      if (button) {
        button.dataset.loading = 'true';
        button.disabled = true;
      }
    });
  });
}
