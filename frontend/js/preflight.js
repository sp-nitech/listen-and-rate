/**
 * The check run before anything is asked of the listener: that every stage
 * about to run can - its audio (practice included) is reachable and its
 * results can be saved. A problem found only part-way through would strand
 * the listener with a session they cannot finish.
 */

import { testClassFor } from './test-types/registry.js';

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

/**
 * Check every stage about to run, each through its own stage's URLs.
 *
 * @param {Array<{stage: import('./stage.js').Stage, config: Object, withPractice: boolean}>} stages
 *   withPractice: whether the stage will run its practice round - not when
 *   it is resumed, which skips it.
 * @returns {Promise<{missing: string[], saveErrors: string[]}>} The audio
 *   URLs that could not be fetched, and each distinct reason results cannot
 *   be saved; both empty when all is well.
 */
export async function preflight(stages) {
  const checks = await Promise.all(
    stages.map(({ stage, config, withPractice }) => {
      // Each test type knows where its trials hold their audio. Practice
      // stimuli/trials are sampled independently of the session's, so they
      // may reference audio files the session list doesn't - preflight them
      // too, through the same method on a config-shaped view of the subset.
      const TestClass = testClassFor(config);
      const practice = withPractice
        ? TestClass.audioStimuli({
            ...config,
            stimuli: config.practice_stimuli,
            trials: config.practice_trials,
          })
        : [];
      const urls = [...practice, ...TestClass.audioStimuli(config)].map((s) => stage.audioUrl(s));
      return Promise.all([checkAudioFiles(urls), checkSaveEndpoint(stage.url('save.php'))]);
    })
  );
  const missing = checks.flatMap(([stageMissing]) => stageMissing);
  const saveErrors = [...new Set(checks.map(([, error]) => error).filter(Boolean))];
  return { missing, saveErrors };
}
