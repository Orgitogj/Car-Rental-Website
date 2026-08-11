

import { api, debounce } from '../core/api.js';

export function initPalette() {
  const palette = document.getElementById('command-palette');
  if (!palette) return;

  const input = palette.querySelector('[data-palette-input]');
  const results = palette.querySelector('[data-palette-results]');
  const endpoint = palette.dataset.endpoint;
  let cursor = -1;
  let items = [];
  let controller;

  const open = () => {
    palette.hidden = false;
    document.body.style.overflow = 'hidden';
    input.value = '';
    renderMessage('Start typing to search companies, vehicles, bookings and customers.');
    input.focus();
  };

  const close = () => {
    palette.hidden = true;
    document.body.style.overflow = '';
    controller?.abort();
  };

  function renderMessage(text) {
    items = [];
    cursor = -1;
    results.innerHTML = '';
    const p = document.createElement('p');
    p.className = 'muted small';
    p.style.padding = 'var(--space-4)';
    p.textContent = text;
    results.appendChild(p);
  }

  function render(rows) {
    results.innerHTML = '';
    items = rows;
    cursor = rows.length ? 0 : -1;

    if (!rows.length) {
      renderMessage('No matches.');
      return;
    }

    rows.forEach((row, index) => {
      const link = document.createElement('a');
      link.className = 'palette__item';
      link.href = row.url;
      link.setAttribute('aria-selected', String(index === 0));

      const type = document.createElement('span');
      type.className = 'palette__item-type';
      type.textContent = row.type;

      const label = document.createElement('span');
      label.className = 'palette__item-label';
      label.textContent = row.label;

      const meta = document.createElement('span');
      meta.className = 'palette__item-meta';
      meta.textContent = row.meta || '';

      link.append(type, label, meta);
      results.appendChild(link);
    });
  }

  const search = debounce(async (term) => {
    if (term.trim().length < 2) {
      renderMessage('Keep typing…');
      return;
    }

    controller?.abort();
    controller = new AbortController();

    try {
      const data = await api.get(
        `${endpoint}?q=${encodeURIComponent(term)}`,
        { signal: controller.signal }
      );
      render(data.results || []);
    } catch (error) {
      if (error.name !== 'AbortError') renderMessage('Search is unavailable right now.');
    }
  }, 180);

  input.addEventListener('input', () => search(input.value));

  palette.querySelector('.modal__backdrop')?.addEventListener('click', close);

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      close();
      return;
    }
    if (!items.length) return;

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      cursor =
        event.key === 'ArrowDown'
          ? (cursor + 1) % items.length
          : (cursor - 1 + items.length) % items.length;

      [...results.children].forEach((node, index) => {
        node.setAttribute('aria-selected', String(index === cursor));
        if (index === cursor) node.scrollIntoView({ block: 'nearest' });
      });
    }

    if (event.key === 'Enter' && cursor >= 0) {
      event.preventDefault();
      window.location.href = items[cursor].url;
    }
  });

  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      palette.hidden ? open() : close();
    }
  });

  document.querySelectorAll('[data-palette-open]').forEach((button) => {
    button.addEventListener('click', open);
  });
}
