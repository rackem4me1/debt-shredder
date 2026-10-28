/* Progressive enhancement only: no financial calculations or browser storage. */
(() => {
  'use strict';
  const form = document.getElementById('scenario-setup');
  if (!form) return;
  const sections = [...form.querySelectorAll('[data-setup-step]')];
  const progress = document.getElementById('setup-progress');
  const heading = document.getElementById('setup-heading');
  const hint = document.getElementById('setup-hint');
  const navigation = document.getElementById('setup-navigation');
  const back = document.getElementById('setup-back');
  const next = document.getElementById('setup-next');
  const all = document.getElementById('setup-all');
  const preview = document.getElementById('setup-preview');
  const steps = [
    ['Your cash', 'Name this what-if, choose its dates, and enter the cash you want to protect.'],
    ['Your cards', 'Enter Card 1, then optionally Cards 2 and 3. Each needs its own statement dates and minimum. Check the interest terms instead of guessing.'],
    ['Income and bills', 'Add money coming in and expenses going out. Open a row to add a schedule, or continue if none apply.'],
    ['Your payments', 'Choose a payment for each included card. The preview will show what fits after protecting cash for your bills.']
  ];
  let current = 0;
  let showAll = false;
  steps.forEach(([name], index) => {
    const item = document.createElement('span');
    item.textContent = `${index + 1}. ${name}`;
    progress.append(item);
  });
  function display(focus = true) {
    sections.forEach(section => {
      section.hidden = !showAll && Number(section.dataset.setupStep) !== current;
    });
    [...progress.children].forEach((item, index) => {
      if (!showAll && index === current) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    });
    heading.textContent = showAll ? 'All setup fields' : `Step ${current + 1} of ${steps.length}: ${steps[current][0]}`;
    hint.textContent = showAll ? 'All your entries are kept when you switch views.' : steps[current][1];
    back.hidden = showAll || current === 0;
    next.hidden = showAll || current === steps.length - 1;
    preview.hidden = !showAll && current !== steps.length - 1;
    all.textContent = showAll ? 'Use guided steps' : 'Show all fields';
    if (focus) { heading.focus(); heading.scrollIntoView({block: 'start'}); }
  }
  function invalidControl(step = null) {
    return [...form.elements].find(control => control.willValidate &&
      (step === null || Number(control.closest('[data-setup-step]')?.dataset.setupStep) === step) &&
      !control.validity.valid);
  }
  function reveal(control) {
    const section = control.closest('[data-setup-step]');
    if (section) current = Number(section.dataset.setupStep);
    display(false);
    for (let node = control.parentElement; node && node !== form; node = node.parentElement) {
      if (node.tagName === 'DETAILS') node.open = true;
    }
    control.focus();
    control.reportValidity();
  }
  next.addEventListener('click', () => {
    const invalid = invalidControl(current);
    if (invalid) return reveal(invalid);
    current += 1; display();
  });
  back.addEventListener('click', () => { current -= 1; display(); });
  all.addEventListener('click', () => { showAll = !showAll; display(); });
  form.addEventListener('submit', event => {
    const invalid = invalidControl(!showAll && current < steps.length - 1 ? current : null);
    if (invalid) { event.preventDefault(); reveal(invalid); return; }
    if (!showAll && current < steps.length - 1) {
      event.preventDefault(); current += 1; display();
    }
  });
  // Cross-field errors come from the server. Show every retained field for correction.
  showAll = Boolean(document.querySelector('[role="alert"]'));
  form.noValidate = true;
  progress.hidden = heading.hidden = hint.hidden = navigation.hidden = false;
  display(false);
})();
