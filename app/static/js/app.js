(() => {
  const form = document.querySelector('#comic-form');
  const overlay = document.querySelector('#loading-overlay');
  const textarea = document.querySelector('textarea[name="story_prompt"]');
  const counter = document.querySelector('[data-character-count]');

  /* Live character counter for the story brief. */
  if (textarea && counter) {
    const updateCount = () => { counter.textContent = String(textarea.value.length); };
    textarea.addEventListener('input', updateCount);
    updateCount();
  }

  /* Generation overlay: show progress while the server builds the comic. */
  if (form && overlay) {
    const messages = [
      'Planning a clear beginning, middle, and ending.',
      'Writing narration and character dialogue.',
      'Creating consistent panel artwork.',
      'Laying out the downloadable PDF.'
    ];
    const message = overlay.querySelector('[data-loading-message]');
    const steps = overlay.querySelectorAll('[data-loading-step]');

    form.addEventListener('submit', () => {
      if (!form.checkValidity()) return;

      overlay.hidden = false;
      document.body.classList.add('is-generating');

      /* Guard against double submission while the request is running. */
      const submit = form.querySelector('button[type="submit"]');
      if (submit) {
        submit.disabled = true;
        submit.setAttribute('aria-disabled', 'true');
      }

      let index = 0;
      const advance = () => {
        index = (index + 1) % messages.length;
        if (message) message.textContent = messages[index];
        steps.forEach((step, i) => {
          step.classList.toggle('is-active', i === index);
          step.classList.toggle('is-done', i < index);
        });
      };
      window.setInterval(advance, 3500);
    });
  }

  /* After the PDF download starts, move to the export confirmation page. */
  const download = document.querySelector('#download-comic');
  if (download) {
    download.addEventListener('click', () => {
      const successUrl = download.dataset.successUrl;
      if (successUrl) window.setTimeout(() => { window.location.href = successUrl; }, 900);
    });
  }
})();
