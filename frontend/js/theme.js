/** Theme toggle: dark (default) ↔ light. Persists choice to localStorage. */
(() => {
  const html = document.documentElement;
  const btn = document.getElementById('theme-toggle');

  // Inline SVG (fill: currentColor) rather than emoji/glyphs, so the icon is
  // monochrome, consistent with the player icons, and identical across
  // platforms. The button shows the mode it switches TO: a moon while light
  // is active, a sun while dark is active.
  const SUN_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.76 4.84l-1.8-1.79-1.41 1.41 1.79 1.79 1.42-1.41zM4 10.5H1v2h3v-2zm9-9.95h-2V3.5h2V.55zm7.45 3.91l-1.41-1.41-1.79 1.79 1.41 1.41 1.79-1.79zm-3.21 13.7l1.79 1.8 1.41-1.41-1.8-1.79-1.4 1.4zM20 10.5v2h3v-2h-3zm-8-5c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm-1 16.95h2V19.5h-2v2.95zm-7.45-3.91l1.41 1.41 1.79-1.8-1.41-1.41-1.79 1.8z"/></svg>';
  const MOON_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

  function applyTheme(theme) {
    if (theme === 'light') {
      html.setAttribute('data-theme', 'light');
    } else {
      html.removeAttribute('data-theme');
    }
    if (btn) {
      btn.innerHTML = theme === 'light' ? MOON_SVG : SUN_SVG;
      btn.setAttribute(
        'aria-label',
        theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'
      );
    }
  }

  function toggleTheme() {
    const next = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', next);
    applyTheme(next);
  }

  applyTheme(localStorage.getItem('theme') ?? 'dark');

  if (btn) btn.addEventListener('click', toggleTheme);
})();
