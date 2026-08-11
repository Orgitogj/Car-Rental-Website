/**
 * Restricted actions.
 *
 * In the platform administrator's read-only drill-in, mutating controls are
 * still rendered so the action stays discoverable — they simply do nothing.
 * The click is swallowed here and explained with a toast.
 *
 * This is affordance, never enforcement: the same mutation is refused by
 * `company_manage_required` and again by the service layer, so stripping the
 * attribute in DevTools buys nothing but a 403.
 */

import { toast } from '../core/toast.js';

const FALLBACK = 'This action is not available from the SuperAdmin site.';

let bound = false;

function block(event) {
  const el = event.target.closest('[data-restricted]');
  if (!el) return;

  event.preventDefault();
  // Listening in the capture phase and stopping here means handlers bound
  // directly to the control — confirm dialogs, dropdown toggles, modal
  // openers, submit states — never run.
  event.stopPropagation();
  event.stopImmediatePropagation();

  toast(el.dataset.restricted || FALLBACK, { tone: 'warning' });
}

export function initRestrictedActions() {
  if (bound) return;
  bound = true;

  document.addEventListener('click', block, true);
  document.addEventListener('submit', block, true);
}
