/**
 * Dashboard sidebar
 */

const STORAGE_KEY = 'cr.sidebar.collapsed';
const DESKTOP = '(min-width: 1025px)';

export function initSidebar() {
  const app = document.querySelector('.app');
  if (!app) return;

  const collapseBtn = document.querySelector('[data-sidebar-collapse]');
  const drawerBtn = document.querySelector('[data-sidebar-drawer]');
  const scrim = document.querySelector('.app__scrim');

  // Restore the remembered desktop state.
  if (window.matchMedia(DESKTOP).matches && localStorage.getItem(STORAGE_KEY) === '1') {
    app.classList.add('is-collapsed');
    collapseBtn?.setAttribute('aria-expanded', 'false');
  }

  collapseBtn?.addEventListener('click', () => {
    const collapsed = app.classList.toggle('is-collapsed');
    localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
    collapseBtn.setAttribute('aria-expanded', String(!collapsed));
  });

  const closeDrawer = () => {
    app.classList.remove('is-drawer-open');
    drawerBtn?.setAttribute('aria-expanded', 'false');
  };

  drawerBtn?.addEventListener('click', () => {
    const open = app.classList.toggle('is-drawer-open');
    drawerBtn.setAttribute('aria-expanded', String(open));
    if (open) document.querySelector('.sidebar__link')?.focus();
  });

  scrim?.addEventListener('click', closeDrawer);

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && app.classList.contains('is-drawer-open')) {
      closeDrawer();
      drawerBtn?.focus();
    }
  });

  // Following a link on mobile should close the drawer.
  document.querySelectorAll('.sidebar__link').forEach((link) => {
    link.addEventListener('click', () => {
      if (!window.matchMedia(DESKTOP).matches) closeDrawer();
    });
  });
}

/* -- Public navbar -------------------------------------------------------- */

export function initNavbar() {
  const navbar = document.querySelector('.navbar');
  if (!navbar) return;

  const toggle = navbar.querySelector('.navbar__toggle');

  toggle?.addEventListener('click', () => {
    const open = navbar.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
  });

  // Solidify the bar once the page scrolls away from the hero.
  const onScroll = () => {
    navbar.classList.toggle('is-stuck', window.scrollY > 12);
  };

  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
}

/* -- Theme toggle --------------------------------------------------------- */

const THEME_KEY = 'cr.theme';

export function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === 'dark' || stored === 'light') {
    document.documentElement.dataset.theme = stored;
  }

  document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const current =
        document.documentElement.dataset.theme ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem(THEME_KEY, next);
      button.setAttribute('aria-pressed', String(next === 'dark'));
    });
  });
}
