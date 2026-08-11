export function initBulkSelect(root = document) {
  root.querySelectorAll('[data-bulk-form]').forEach((form) => {
    if (form.dataset.bound) return;
    form.dataset.bound = '1';

    const master = form.querySelector('[data-bulk-all]');
    const boxes = () => [...form.querySelectorAll('[data-bulk-item]')];
    const bar = form.querySelector('[data-bulk-bar]');
    const countEl = form.querySelector('[data-bulk-count]');

    const sync = () => {
      const items = boxes();
      const checked = items.filter((b) => b.checked);

      if (bar) bar.hidden = checked.length === 0;
      if (countEl) countEl.textContent = String(checked.length);

      items.forEach((box) => {
        box.closest('tr')?.setAttribute('data-selected', String(box.checked));
      });

      if (master) {
        master.checked = checked.length > 0 && checked.length === items.length;
        master.indeterminate = checked.length > 0 && checked.length < items.length;
      }
    };

    master?.addEventListener('change', () => {
      boxes().forEach((box) => {
        box.checked = master.checked;
      });
      sync();
    });

    boxes().forEach((box) => box.addEventListener('change', sync));
    sync();
  });
}

export function initCounters(root = document) {
  const targets = root.querySelectorAll('[data-count]');
  if (!targets.length) return;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const run = (node) => {
    const target = Number(node.dataset.count);
    if (!Number.isFinite(target)) return;

    const decimals = Number(node.dataset.countDecimals || 0);
    const prefix = node.dataset.countPrefix || '';
    const suffix = node.dataset.countSuffix || '';

    const write = (value) => {
      node.textContent =
        prefix +
        value.toLocaleString(undefined, {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }) +
        suffix;
    };

    if (reduced || target === 0) {
      write(target);
      return;
    }

    const duration = 900;
    const start = performance.now();

    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      // easeOutCubic
      const eased = 1 - (1 - progress) ** 3;
      write(target * eased);
      if (progress < 1) requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        run(entry.target);
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.35 }
  );

  targets.forEach((node) => observer.observe(node));
}

/** Fade elements in as they enter the viewport. */
export function initReveal(root = document) {
  const targets = root.querySelectorAll('[data-reveal]');
  if (!targets.length) return;

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    targets.forEach((node) => node.classList.add('is-visible'));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
  );

  targets.forEach((node, index) => {
    if (!node.style.getPropertyValue('--reveal-delay')) {
      node.style.setProperty('--reveal-delay', `${Math.min(index * 55, 380)}ms`);
    }
    observer.observe(node);
  });
}
