/**
 * Entry point: fetches config, selects the appropriate test class, and
 * renders the test into #app. Shows an error screen on any failure.
 *
 * The page runs one config, or several back to back as a sequence: config.php
 * then answers with a manifest naming the stages, and each stage runs as a
 * lone config would - its own practice, test, and survey, submitted to its
 * own results - under one session id and one set of metadata answers, asked
 * before the first. A lone config is a sequence of one (see stage.js).
 */

import { fetchConfig, submitRatings } from './api.js';
import { escapeHtml } from './dom.js';
import { MetadataPage } from './metadata.js';
import { runPracticeStage } from './practice.js';
import { pageCount, setStageSpan, showStageProgress, stageSpans } from './progress.js';
import {
  buildRecord,
  clearRecord,
  clearStageRecords,
  findResumableStage,
  pruneExpiredRecords,
  recordKey,
  saveRecord,
} from './resume.js';
import { generateSessionId } from './session.js';
import { audioUrl, setStage, stageUrl } from './stage.js';
import { currentLanguage, setLanguage, t } from './strings.js';
import { ABTest } from './test-types/ab.js';
import { ABXTest } from './test-types/abx.js';
import { CMOSTest } from './test-types/cmos.js';
import { DMOSTest } from './test-types/dmos.js';
import { MOSTest } from './test-types/mos.js';
import { MUSHRATest } from './test-types/mushra.js';
import { XABTest } from './test-types/xab.js';

/**
 * Return the flat list of stimuli to preflight-check, regardless of test type.
 *
 * @param {Object} config
 * @returns {Array<{id: string, audio_url?: string}>}
 */
function flatStimuli(config) {
  // ABX's hidden "X" reference is deliberately excluded here - it's always a
  // duplicate of one of this same trial's own A/B stimuli (already checked
  // below), fetched through a different resolver URL, so probing it
  // separately would be redundant.
  if (config.test_type === 'dmos') {
    return config.trials.flatMap((trial) => [trial.reference, trial.test]);
  }
  if (config.test_type === 'cmos' || config.test_type === 'ab' || config.test_type === 'abx') {
    return config.trials.flatMap((trial) => trial.stimuli);
  }
  if (config.test_type === 'xab') {
    return config.trials.flatMap((trial) => [trial.reference, ...trial.stimuli]);
  }
  if (config.test_type === 'mushra') {
    return config.trials.flatMap((trial) =>
      [trial.reference, ...trial.systems, trial.anchor].filter(Boolean)
    );
  }
  return config.stimuli;
}

/** The config's practice stimuli/trials, or [] when it has no practice stage. */
function practiceItems(config) {
  return config.practice_stimuli ?? config.practice_trials ?? [];
}

/**
 * HEAD-request each audio URL in parallel.
 *
 * @param {string[]} urls
 * @returns {Promise<string[]>} URLs that returned a non-OK response or threw.
 */
async function checkAudioFiles(urls) {
  const results = await Promise.all(
    urls.map(async (url) => {
      try {
        const res = await fetch(url, { method: 'HEAD' });
        return res.ok ? null : url;
      } catch {
        return url;
      }
    })
  );
  return results.filter(Boolean);
}

/**
 * GET save.php to verify the results directory is writable before the test starts.
 *
 * @param {string} url - save.php, naming the stage in a sequence.
 * @returns {Promise<string|null>} Error message, or null if writable.
 */
async function checkSaveEndpoint(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return err.error || `save.php returned ${res.status}`;
    }
    return null;
  } catch {
    return 'Cannot reach save.php';
  }
}

/** Map test_type strings to their corresponding test class constructors. */
const testTypeMap = {
  mos: MOSTest,
  dmos: DMOSTest,
  cmos: CMOSTest,
  ab: ABTest,
  abx: ABXTest,
  xab: XABTest,
  mushra: MUSHRATest,
};

