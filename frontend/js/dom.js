/** Safely escape a string for insertion into innerHTML. */
export function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}
