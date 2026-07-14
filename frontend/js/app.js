/**
 * Entry point: fetches config, selects the appropriate test class, and
 * renders the test into #app. Shows an error screen on any failure.
 */

import { fetchConfig, submitRatings } from './api.js';
import { escapeHtml } from './dom.js';
import { MetadataPage } from './metadata.js';
import { runPracticeStage } from './practice.js';
import { clearRecord, isResumable, loadRecord, recordKey, saveRecord } from './resume.js';
import { generateSessionId } from './session.js';
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
    return config.trials.flatMap((t) => [t.reference, t.test]);
  }
  if (config.test_type === 'cmos' || config.test_type === 'ab' || config.test_type === 'abx') {
    return config.trials.flatMap((t) => t.stimuli);
  }
  if (config.test_type === 'xab') {
    return config.trials.flatMap((t) => [t.reference, ...t.stimuli]);
  }
  if (config.test_type === 'mushra') {
    return config.trials.flatMap((t) => [t.reference, ...t.systems, t.anchor].filter(Boolean));
  }
  return config.stimuli;
}

/**
 * HEAD-request each stimulus audio URL in parallel.
 *
 * @param {Array<{id: string, audio_url?: string}>} stimuli
 * @returns {Promise<string[]>} URLs that returned a non-OK response or threw.
 */
async function checkAudioFiles(stimuli) {
  const results = await Promise.all(
    stimuli.map(async (s) => {
      const url = s.audio_url ?? `/audio/${encodeURIComponent(s.id)}`;
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
 * @returns {Promise<string|null>} Error message, or null if writable.
 */
async function checkSaveEndpoint() {
  try {
    const res = await fetch('save.php');
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
  const total = (record.config?.stimuli ?? record.config?.trials ?? []).length;
  const page = (record.progress?.currentIndex ?? 0) + 1;
  const progressHint =
    total > 0 ? `<p>You were on item ${Math.min(page, total)} of ${total}.</p>` : '';

  container.innerHTML = `
    <div class="resume-screen">
      <h2>Resume previous session?</h2>
      <p>An unfinished session was found on this device.</p>
      ${progressHint}
      <div class="resume-actions">
        <button class="btn btn-primary" id="btn-resume" type="button">Resume</button>
        <button class="btn btn-secondary" id="btn-restart" type="button">Start over</button>
      </div>
    </div>
  `;

  return new Promise((resolve) => {
    container.querySelector('#btn-resume').addEventListener('click', () => resolve(true));
    container.querySelector('#btn-restart').addEventListener('click', () => resolve(false));
  });
}

async function main() {
  const freshConfig = await fetchConfig();
  const container = document.getElementById('app');
  const key = recordKey(freshConfig.experiment_id);

  // Offer resume only when a saved session still matches the current config
  // (fingerprint) and hasn't gone stale (>2h since the last activity).
  const saved = loadRecord(key);
  let resume = false;
  if (isResumable(saved, freshConfig.config_version, Date.now())) {
    resume = await promptResume(container, saved);
    if (!resume) clearRecord(key);
  }

  // On resume, use the frozen config the session was started with - re-fetching
  // would re-sample and re-shuffle into a different test (and re-mint x tokens).
  const config = resume ? saved.config : freshConfig;
  document.title = config.title;

  // Practice stimuli/trials are sampled independently of the session's, so
  // they may reference audio files the session list doesn't - preflight them
  // too, reusing flatStimuli on a config-shaped view of the practice subset.
  // (Practice is skipped on resume, so only preflight it on a fresh start.)
  const hasPractice = !resume && (config.practice_stimuli ?? config.practice_trials)?.length > 0;
  const practiceStimuli = hasPractice
    ? flatStimuli({
        ...config,
        stimuli: config.practice_stimuli,
        trials: config.practice_trials,
      })
    : [];
  const [missing, saveError] = await Promise.all([
    checkAudioFiles([...practiceStimuli, ...flatStimuli(config)]),
    checkSaveEndpoint(),
  ]);

  const errors = [];
  if (saveError) errors.push(`<p><strong>Result saving:</strong> ${escapeHtml(saveError)}</p>`);
  if (missing.length > 0)
    errors.push(`
    <p><strong>${missing.length} audio file(s) not accessible:</strong></p>
    <ul class="error-list">
      ${missing.map((u) => `<li><code>${escapeHtml(u)}</code></li>`).join('')}
    </ul>
  `);

  if (errors.length > 0) {
    container.innerHTML = `
      <div class="error-screen">
        <h2>Cannot start test</h2>
        ${errors.join('')}
      </div>
    `;
    return;
  }

  const TestClass = testTypeMap[config.test_type];
  if (!TestClass) throw new Error(`Unknown test type: "${config.test_type}"`);

  const sessionId = resume ? saved.sessionId : generateSessionId();
  container.innerHTML = '';

  let listenerMetadata = resume ? (saved.metadata ?? {}) : {};
  if (!resume && config.metadata?.length > 0) {
    const metaPage = new MetadataPage(config.metadata);
    listenerMetadata = await metaPage.collect(container);
    container.innerHTML = '';
  }

  if (hasPractice) {
    await runPracticeStage(config, sessionId, TestClass, container);
    container.innerHTML = '';
    // The practice round fills the shared progress bar; the real test must
    // start back at zero.
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = '0%';
  }

  // Persist the whole delivered config plus current answers/position after
  // every state change, so the session can be resumed if the tab is closed.
  const persist = (test) => {
    saveRecord(key, {
      v: 1,
      fingerprint: config.config_version,
      savedAt: Date.now(),
      sessionId,
      config,
      metadata: listenerMetadata,
      progress: test.getProgress(),
    });
  };

  async function onSubmit(sid, testType, payload) {
    await submitRatings({
      session_id: sid,
      test_type: testType,
      experiment_id: config.experiment_id ?? '',
      metadata: listenerMetadata,
      ...payload,
    });
    // The session is complete - it must never be offered for resume again.
    clearRecord(key);
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = '100%';
    document.getElementById('app').innerHTML = `
      <div class="complete-screen">
        <div class="complete-icon">✓</div>
        <h2>Thank you!</h2>
        <p>Your ratings have been saved successfully.</p>
      </div>
    `;
  }

  // Server already shuffles (randomize is always false in the response), so
  // this is defensive-only and only applies to MOS's flat stimuli list.
  if (config.randomize && config.stimuli) {
    for (let i = config.stimuli.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [config.stimuli[i], config.stimuli[j]] = [config.stimuli[j], config.stimuli[i]];
    }
  }

  const test = new TestClass(config, sessionId, onSubmit);
  test._onChange = () => persist(test);
  test.render(container);
  if (resume) test.restoreProgress(saved.progress);
}

main().catch((err) => {
  document.getElementById('app').innerHTML = `
    <div class="error-screen">
      <h2>Failed to load test</h2>
      <p>${escapeHtml(err.message)}</p>
    </div>
  `;
});
