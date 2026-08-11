import { initAuth } from '../components/auth.js';
import { initCharts } from '../components/chart.js';
import { initContract } from '../components/contract.js';
import { initAvailabilityCalendar } from '../components/datepicker.js';
import { initDateRange, initSearchFilters } from '../components/filters.js';
import { initPalette } from '../components/palette.js';
import {
  initConfirms,
  initDropdowns,
  initModals,
  initSubmitStates,
} from '../components/overlays.js';
import { initRestrictedActions } from '../components/restricted.js';
import { initNavbar, initSidebar, initTheme } from '../components/sidebar.js';
import { initBulkSelect, initCounters, initReveal } from '../components/table.js';
import { initCarDetail } from '../pages/car-detail.js';
import { toast } from './toast.js';

function initFlashMessages() {
  const node = document.getElementById('flash-messages');
  if (!node) return;

  try {
    const messages = JSON.parse(node.textContent || '[]');
    messages.forEach((item) => {
      toast(item.message, { tone: item.tone || 'info' });
    });
  } catch {
  }
}

function initStaggeredCards() {
  document.querySelectorAll('.results__grid').forEach((grid) => {
    [...grid.children].forEach((child, index) => {
      child.style.setProperty('--i', index);
    });
  });
}

function init() {
  initTheme();
  initNavbar();
  initSidebar();
  initRestrictedActions();
  initDropdowns();
  initModals();
  initConfirms();
  initSubmitStates();
  initBulkSelect();
  initCounters();
  initReveal();
  initCharts();
  initDateRange();
  initAvailabilityCalendar();
  initSearchFilters();
  initCarDetail();
  initAuth();
  initContract();
  initPalette();
  initFlashMessages();
  initStaggeredCards();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init, { once: true });
} else {
  init();
}
window.crToast = toast;