/** Return the test class for the config's test_type; throws on an unknown one. */
function testClassFor(config) {
  const TestClass = testTypeMap[config.test_type];
  if (!TestClass) throw new Error(`Unknown test type: "${config.test_type}"`);
  return TestClass;
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
function promptResume(container, record) {
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

/** Whether a {title, description, fields} block has anything to display. */
function hasFormPage(form) {
  return !!form?.description || form?.fields?.length > 0;
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
function promptRetry(container, err) {
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
 * @param {number} done - How many stages are submitted.
 * @param {number} total - How many stages the sequence has.
 * @returns {Promise<void>}
 */
function promptNextStage(container, done, total) {
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

/** Show the screen that ends the whole session. */
function showComplete(container) {
  showStageProgress(1);
  container.innerHTML = `
    <div class="complete-screen">
      <div class="complete-icon">✓</div>
      <h2>${t('complete_title')}</h2>
      <p>${t('complete_body')}</p>
    </div>
  `;
}

/** Render the page chrome (language, tab title) for the config about to run. */
function applyConfigChrome(config) {
  setLanguage(config.ui_language);
  document.title = config.title;
  document.documentElement.lang = currentLanguage();
}

/**
 * Fetch every stage's config, in order. Sequential rather than in parallel:
 * each request names its stage through stage.js's current stage.
 *
 * @param {string[]} stageIds
 * @returns {Promise<Object[]>}
 */
async function fetchStageConfigs(stageIds) {
  const configs = [];
  for (const stageId of stageIds) {
    setStage(stageId);
    configs.push(await fetchConfig());
  }
  return configs;
}

/**
 * Decide where this page load starts, from the saved records.
 *
 * With nothing to resume, the first stage starts with a new session.
 * Otherwise the saved session is offered back - a stage in progress, or one
 * handed its session but not started yet (see main). Resuming continues at
 * that stage with the session id and metadata answers, restoring its frozen
 * config and answers when it was in progress. Starting over clears every
 * stage's record and begins the whole sequence again with a new session, as
 * a lone config does: keeping the old session instead would, on a shared
 * device, pass one listener's id and answers on to the next.
 *
 * @param {HTMLElement} container
 * @param {Object[]} configs - Each stage's freshly fetched config, in order.
 * @returns {Promise<{index: number, carried: Object|null, resumed: Object|null}>}
 *   carried: {sessionId, metadata} to continue with, or null for a new
 *   session. resumed: the saved record to restore, or null to start afresh.
 */
async function chooseStart(container, configs) {
  const now = Date.now();
  const found = findResumableStage(configs, pruneExpiredRecords(now), now);
  if (!found) return { index: 0, carried: null, resumed: null };
  const { index, record } = found;
  setLanguage(configs[index].ui_language);
  if (await promptResume(container, record)) {
    return {
      index,
      carried: { sessionId: record.sessionId, metadata: record.metadata ?? {} },
      resumed: record.progress ? record : null,
    };
  }
  clearStageRecords(configs);
  return { index: 0, carried: null, resumed: null };
}

/**
 * Check, before anything is asked of the listener, that every stage about
 * to run can: its audio (practice included) is reachable and its results can
 * be saved. Returns the error screen's paragraphs, [] when all is well.
 *
 * @param {Array<{stageId: string|null, config: Object, withPractice: boolean}>} stages
 * @returns {Promise<string[]>}
 */
async function preflight(stages) {
  const missing = [];
  const saveErrors = new Set();
  for (const { stageId, config, withPractice } of stages) {
    setStage(stageId);
    // Practice stimuli/trials are sampled independently of the session's, so
    // they may reference audio files the session list doesn't - preflight
    // them too, reusing flatStimuli on a config-shaped view of the subset.
    const practice = withPractice
      ? flatStimuli({
          ...config,
          stimuli: config.practice_stimuli,
          trials: config.practice_trials,
        })
      : [];
    const urls = [...practice, ...flatStimuli(config)].map(audioUrl);
    const [stageMissing, saveError] = await Promise.all([
      checkAudioFiles(urls),
      checkSaveEndpoint(stageUrl('save.php')),
    ]);
    missing.push(...stageMissing);
    if (saveError) saveErrors.add(saveError);
  }

  const errors = [...saveErrors].map(
    (e) => `<p><strong>Result saving:</strong> ${escapeHtml(e)}</p>`
  );
  if (missing.length > 0)
    errors.push(`
    <p><strong>${missing.length} audio file(s) not accessible:</strong></p>
    <ul class="error-list">
      ${missing.map((u) => `<li><code>${escapeHtml(u)}</code></li>`).join('')}
    </ul>
  `);
  return errors;
}

/**
 * Run one stage - practice (unless resumed), the test, then the survey -
 * and resolve once its answers are submitted.
 *
 * @param {HTMLElement} container
 * @param {Object} config - The stage's delivered config.
 * @param {{sessionId: string, metadata: Object}} session
 * @param {Object|null} progress - Saved progress to restore, or null.
 * @returns {Promise<void>}
 */
async function runStage(container, config, session, progress) {
  applyConfigChrome(config);
  const TestClass = testClassFor(config);
  container.innerHTML = '';
  showStageProgress(0);

  // Practice is skipped on resume: the listener has already been through it.
  // It leaves the progress bar alone (see ListeningTest._updateProgressBar).
  if (!progress && practiceItems(config).length > 0) {
    await runPracticeStage(config, session.sessionId, TestClass, container);
    container.innerHTML = '';
  }

  // Persist the whole delivered config plus current answers/position after
  // every state change, so the session can be resumed if the tab is closed.
  // With the window set to 0 nothing is written at all: a record that will
  // never be offered would only take up the listener's storage quota.
  const key = recordKey(config.experiment_id);
  const persist = (test) => {
    if (config.resume.max_age_ms <= 0) return;
    saveRecord(
      key,
      buildRecord(config, session.sessionId, session.metadata, test.getProgress(), Date.now())
    );
  };

  await new Promise((resolve) => {
    async function onSubmit(sid, testType, payload) {
      // Post-test survey: shown between the last trial ("Finish") and the
      // actual POST, so its answers ride along in the same submission.
      const hasSurvey = hasFormPage(config.survey);
      let surveyAnswers = {};
      if (hasSurvey) {
        const surveyPage = new MetadataPage(config.survey.fields, {
          title: config.survey.title,
          description: config.survey.description,
          submitLabel: t('submit_idle'),
          // Same wording as the test page's own button (see submit.js): from
          // here the submission is what is in flight.
          busyLabel: t('submit_busy'),
        });
        container.innerHTML = '';
        surveyAnswers = await surveyPage.collect(container);
      }

      const request = {
        session_id: sid,
        test_type: testType,
        metadata: session.metadata,
        survey: surveyAnswers,
        ...payload,
      };
      let submitted = false;
      while (!submitted) {
        try {
          await submitRatings(request);
          submitted = true;
        } catch (err) {
          // Without a survey the test UI still exists: rethrow so submit.js
          // restores its button/shortcuts and shows the error inline there.
          // With one, that UI is gone - retry from a dedicated screen instead
          // (the answers are kept in `request`, nothing is re-entered).
          if (!hasSurvey) throw err;
          await promptRetry(container, err);
        }
      }
      // The stage is complete - it must never be offered for resume again.
      clearRecord(key);
      resolve();
    }

    const test = new TestClass(config, session.sessionId, onSubmit);
    test._onChange = () => persist(test);
    test.render(container);
    if (progress) test.restoreProgress(progress);
  });
}

async function main() {
  const container = document.getElementById('app');
  // Before any stage is named, config.php answers with what the page is: a
  // lone config, or a sequence's manifest listing its stages in order.
  const first = await fetchConfig();
  const stageIds = first.sequence ?? [null];
  const freshConfigs = first.sequence ? await fetchStageConfigs(stageIds) : [first];
  // Set before any DOM is touched - promptResume() needs translated strings
  // too. Re-set as each stage runs (see applyConfigChrome).
  setLanguage(freshConfigs[0].ui_language);

  const start = await chooseStart(container, freshConfigs);
  // A resumed stage runs the frozen config it was started with - re-fetching
  // would re-sample and re-shuffle into a different test (and re-mint x
  // tokens). Every other stage runs the config just fetched.
  const configs = freshConfigs.map((config, i) =>
    i === start.index && start.resumed ? start.resumed.config : config
  );
  applyConfigChrome(configs[start.index]);
  const stages = stageIds.map((stageId, i) => ({ stageId, config: configs[i] })).slice(start.index);

  for (const { config } of stages) testClassFor(config);
  const errors = await preflight(
    stages.map((stage, i) => ({
      ...stage,
      withPractice: !(i === 0 && start.resumed) && practiceItems(stage.config).length > 0,
    }))
  );
  if (errors.length > 0) {
    container.innerHTML = `
      <div class="error-screen">
        <h2>Cannot start test</h2>
        ${errors.join('')}
      </div>
    `;
    return;
  }

  container.innerHTML = '';
  let session = start.carried;
  if (!session) {
    session = { sessionId: generateSessionId(), metadata: {} };
    // Prose alone is reason enough to show the page: a study may need to
    // state what it collects without collecting anything on that page itself.
    if (hasFormPage(configs[0].metadata)) {
      const metaPage = new MetadataPage(configs[0].metadata.fields, {
        title: configs[0].metadata.title,
        description: configs[0].metadata.description,
      });
      session.metadata = await metaPage.collect(container);
      container.innerHTML = '';
    }
  }

  // The progress bar spans the whole session, each stage its share of it -
  // the stages already submitted included, so a resumed session's bar
  // starts where they left it.
  const spans = stageSpans(configs.map(pageCount));
  for (const [i, { stageId, config }] of stages.entries()) {
    setStage(stageId);
    setStageSpan(spans[start.index + i]);
    await runStage(container, config, session, i === 0 ? (start.resumed?.progress ?? null) : null);
    const next = stages[i + 1];
    if (!next) break;
    // Hand the session on before asking for the click: a tab closed on the
    // screen below then offers to continue at the next stage.
    if (next.config.resume.max_age_ms > 0) {
      saveRecord(
        recordKey(next.config.experiment_id),
        buildRecord(next.config, session.sessionId, session.metadata, null, Date.now())
      );
    }
    showStageProgress(1);
    await promptNextStage(container, start.index + i + 1, stageIds.length);
  }
  showComplete(container);
}

main().catch((err) => {
  document.getElementById('app').innerHTML = `
    <div class="error-screen">
      <h2>Failed to load test</h2>
      <p>${escapeHtml(err.message)}</p>
    </div>
  `;
});
