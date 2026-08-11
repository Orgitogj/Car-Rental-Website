/**
 * Live filtering for the vehicle search page.
 *
 * Progressive enhancement: the form works as a plain GET submit without any of
 * this. When JS is available, changes fetch just the results grid and update
 * the URL so the page stays shareable and the back button keeps working.
 */

import { debounce, fetchFragment } from '../core/api.js';

export function initSearchFilters() {
  const form = document.querySelector('[data-filter-form]');
  const region = document.querySelector('[data-results-region]');
  if (!form || !region) return;

  const progress = document.querySelector('.route-progress');
  let controller;

  const setBusy = (busy) => {
    region.dataset.loadingRegion = String(busy);
    region.setAttribute('aria-busy', String(busy));
    if (!progress) return;
    progress.classList.toggle('is-active', busy);
    progress.style.width = busy ? '72%' : '100%';
    if (!busy) setTimeout(() => { progress.style.width = '0'; }, 260);
  };

  async function apply({ push = true } = {}) {
    const params = new URLSearchParams(new FormData(form));

    // Drop empty values so the URL stays readable.
    [...params.entries()].forEach(([key, value]) => {
      if (value === '' || value == null) params.delete(key);
    });

    const url = `${form.action || window.location.pathname}?${params}`;

    controller?.abort();
    controller = new AbortController();
    setBusy(true);

    try {
      const html = await fetchFragment(url, { signal: controller.signal });
      region.innerHTML = html;
      if (push) window.history.pushState({ url }, '', url);
      region.querySelectorAll('.car-card').forEach((card, i) => {
        card.style.setProperty('--i', i);
      });
    } catch (error) {
      if (error.name !== 'AbortError') {
        // Fall back to a full navigation rather than leaving stale results.
        window.location.href = url;
      }
    } finally {
      setBusy(false);
    }
  }

  const debouncedApply = debounce(() => apply(), 300);

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    apply();
  });

  form.addEventListener('change', (event) => {
    if (event.target.matches('input[type="text"], input[type="search"]')) return;
    apply();
  });

  form.addEventListener('input', (event) => {
    if (event.target.matches('input[type="text"], input[type="search"], input[type="number"]')) {
      debouncedApply();
    }
  });

  // Sort control lives outside the filter form.
  document.querySelector('[data-sort-select]')?.addEventListener('change', (event) => {
    let hidden = form.querySelector('input[name="sort"]');
    if (!hidden) {
      hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'sort';
      form.appendChild(hidden);
    }
    hidden.value = event.target.value;
    apply();
  });

  document.querySelector('[data-filter-reset]')?.addEventListener('click', (event) => {
    event.preventDefault();
    form.reset();
    form.querySelectorAll('input[type="hidden"][name="sort"]').forEach((i) => i.remove());
    apply();
  });

  window.addEventListener('popstate', () => {
    window.location.reload();
  });

  // Mobile bottom sheet
  const panel = document.querySelector('.filters');
  document.querySelector('[data-filters-open]')?.addEventListener('click', () => {
    panel?.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  });

  const closeSheet = () => {
    panel?.classList.remove('is-open');
    document.body.style.overflow = '';
  };

  document.querySelectorAll('[data-filters-close]').forEach((btn) =>
    btn.addEventListener('click', closeSheet)
  );

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeSheet();
  });
}

/**
 * Keeps a date range honest: the return date can never precede the pick-up
 * date plus the minimum rental period.
 */
export function initDateRange(root = document) {
  root.querySelectorAll('[data-date-range]').forEach((group) => {
    const start = group.querySelector('[data-date-start]');
    const end = group.querySelector('[data-date-end]');
    if (!start || !end) return;

    const minDays = Number(group.dataset.minDays || 1);
    const today = new Date().toISOString().split('T')[0];

    start.min = today;
    if (!end.min) end.min = today;

    const syncEnd = () => {
      if (!start.value) return;
      const earliest = new Date(`${start.value}T00:00:00`);
      earliest.setDate(earliest.getDate() + minDays);
      const iso = earliest.toISOString().split('T')[0];
      end.min = iso;
      if (end.value && end.value < iso) end.value = iso;
    };

    start.addEventListener('change', () => {
      syncEnd();
      group.dispatchEvent(new CustomEvent('range:change', { bubbles: true }));
    });

    end.addEventListener('change', () => {
      group.dispatchEvent(new CustomEvent('range:change', { bubbles: true }));
    });

    syncEnd();
  });
}
