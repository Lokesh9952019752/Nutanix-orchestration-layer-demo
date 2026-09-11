document.addEventListener('submit', (event) => {
  const form = event.target;
  if (form.matches('.grid-form')) {
    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
      button.textContent = 'Submitting…';
    }
  }
});
