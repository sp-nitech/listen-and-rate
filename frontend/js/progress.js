/**
 * The shared progress bar, measured across every stage of a sequence.
 *
 * Each stage counts its own pages in its trial counter ("Trial 1 / 4"),
 * while the bar at the top of the page shows how far the whole session has
 * come: every stage takes a share of the bar in proportion to its pages, and
 * a stage's progress is placed within its share. A lone config is a
 * sequence of one, so its share is the whole bar.
 *
 * The current stage's share is module-level state, set by app.js as each
 * stage starts - like stage.js's stage, and for the same reason: exactly one
 * stage runs at a time.
 */

let _span = { start: 0, width: 1 };

/**
 * Return how many pages a delivered config presents: one per stimulus for
 * MOS, one per trial for the other test types.
 *
 * @param {Object} config
 * @returns {number}
 */
export function pageCount(config) {
  return (config.stimuli ?? config.trials ?? []).length;
}

/**
 * Return each stage's share of the bar, in proportion to its pages.
 *
 * @param {number[]} pageCounts - Each stage's page count, in order.
 * @returns {Array<{start: number, width: number}>} Fractions of the whole bar.
 */
export function stageSpans(pageCounts) {
  const total = pageCounts.reduce((sum, n) => sum + n, 0);
  let start = 0;
  return pageCounts.map((n) => {
    const span = { start, width: total > 0 ? n / total : 0 };
    start += span.width;
    return span;
  });
}

/** Set the share of the bar that the stage now running takes. */
export function setStageSpan(span) {
  _span = span;
}

/**
 * Return the fraction of the whole bar reached by `fraction` of the current
 * stage.
 *
 * @param {number} fraction - How much of the current stage is done, 0 to 1.
 * @returns {number}
 */
export function overallFraction(fraction) {
  return _span.start + _span.width * fraction;
}

/** Show `fraction` (0 to 1) of the current stage done on the shared bar. */
export function showStageProgress(fraction) {
  const bar = document.getElementById('progress-bar');
  if (bar) bar.style.width = `${overallFraction(fraction) * 100}%`;
}
