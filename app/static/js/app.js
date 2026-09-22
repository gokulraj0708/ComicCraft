(() => {
  const form = document.querySelector('#comic-form');
  const overlay = document.querySelector('#loading-overlay');
  const textarea = document.querySelector('textarea[name="story_prompt"]');
  const counter = document.querySelector('[data-character-count]');

  if (textarea && counter) {
    const updateCount = () => { counter.textContent = String(textarea.value.length); };
    textarea.addEventListener('input', updateCount);
    updateCount();
  }

  if (form && overlay) {
    const messages = [
      'Planning a clear beginning, middle, and ending.',
      'Writing narration and character dialogue.',
      'Creating consistent panel artwork.',
      'Laying out the downloadable PDF.'
    ];
    form.addEventListener('submit', () => {
      if (!form.checkValidity()) return;
      overlay.hidden = false;
      document.body.classList.add('is-generating');
      const target = overlay.querySelector('[data-loading-message]');
      let index = 0;
      window.setInterval(() => {
        index = (index + 1) % messages.length;
        if (target) target.textContent = messages[index];
      }, 3500);
    });
  }

  const download = document.querySelector('#download-comic');
  if (download) {
    download.addEventListener('click', () => {
      const successUrl = download.dataset.successUrl;
      if (successUrl) window.setTimeout(() => { window.location.href = successUrl; }, 900);
    });
  }
})();
