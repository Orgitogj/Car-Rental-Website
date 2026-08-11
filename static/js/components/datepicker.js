
import { api } from '../core/api.js';

const DAY_MS = 86400000;

const iso = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
    date.getDate()
  ).padStart(2, '0')}`;

const fromIso = (value) => {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
};

const addDays = (date, count) => new Date(date.getTime() + count * DAY_MS);

const startOfMonth = (date) => new Date(date.getFullYear(), date.getMonth(), 1);

const addMonths = (date, count) =>
  new Date(date.getFullYear(), date.getMonth() + count, 1);

/** Monday-first weekday index. */
const weekdayIndex = (date) => (date.getDay() + 6) % 7;

function monthLabel(date, locale) {
  return date.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
}

function weekdayNames(locale) {
  // 2024-01-01 was a Monday, so this walks Mon→Sun in the page's language.
  return Array.from({ length: 7 }, (_, i) =>
    new Date(2024, 0, 1 + i).toLocaleDateString(locale, { weekday: 'short' })
  );
}

function detachNativePicker(input) {
  const hidden = document.createElement('input');
  hidden.type = 'hidden';
  hidden.name = input.name;
  hidden.value = input.value;

  ['dateStart', 'dateEnd'].forEach((hook) => {
    if (hook in input.dataset) {
      hidden.dataset[hook] = input.dataset[hook];
      delete input.dataset[hook];
    }
  });

  input.after(hidden);
  input.type = 'text';
  input.removeAttribute('name');
  input.readOnly = true;
  input.autocomplete = 'off';
  input.dataset.dateDisplay = '';

  // It behaves as a button onto the calendar panel now, so say so — and give
  // the stylesheet a hook for the open state.
  input.setAttribute('aria-haspopup', 'dialog');
  input.setAttribute('aria-expanded', 'false');

  return hidden;
}

function buildCalendar(root) {
  const startField = root.querySelector('[data-date-start]');
  const endField = root.querySelector('[data-date-end]');
  const endpoint = root.dataset.availabilityEndpoint;
  if (!startField || !endField || !endpoint) return;

  const startInput = detachNativePicker(startField);
  const endInput = detachNativePicker(endField);

  const locale = document.documentElement.lang || undefined;
  const labels = {
    unavailable: root.dataset.msgUnavailable || 'Already booked',
    checkout: root.dataset.msgCheckout || 'Return only',
    selected: root.dataset.msgSelected || 'Selected',
    prev: root.dataset.msgPrev || 'Previous month',
    next: root.dataset.msgNext || 'Next month',
    hint: root.dataset.msgHint || 'Select your pick-up date',
    hintEnd: root.dataset.msgHintEnd || 'Now choose your return date',
    invalid: root.dataset.msgInvalid || 'Not possible with these dates',
  };

  let blocked = new Set();
  let blockedSorted = [];
  let minDays = Number(root.dataset.minDays || 1);
  let todayIso = iso(new Date());

  let start = startInput.value || null;
  let end = endInput.value || null;
  let picking = 'start';
  let hovered = null;
  let view = startOfMonth(start ? fromIso(start) : new Date());
  // Roving tabindex: exactly one day is in the tab order at a time, and the
  // arrow keys move it. 61 individually tabbable cells would be unusable.
  let focusDay = start || todayIso;
  const panel = document.createElement('div');
  panel.className = 'datepicker';
  panel.hidden = true;
  panel.innerHTML = `
    <div class="datepicker__head">
      <button type="button" class="datepicker__nav" data-cal-prev aria-label="${labels.prev}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6"/>
        </svg>
      </button>
      <p class="datepicker__hint" data-cal-hint>${labels.hint}</p>
      <button type="button" class="datepicker__nav" data-cal-next aria-label="${labels.next}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M9 18l6-6-6-6"/>
        </svg>
      </button>
    </div>
    <div class="datepicker__months" data-cal-months></div>
    <div class="datepicker__legend">
      <span class="datepicker__key"><i data-key="open"></i>${
        root.dataset.msgOpen || 'Available'
      }</span>
      <span class="datepicker__key"><i data-key="blocked"></i>${labels.unavailable}</span>
      <span class="datepicker__key"><i data-key="range"></i>${labels.selected}</span>
    </div>`;

  const datePair = root.querySelector('.date-pair') || startInput.parentElement;
  datePair.insertAdjacentElement('afterend', panel);

  const months = panel.querySelector('[data-cal-months]');
  const hint = panel.querySelector('[data-cal-hint]');
  const firstBlockedAfter = (day) => blockedSorted.find((d) => d > day) || null;

  const minEndFor = (day) => iso(addDays(fromIso(day), minDays));
  function dayState(day) {
    if (day < todayIso) return 'past';

    if (picking === 'end' && start) {
      if (day === start) return 'start';
      if (day < start) return 'disabled';

      const cap = firstBlockedAfter(start);
      if (cap && day > cap) return 'disabled'; // would jump over a booking
      if (day < minEndFor(start)) return 'disabled'; // under the minimum stay
      if (blocked.has(day)) return day === cap ? 'checkout' : 'disabled';
      return 'open';
    }

    return blocked.has(day) ? 'blocked' : 'open';
  }

  const isPickable = (state) =>
    state === 'open' || state === 'checkout' || state === 'start';

  function inRange(day) {
    const to = end || (picking === 'end' ? hovered : null);
    if (!start || !to) return false;
    return day > start && day < to;
  }

  function renderMonth(monthStart) {
    const names = weekdayNames(locale);
    const first = weekdayIndex(monthStart);
    const total = new Date(
      monthStart.getFullYear(),
      monthStart.getMonth() + 1,
      0
    ).getDate();

    const cells = [];
    for (let i = 0; i < first; i += 1) {
      cells.push('<span class="datepicker__pad"></span>');
    }

    for (let dayNum = 1; dayNum <= total; dayNum += 1) {
      const date = new Date(monthStart.getFullYear(), monthStart.getMonth(), dayNum);
      const day = iso(date);
      const state = dayState(day);
      const selected = day === start || day === end;
      const title =
        state === 'blocked'
          ? labels.unavailable
          : state === 'disabled'
            ? labels.invalid
            : state === 'checkout'
              ? labels.checkout
              : '';

      cells.push(
        `<button type="button" class="datepicker__day" data-day="${day}"` +
          ` data-state="${state}"` +
          `${selected ? ' data-selected="true"' : ''}` +
          `${inRange(day) ? ' data-in-range="true"' : ''}` +
          `${isPickable(state) ? '' : ' aria-disabled="true"'}` +
          `${title ? ` title="${title}"` : ''}` +
          ` aria-label="${fromIso(day).toLocaleDateString(locale, {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          })}${title ? `, ${title}` : ''}"` +
          ` tabindex="${day === focusDay ? '0' : '-1'}">${dayNum}</button>`
      );
    }

    return `
      <div class="datepicker__month">
        <p class="datepicker__month-name">${monthLabel(monthStart, locale)}</p>
        <div class="datepicker__weekdays">
          ${names.map((n) => `<span>${n}</span>`).join('')}
        </div>
        <div class="datepicker__grid">${cells.join('')}</div>
      </div>`;
  }

  function render() {
    months.innerHTML = renderMonth(view) + renderMonth(addMonths(view, 1));
    hint.textContent = picking === 'end' && start ? labels.hintEnd : labels.hint;

    const floor = startOfMonth(new Date());
    panel.querySelector('[data-cal-prev]').disabled = view <= floor;
  }

  function paintRange() {
    months.querySelectorAll('[data-day]').forEach((cell) => {
      if (inRange(cell.dataset.day)) cell.dataset.inRange = 'true';
      else delete cell.dataset.inRange;
    });
  }

  
  const display = (value) =>
    value
      ? fromIso(value).toLocaleDateString(locale, {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
        })
      : '';

  function commit() {
    startInput.value = start || '';
    endInput.value = end || '';
    startField.value = display(start);
    endField.value = display(end);

    root.dispatchEvent(new CustomEvent('range:change', { bubbles: true }));
  }

  function choose(day) {
    const state = dayState(day);
    if (!isPickable(state)) return;

    if (picking === 'start' || !start || end) {
      start = day;
      end = null;
      picking = 'end';
    } else if (day <= start) {
      start = day;
      picking = 'end';
    } else {
      end = day;
      picking = 'start';
    }

    hovered = null;
    focusDay = day;
    commit();
    render();

    if (start && end) setTimeout(close, 140);
  }
  const setExpanded = (state) => {
    [startField, endField].forEach((field) =>
      field.setAttribute('aria-expanded', String(state))
    );
  };

  function open() {
    if (!panel.hidden) return;
    view = startOfMonth(start ? fromIso(start) : new Date());
    panel.hidden = false;
    setExpanded(true);
    render();
  }

  function close() {
    panel.hidden = true;
    setExpanded(false);
  }

  const toggle = (target) => {
    picking = target;
    if (panel.hidden) open();
    render();
  };

  [startField, endField].forEach((field) => {
    const role = () => (field === endField && start ? 'end' : 'start');

    field.addEventListener('focus', () => toggle(role()));
    field.addEventListener('click', () => toggle(role()));
    field.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') close();
      else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggle(role());
      }
    });
  });

  panel.addEventListener('click', (event) => {
    const day = event.target.closest('[data-day]');
    if (day) {
      choose(day.dataset.day);
      return;
    }
    if (event.target.closest('[data-cal-prev]')) {
      view = addMonths(view, -1);
      render();
    } else if (event.target.closest('[data-cal-next]')) {
      view = addMonths(view, 1);
      render();
    }
  });

  panel.addEventListener('mouseover', (event) => {
    if (picking !== 'end' || !start || end) return;
    const day = event.target.closest('[data-day]');
    if (!day || day.dataset.day === hovered) return;
    if (!isPickable(dayState(day.dataset.day))) return;
    hovered = day.dataset.day;
    paintRange();
  });

  panel.addEventListener('mouseleave', () => {
    if (!hovered) return;
    hovered = null;
    paintRange();
  });

  const KEY_STEPS = {
    ArrowLeft: -1,
    ArrowRight: 1,
    ArrowUp: -7,
    ArrowDown: 7,
    PageUp: -28,
    PageDown: 28,
  };

  panel.addEventListener('keydown', (event) => {
    const cell = event.target.closest('[data-day]');
    if (!cell) return;

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      choose(cell.dataset.day);
      return;
    }

    const step = KEY_STEPS[event.key];
    if (step === undefined) return;

    event.preventDefault();
    const next = iso(addDays(fromIso(focusDay), step));
    if (next < todayIso) return;
    focusDay = next;
    const shown = [view, addMonths(view, 1)].map(
      (m) => `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, '0')}`
    );
    if (!shown.includes(focusDay.slice(0, 7))) {
      view = addMonths(startOfMonth(fromIso(focusDay)), step < 0 ? 0 : -1);
      if (view < startOfMonth(new Date())) view = startOfMonth(new Date());
    }

    render();
    months.querySelector(`[data-day="${focusDay}"]`)?.focus();
  });

  document.addEventListener('click', (event) => {
    if (panel.hidden) return;
    if (panel.contains(event.target) || datePair.contains(event.target)) return;
    close();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });

  commit();

  api
    .get(endpoint)
    .then((data) => {
      blockedSorted = data.unavailable || [];
      blocked = new Set(blockedSorted);
      minDays = Number(data.min_days || minDays);
      todayIso = data.today || todayIso;

      if (start && blocked.has(start)) {
        start = null;
        end = null;
        picking = 'start';
      }
      commit();
      root.dataset.availabilityReady = 'true';
      if (!panel.hidden) render();
    })
    .catch(() => {
      root.dataset.availabilityReady = 'error';
    });
}

export function initAvailabilityCalendar(root = document) {
  root.querySelectorAll('[data-availability-calendar]').forEach(buildCalendar);
}
