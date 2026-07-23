import { escapeHtml } from './dom.js';

/**
 * Build the rating-keys fragment of the shortcut hint, shared by every
 * rating-scale test (MOS, DMOS, CMOS).
 *
 * Keys are ordered by ascending rating value. The compact "1-5" dash form is
 * used only when every key is a single digit and each digit is exactly one
 * higher than the previous - anything else (letters, gaps, multi-character
 * keys) lists every key individually, since a dash range would falsely imply
 * that the in-between keys work too (and an alphabet run like "a-e" reads
 * ambiguously even when it happens to be contiguous).
 *
 * @param {Object} rating - Browser-facing shortcut map: pressed key → rating value.
 * @returns {string} HTML fragment of <kbd> elements.
 */
export function ratingKeysHint(rating) {
  const keys = Object.entries(rating)
    .sort((a, b) => a[1] - b[1])
    .map(([key]) => key);

  const isDigitRun =
    keys.length > 1 &&
    keys.every((k, i) => /^[0-9]$/.test(k) && (i === 0 || Number(k) === Number(keys[i - 1]) + 1));
  if (isDigitRun) {
    return `<kbd>${escapeHtml(keys[0])}</kbd>\u2013<kbd>${escapeHtml(keys[keys.length - 1])}</kbd>`;
  }
  return keys.map((k) => `<kbd>${escapeHtml(k)}</kbd>`).join('');
}
