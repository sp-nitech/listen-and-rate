/**
 * Practice stage - shown right after metadata collection, before the real
 * test, when the server config carries practice_stimuli/practice_trials
 * (i.e. the YAML's practice.count > 0). Reuses the real TestClass on an
 * independently-sampled (server-side) practice subset, so every test type's
 * playback gating/keyboard shortcuts/UI work unchanged; results are never
 * submitted (see submit.js's practice bypass). The helpers below give every
 * test type's rendering the same practice look: badge next to the title, a
 * banner ahead of the instructions, "Practice N / M" page counters, and a
 * final Start (not Submit) button.
 */

import { proseHtml } from './dom.js';
import { t } from './strings.js';

/** " <span…>Practice</span>" to append inside the header's h1; '' for the real test. */
export function practiceBadgeHtml(config) {
  return config.isPractice ? ' <span class="practice-badge">Practice</span>' : '';
}

/**
 * The practice-instructions banner shown above the regular instructions.
 *
 * '' for the real test, and also when the practice stage carries no wording -
 * practice.instructions is optional, and an empty banner would still show as
 * a bordered, padded, coloured box with nothing in it. Prose, laid out like
 * the instructions it sits above (see proseHtml).
 */
export function practiceBannerHtml(config) {
  if (!config.isPractice) return '';
  return proseHtml(config.practice_instructions, 'practice-banner');
}

/**
 * The final page's button label: Start ends the practice; with a post-test
 * survey configured the last trial concludes the rating phase irreversibly
 * (the survey page follows and owns the real Submit; there is no way back,
 * so the survey's reflection can never contaminate the frozen ratings) -
 * "Finish" says exactly that, where "Next" would imply a Prev counterpart.
 */
export function finalButtonLabel(config) {
  if (config.isPractice) return t('practice_startTest');
  return config.survey?.fields?.length > 0 ? t('trial_finish') : t('submit_idle');
}

/**
 * The final page's confirm-shortcut hint, matching finalButtonLabel().
 *
 * Derived by lowercasing rather than a second set of translated strings:
 * ja has no case distinction, so this is a no-op there and the hint reads
 * identically to the button, exactly as the en wording always intended.
 */
export function finalConfirmHint(config) {
  return finalButtonLabel(config).toLowerCase();
}

/**
 * Run the practice stage: render the real TestClass on a config copy whose
 * stimuli/trials are the server's independently-sampled practice_stimuli/
 * practice_trials, with an onSubmit that never hits the network.
 *
 * @param {Object} config - Server config from /api/config.
 * @param {string} sessionId
 * @param {Function} TestClass - The same test-type class used for the real test.
 * @param {HTMLElement} container
 * @returns {Promise<void>} Resolves once the practice round is completed.
 */
export function runPracticeStage(config, sessionId, TestClass, container) {
  const practiceConfig = { ...config, isPractice: true };
  if (config.stimuli) {
    practiceConfig.stimuli = config.practice_stimuli;
  } else {
    practiceConfig.trials = config.practice_trials;
  }

  return new Promise((resolve) => {
    const test = new TestClass(practiceConfig, sessionId, async () => {
      resolve();
    });
    test.render(container);
  });
}
