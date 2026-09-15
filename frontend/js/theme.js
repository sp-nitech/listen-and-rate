/**
 * The page's light/dark theme: the listener's own choice once they make one
 * with the toggle, the system's preference until then, and dark when neither
 * says. The choice is kept in localStorage, so it outlasts a reload.
 *
 * index.html applies the same rule inline before the CSS loads, since a
 * module runs too late to prevent a flash of the other theme - keep the two
 * in step.
 */

const THEME_KEY = 'theme';

// Inline SVG (fill: currentColor) rather than emoji/glyphs, so the icon is
// monochrome, consistent with the player icons, and identical across
// platforms. The button shows the mode it switches TO: a moon while light
// is active, a sun while dark is active.
const SUN_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.76 4.84l-1.8-1.79-1.41 1.41 1.79 1.79 1.42-1.41zM4 10.5H1v2h3v-2zm9-9.95h-2V3.5h2V.55zm7.45 3.91l-1.41-1.41-1.79 1.79 1.41 1.41 1.79-1.79zm-3.21 13.7l1.79 1.8 1.41-1.41-1.8-1.79-1.4 1.4zM20 10.5v2h3v-2h-3zm-8-5c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm-1 16.95h2V19.5h-2v2.95zm-7.45-3.91l1.41 1.41 1.79-1.8-1.41-1.41-1.79 1.8z"/></svg>';
const MOON_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

/**
 * Which theme to show: a saved choice first, then the system's preference.
 *
 * @param {string|null} saved - what the toggle last saved, if anything
 * @param {boolean} prefersLight - whether the system asks for a light theme
 * @returns {'light'|'dark'}
 */
export function themeFor(saved, prefersLight) {
  if (saved === 'light' || saved === 'dark') return saved;
  return prefersLight ? 'light' : 'dark';
}

/**
 * Show the theme, follow the system's changes until the listener chooses,
 * and make the toggle save their choice.
 *
 * @param {HTMLElement} root - the element whose data-theme the CSS reads
 * @param {HTMLElement|null} button - the toggle
 * @param {Storage} storage - where the choice is kept
 * @param {MediaQueryList} systemLight - the system's prefers-color-scheme: light
 */
export function mountTheme(root, button, storage, systemLight) {
  function apply(theme) {
    if (theme === 'light') {
      root.setAttribute('data-theme', 'light');
    } else {
      root.removeAttribute('data-theme');
    }
    if (button) {
      button.innerHTML = theme === 'light' ? MOON_SVG : SUN_SVG;
      button.setAttribute(
        'aria-label',
        theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'
      );
    }
  }

  const current = () => themeFor(storage.getItem(THEME_KEY), systemLight.matches);
  apply(current());
  // A saved choice wins inside themeFor, so this only moves an unchosen page.
  systemLight.addEventListener('change', () => apply(current()));

  button?.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    storage.setItem(THEME_KEY, next);
    apply(next);
  });
}
