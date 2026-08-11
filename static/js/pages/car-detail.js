/**
 * Vehicle detail page
 */

import { api, debounce } from '../core/api.js';

const ICON_CHECK =
  '<path d="M20 6 9 17l-5-5"/>';
const ICON_CROSS =
  '<circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>';
const ICON_SPIN =
  '<path d="M21 12a9 9 0 1 1-6.2-8.6"/>';
const ICON_INFO =
  '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>';

function initGallery() {
  const main = document.querySelector('[data-gallery-main]');
  if (!main) return;

  document.querySelectorAll('[data-gallery-thumb]').forEach((thumb) => {
    thumb.addEventListener('click', () => {
      const src = thumb.dataset.galleryThumb;
      if (!src || main.src.endsWith(src)) return;

      main.style.opacity = '0';
      const swap = () => {
        main.src = src;
        main.style.opacity = '1';
      };
      setTimeout(swap, 120);

      document.querySelectorAll('[data-gallery-thumb]').forEach((t) => {
        t.setAttribute('aria-current', String(t === thumb));
      });
    });
  });
}

function initQuote() {
  const panel = document.querySelector('[data-booking-panel]');
  if (!panel) return;

  const carId = Number(panel.dataset.carId);
  const endpoint = panel.dataset.quoteEndpoint;
  const currency = panel.dataset.currency || '€';

  const start = panel.querySelector('[data-date-start]');
  const end = panel.querySelector('[data-date-end]');
  const status = panel.querySelector('[data-availability]');
  const submit = panel.querySelector('[data-book-submit]');

  const out = {
    days: panel.querySelector('[data-out-days]'),
    base: panel.querySelector('[data-out-base]'),
    extras: panel.querySelector('[data-out-extras]'),
    extrasRow: panel.querySelector('[data-out-extras-row]'),
    total: panel.querySelector('[data-out-total]'),
    rate: panel.querySelector('[data-out-rate]'),
  };

  let controller;

  const setStatus = (state, message, icon) => {
    if (!status) return;
    status.dataset.state = state;
    status.querySelector('[data-availability-text]').textContent = message;
    const svg = status.querySelector('svg');
    if (svg && icon) svg.innerHTML = icon;
  };

  const money = (value) =>
    `${currency}${Number(value).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;

  const selectedExtras = () =>
    [...panel.querySelectorAll('[data-extra]:checked')].map((box) => box.value);

  const resetTotals = () => {
    if (out.days) out.days.textContent = '0';
    if (out.base) out.base.textContent = money(0);
    if (out.total) out.total.textContent = money(0);
    if (out.extrasRow) out.extrasRow.hidden = true;
  };

  const refresh = async () => {
    if (!start?.value || !end?.value) {
      resetTotals();
      setStatus('idle', panel.dataset.msgIdle || 'Choose your dates', ICON_INFO);
      if (submit) submit.disabled = true;
      return;
    }

    setStatus('checking', panel.dataset.msgChecking || 'Checking availability…', ICON_SPIN);

    controller?.abort();
    controller = new AbortController();

    try {
      const data = await api.post(
        endpoint,
        {
          car_id: carId,
          start_date: start.value,
          end_date: end.value,
          extras: selectedExtras(),
        },
        { signal: controller.signal }
      );

      if (!data.ok) {
        resetTotals();
        setStatus('error', data.error, ICON_INFO);
        if (submit) submit.disabled = true;
        return;
      }

      const q = data.quote;
      if (out.days) out.days.textContent = q.days;
      if (out.base) out.base.textContent = money(q.base_total);
      if (out.total) out.total.textContent = money(q.total);
      if (out.rate) out.rate.textContent = money(q.price_per_day);

      const extrasTotal = Number(q.extras_total);
      if (out.extrasRow) out.extrasRow.hidden = extrasTotal <= 0;
      if (out.extras) out.extras.textContent = money(extrasTotal);

      if (data.available) {
        setStatus('available', data.message, ICON_CHECK);
        if (submit) submit.disabled = false;
      } else {
        setStatus('unavailable', data.message, ICON_CROSS);
        if (submit) submit.disabled = true;
      }
    } catch (error) {
      if (error.name === 'AbortError') return;
      setStatus(
        'error',
        panel.dataset.msgError || 'Could not check availability. Try again.',
        ICON_INFO
      );
      if (submit) submit.disabled = false;
    }
  };

  const debouncedRefresh = debounce(refresh, 220);

  panel.addEventListener('range:change', debouncedRefresh);
  start?.addEventListener('change', debouncedRefresh);
  end?.addEventListener('change', debouncedRefresh);
  panel.querySelectorAll('[data-extra]').forEach((box) =>
    box.addEventListener('change', debouncedRefresh)
  );

  refresh();
}

export function initCarDetail() {
  initGallery();
  initQuote();
}
