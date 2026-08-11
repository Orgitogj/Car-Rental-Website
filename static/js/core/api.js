/**
 * Fetch helpers.
 */

export function getCookie(name) {
  const match = document.cookie.match(
    new RegExp('(^|;\\s*)' + name.replace(/([.*+?^${}()|[\]\\])/g, '\\$1') + '=([^;]*)')
  );
  return match ? decodeURIComponent(match[2]) : null;
}

export function csrfToken() {
  return (
    getCookie('csrftoken') ||
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    ''
  );
}

class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

export { ApiError };

async function request(url, { method = 'GET', body, signal, headers = {} } = {}) {
  const init = {
    method,
    signal,
    credentials: 'same-origin',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      Accept: 'application/json',
      ...headers,
    },
  };

  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  if (method !== 'GET' && method !== 'HEAD') {
    init.headers['X-CSRFToken'] = csrfToken();
  }

  const response = await fetch(url, init);

  let payload = null;
  const type = response.headers.get('Content-Type') || '';
  if (type.includes('application/json')) {
    payload = await response.json().catch(() => null);
  }

  if (!response.ok) {
    throw new ApiError(
      payload?.error || `Request failed (${response.status})`,
      response.status,
      payload
    );
  }

  return payload;
}

export const api = {
  get: (url, options) => request(url, { ...options, method: 'GET' }),
  post: (url, body, options) => request(url, { ...options, method: 'POST', body }),
};

/** Fetch an HTML fragment (used for live-updating result grids). */
export async function fetchFragment(url, { signal, partial = 'results' } = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    signal,
    headers: { 'X-Partial': partial, 'X-Requested-With': 'XMLHttpRequest' },
  });
  if (!response.ok) throw new ApiError('Could not load results', response.status);
  return response.text();
}

/** Trailing-edge debounce. */
export function debounce(fn, wait = 250) {
  let timer;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
  wrapped.cancel = () => clearTimeout(timer);
  return wrapped;
}

/** Format a number as currency using the symbol the server rendered. */
export function formatMoney(value, symbol) {
  const amount = Number(value || 0);
  const currency = symbol || document.documentElement.dataset.currency || '€';
  return `${currency}${amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
