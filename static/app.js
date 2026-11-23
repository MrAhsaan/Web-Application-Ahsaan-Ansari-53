document.addEventListener('DOMContentLoaded', () => {
  const navToggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-nav]');
  if (navToggle && nav) navToggle.addEventListener('click', () => {
    nav.classList.toggle('open');
    navToggle.setAttribute('aria-expanded', nav.classList.contains('open'));
  });

  document.querySelectorAll('[data-nav] a').forEach(a => a.addEventListener('click', () => nav?.classList.remove('open')));

  document.querySelectorAll('[data-faq]').forEach(item => {
    item.addEventListener('click', () => item.classList.toggle('open'));
  });

  const dateInput = document.querySelector('input[name="date"]');
  if (dateInput && !dateInput.min) {
    const d = new Date();
    dateInput.min = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  const bookingForm = document.querySelector('[data-booking-form]');
  if (bookingForm) {
    const steps = [...bookingForm.querySelectorAll('[data-step]')];
    const progress = bookingForm.querySelector('[data-progress]');
    const buttons = bookingForm.querySelectorAll('[data-next], [data-back]');
    let current = 0;
    const showStep = (i) => {
      current = Math.max(0, Math.min(i, steps.length - 1));
      steps.forEach((s, idx) => s.hidden = idx !== current);
      if (progress) progress.style.setProperty('--progress', `${((current + 1) / steps.length) * 100}%`);
      bookingForm.querySelectorAll('[data-step-dot]').forEach((dot, idx) => dot.classList.toggle('active', idx <= current));
    };
    buttons.forEach(btn => btn.addEventListener('click', () => {
      if (btn.matches('[data-next]')) {
        const fields = [...steps[current].querySelectorAll('input, select, textarea')];
        const valid = fields.every(f => !f.required || f.reportValidity());
        if (!valid) return;
        showStep(current + 1);
      } else showStep(current - 1);
    }));
    showStep(0);
  }

  const flash = document.querySelector('.flash');
  if (flash) setTimeout(() => flash.classList.add('hide'), 4500);

  document.querySelectorAll('[data-year]').forEach(el => el.textContent = new Date().getFullYear());
});
