function initPasswordToggles() {
  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    const input = button.parentElement?.querySelector('input');
    if (!input) return;

    button.addEventListener('click', () => {
      const revealed = input.type === 'text';
      input.type = revealed ? 'password' : 'text';
      button.setAttribute('aria-pressed', String(!revealed));
      button.setAttribute(
        'aria-label',
        revealed
          ? button.dataset.labelShow || 'Show password'
          : button.dataset.labelHide || 'Hide password',
      );
    });
  });
}
function paneIsValid(pane) {
  const fields = [...pane.querySelectorAll('input, select, textarea')];
  const invalid = fields.find((field) => !field.checkValidity());

  if (invalid) {
    invalid.reportValidity();
    invalid.focus();
    return false;
  }
  return true;
}

function initWizard() {
  document.querySelectorAll('[data-wizard]').forEach((form) => {
    const panes = [...form.querySelectorAll('[data-pane]')];
    const markers = [...form.querySelectorAll('[data-step-marker]')];
    if (panes.length < 2) return;

    const show = (step) => {
      form.dataset.step = String(step);

      panes.forEach((pane) => {
        pane.hidden = Number(pane.dataset.pane) !== step;
      });

      markers.forEach((marker) => {
        const number = Number(marker.dataset.stepMarker);
        marker.toggleAttribute('data-complete', number < step);
        if (number === step) marker.setAttribute('aria-current', 'step');
        else marker.removeAttribute('aria-current');
      });

      const heading = panes.find((pane) => !pane.hidden)?.querySelector('.wizard__title');
      heading?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    };

    form.querySelectorAll('[data-wizard-next]').forEach((button) => {
      button.addEventListener('click', () => {
        const pane = button.closest('[data-pane]');
        if (pane && !paneIsValid(pane)) return;
        show(Number(button.dataset.wizardNext));
      });
    });

    form.querySelectorAll('[data-wizard-back]').forEach((button) => {
      button.addEventListener('click', () => show(Number(button.dataset.wizardBack)));
    });
    show(Number(form.dataset.step) || 1);
  });
}

function initDropzones() {
  document.querySelectorAll('[data-dropzone]').forEach((zone) => {
    const input = zone.querySelector('input[type="file"]');
    const list = zone.querySelector('[data-dropzone-files]');
    if (!input) return;

    const render = () => {
      if (!list) return;
      const names = [...(input.files || [])].map((file) => file.name);
      list.hidden = names.length === 0;
      list.textContent = names.join(', ');
    };

    input.addEventListener('change', render);

    ['dragenter', 'dragover'].forEach((type) => {
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.add('is-dragging');
      });
    });

    ['dragleave', 'drop'].forEach((type) => {
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.remove('is-dragging');
      });
    });

    zone.addEventListener('drop', (event) => {
      if (!event.dataTransfer?.files?.length) return;
      input.files = event.dataTransfer.files;
      render();
    });

    render();
  });
}

export function initAuth() {
  initPasswordToggles();
  initWizard();
  initDropzones();
}
