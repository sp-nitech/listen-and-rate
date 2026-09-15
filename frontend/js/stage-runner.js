/**
 * Run one stage: practice (unless resumed), the test, then the survey, and
 * the submission of its answers - resuming from saved progress, and saving
 * progress as the listener goes.
 */

import { submitRatings } from './api.js';
import { hasFormPage, MetadataPage } from './metadata.js';
import { practiceItems, runPracticeStage } from './practice.js';
import { buildRecord, clearRecord, recordKey, saveRecord } from './resume.js';
import { applyConfigChrome, promptRetry } from './screens.js';
import { t } from './strings.js';
import { ABTest } from './test-types/ab.js';
import { ABXTest } from './test-types/abx.js';
import { CMOSTest } from './test-types/cmos.js';
import { DMOSTest } from './test-types/dmos.js';
import { MOSTest } from './test-types/mos.js';
import { MUSHRATest } from './test-types/mushra.js';
import { XABTest } from './test-types/xab.js';

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
export function testClassFor(config) {
  const TestClass = testTypeMap[config.test_type];
  if (!TestClass) throw new Error(`Unknown test type: "${config.test_type}"`);
  return TestClass;
}

/**
 * Run one stage - practice (unless resumed), the test, then the survey -
 * and resolve once its answers are submitted.
 *
 * @param {HTMLElement} container
 * @param {{stage: import('./stage.js').Stage, config: Object}} current - The
 *   stage to run and its delivered config (see sequence.js's planStages).
 * @param {string[]} sequence - Every stage's experiment_id, in order.
 * @param {{sessionId: string, metadata: Object}} session
 * @param {Object|null} progress - Saved progress to restore, or null.
 * @returns {Promise<void>}
 */
export async function runStage(container, { stage, config }, sequence, session, progress) {
  applyConfigChrome(config);
  const TestClass = testClassFor(config);
  container.innerHTML = '';
  stage.showProgress(0);

  // Practice is skipped on resume: the listener has already been through it.
  // It leaves the progress bar alone (see ListeningTest._updateProgressBar).
  if (!progress && practiceItems(config).length > 0) {
    await runPracticeStage(config, stage, session.sessionId, TestClass, container);
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
      buildRecord(
        config,
        sequence,
        session.sessionId,
        session.metadata,
        test.getProgress(),
        Date.now()
      )
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
          await submitRatings(stage, request);
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

    const test = new TestClass(config, session.sessionId, onSubmit, stage);
    test._onChange = () => persist(test);
    test.render(container);
    if (progress) test.restoreProgress(progress);
  });
}
