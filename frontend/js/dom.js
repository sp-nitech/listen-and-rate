/** Safely escape a string for insertion into innerHTML. */
export function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

/**
 * Render config-authored prose (instructions, a form page's description), or
 * '' when there is none.
 *
 * The element carries `white-space: pre-line`, so the text is displayed
 * exactly as it reads here - only the line breaks move. A single newline is
 * the config file's own wrapping and reflows into a space; blank lines are
 * the author asking for breaks, and a run of n of them becomes n breaks (so
 * one blank line breaks the line, two leave a blank line in the display).
 * That distinction is the whole point: keeping every newline turns the
 * file's wrapping into hard breaks, and keeping none leaves no way to break
 * a line at all.
 *
 * Escaped, not parsed - this is plain text, not markup.
 */
export function proseHtml(text, className) {
  const prose = (text ?? '')
    .trim()
    .replace(/^[ \t]+|[ \t]+$/gm, '')
    .split(/(\n{2,})/)
    .map((part, i) => (i % 2 ? '\n'.repeat(part.length - 1) : part.replace(/\n/g, ' ')))
    .join('');
  return prose ? `<p class="${className}">${escapeHtml(prose)}</p>` : '';
}
