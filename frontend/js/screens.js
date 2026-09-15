/**
 * The page's own screens around the tests: resuming, retrying a submission,
 * moving on between stages, the end of the session, and the errors that stop
 * a load. Each renders into the container it is given.
 */

import { escapeHtml } from './dom.js';
import { pageCount } from './progress.js';
import { currentLanguage, setLanguage, t } from './strings.js';

/** Render the page chrome (language, tab title) for the config about to run. */
export function applyConfigChrome(config) {
  setLanguage(config.ui_language);
  document.title = config.title;
  document.documentElement.lang = currentLanguage();
}

/**
 * Ask the listener whether to resume a saved in-progress session or start
 * over. Renders a two-button screen into `container` and resolves true
 * (resume) or false (start over).
 *
 * @param {HTMLElement} container
 * @param {Object} record - The saved resume record (see resume.js).
 * @returns {Promise<boolean>}
 */
export function promptResume(container, record) {
  const total = pageCount(record.config ?? {});
  const page = (record.progress?.currentIndex ?? 0) + 1;
  // A stage handed its session but not started has no position to report.
  const progressHint =
    total > 0 && record.progress
      ? `<p>${t('resume_progress', { page: Math.min(page, total), total })}</p>`
      : '';

  container.innerHTML = `
    <div class="resume-screen">
      <h2>${t('resume_title')}</h2>
      <p>${t('resume_body')}</p>
      ${progressHint}
      <div class="screen-actions">
        <button class="btn btn-primary" id="btn-resume" type="button">${t('resume_resume')}</button>
        <button class="btn btn-secondary" id="btn-restart" type="button">${t('resume_startOver')}</button>
      </div>
    </div>
  `;

  return new Promise((resolve) => {
    container.querySelector('#btn-resume').addEventListener('click', () => resolve(true));
    container.querySelector('#btn-restart').addEventListener('click', () => resolve(false));
  });
}

/**
 * Show a submission-failure screen with a Retry button; resolves when the
 * listener clicks it. Used on the survey path, where the test UI (and its
 * own inline retry, see submit.js) is already gone by the time the POST runs.
 *
 * @param {HTMLElement} container
 * @param {Error} err
 * @returns {Promise<void>}
 */
export function promptRetry(container, err) {
  container.innerHTML = `
    <div class="error-screen">
      <h2>Submission failed</h2>
      <p>${escapeHtml(err.message)}</p>
      <button class="btn btn-primary" id="btn-retry" type="button">Retry</button>
    </div>
  `;
  return new Promise((resolve) => {
    container.querySelector('#btn-retry').addEventListener('click', () => resolve());
  });
}

/**
 * Show the screen between two stages of a sequence; resolves when the
 * listener starts the next one. A button rather than an automatic move on:
 * the next test opens with its own instructions, and the listener may want
 * a break first.
 *
 * @param {HTMLElement} container
 * @param {import('./stage.js').Stage} stage - The stage just submitted; the
 *   progress bar is left at the end of its share.
 * @param {number} done - How many stages are submitted.
 * @param {number} total - How many stages the sequence has.
 * @returns {Promise<void>}
 */
export function promptNextStage(container, stage, done, total) {
  stage.showProgress(1);
  container.innerHTML = `
    <div class="complete-screen">
      <div class="complete-icon">✓</div>
      <h2>${t('complete_stage', { done, total })}</h2>
      <p>${t('complete_body')}</p>
      <div class="screen-actions">
        <button class="btn btn-primary" id="btn-next-stage" type="button">${t('complete_next')}</button>
      </div>
    </div>
  `;
  return new Promise((resolve) => {
    container.querySelector('#btn-next-stage').addEventListener('click', () => resolve());
  });
}

/**
 * Show the screen that ends the whole session.
 *
 * @param {HTMLElement} container
 * @param {import('./stage.js').Stage} stage - The last stage, whose share ends the bar.
 */
export function showComplete(container, stage) {
  stage.showProgress(1);
  container.innerHTML = `
    <div class="complete-screen">
      <div class="complete-icon">✓</div>
      <h2>${t('complete_title')}</h2>
      <p>${t('complete_body')}</p>
    </div>
  `;
}

/**
 * Show why the session cannot start (see preflight.js).
 *
 * @param {HTMLElement} container
 * @param {{missing: string[], saveErrors: string[]}} problems
 */
export function showPreflightErrors(container, { missing, saveErrors }) {
  const errors = saveErrors.map((e) => `<p><strong>Result saving:</strong> ${escapeHtml(e)}</p>`);
  if (missing.length > 0)
    errors.push(`
    <p><strong>${missing.length} audio file(s) not accessible:</strong></p>
    <ul class="error-list">
      ${missing.map((u) => `<li><code>${escapeHtml(u)}</code></li>`).join('')}
    </ul>
  `);
  container.innerHTML = `
    <div class="error-screen">
      <h2>Cannot start test</h2>
      ${errors.join('')}
    </div>
  `;
}

/** Show a failure that stopped the page from loading at all. */
export function showLoadError(container, err) {
  container.innerHTML = `
    <div class="error-screen">
      <h2>Failed to load test</h2>
      <p>${escapeHtml(err.message)}</p>
    </div>
  `;
}
