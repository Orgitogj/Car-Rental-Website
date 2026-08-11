export function initContract() {
  document.querySelectorAll('[data-contract-sign]').forEach((form) => {
    const agree = form.querySelector('[data-signature-agree]');
    const name = form.querySelector('[data-signature-input]');
    const submit = form.querySelector('[data-signature-submit]');
    const hint = form.querySelector('[data-signature-hint]');
    if (!agree || !name || !submit) return;

    const sync = () => {
      const ready = agree.checked && name.value.trim().length >= 3;
      submit.disabled = !ready;
      if (hint) hint.hidden = ready;
    };

    agree.addEventListener('change', sync);
    name.addEventListener('input', sync);
    form.addEventListener('submit', () => {
      submit.disabled = true;
    });

    sync();
  });

  const pending = document.querySelector('.alert--warning [data-contract-scroll]');
  if (pending) pending.setAttribute('aria-label', document.title);
}
