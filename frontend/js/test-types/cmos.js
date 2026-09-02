/**
 * CMOS (comparative MOS / ITU-T P.800 CCR) listening test UI.
 *
 * Displays one trial (a pair of same-item samples from two systems) per
 * page, labeled purely positionally ("A"/"B") like ABTest - never system
 * names, since which system plays in which position is randomized
 * server-side per trial. Listeners must play both clips to completion before
 * rating buttons become active (playback-gated rating), mirroring MOSTest's
 * UX. The listener rates how B compares to A on a signed 7-point scale
 * (-3 much worse .. +3 much better); the server determines the canonical
 * system_a/system_b assignment and flips the sign if needed. All keyboard
 * shortcuts are configurable via the server-side YAML config.
 */

import { escapeHtml } from '../dom.js';
import { ratingKeysHint } from '../hints.js';
import { t } from '../strings.js';
import { submitPayload } from '../submit.js';
import { PairedTrialTest } from './paired-trial-test.js';

const SAMPLE_LETTERS = ['A', 'B'];

const CMOS_RATING_VALUES = [-3, -2, -1, 0, 1, 2, 3];

const CMOS_LABELS_DEFAULT = {
  '-3': 'Much worse',
  '-2': 'Worse',
  '-1': 'Slightly worse',
  0: 'About the same',
  1: 'Slightly better',
  2: 'Better',
  3: 'Much better',
};

/**
 * Format a signed rating value for the button display: 0 -> "0", 2 -> "+2",
 * and a negative like -2 to the digit prefixed with the typographic MINUS SIGN
 * (U+2212), not the ASCII hyphen-minus JS would otherwise produce: the hyphen
 * glyph is short and sits high, reading off-center next to the full,
 * math-axis-centered "+".
 */
function formatScore(v) {
  if (v > 0) return `+${v}`;
  if (v < 0) return `\u2212${Math.abs(v)}`;
  return `${v}`;
}

export class CMOSTest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {choices}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    // choices: trial index → rating value (-3..3)
    // played: trial index → Set of local indices (0 = A, 1 = B)
    this.shortcuts = config.shortcuts ?? {
      play: 'Space',
      rating: { 1: -3, 2: -2, 3: -1, 4: 0, 5: 1, 6: 2, 7: 3 },
      prev: 'ArrowLeft',
      next: 'ArrowRight',
      confirm: 'Enter',
    };
    this.cmosLabels = config.rating_labels ?? CMOS_LABELS_DEFAULT;
  }

  // -- build-once structure -------------------------------------------------

  _listenStepsHtml() {
    return `
      <span class="step-listen">① Listen to both</span>
      <span class="step-sep">→</span>
      <span class="step-rate">② Rate</span>
    `;
  }

  _ratingButtonsClass() {
    return 'cmos-rating-buttons';
  }

  _audioRegionHtml() {
    return `<div class="ab-pair">${SAMPLE_LETTERS.map((letter, i) => this._audioCardHtml(letter, i)).join('')}</div>`;
  }

  _choiceButtonsHtml() {
    return CMOS_RATING_VALUES.map(
      (v) => `
      <button class="rating-btn" data-value="${v}" type="button">
        <span class="rating-score">${formatScore(v)}</span>
        <span class="rating-word">${escapeHtml(this.cmosLabels[v] ?? '')}</span>
      </button>
    `
    ).join('');
  }

  // -- per-trial sync -------------------------------------------------------

  _trialAudioClips(trial) {
    return { 0: this._clip(trial.stimuli[0]), 1: this._clip(trial.stimuli[1]) };
  }

  _syncChoiceButtons() {
    const rated = this.choices.get(this.currentIndex);
    const canChoose = this._canChoose(this.currentIndex);
    for (const btn of this._el.buttons) {
      btn.classList.toggle('selected', Number.parseInt(btn.dataset.value, 10) === rated);
      btn.disabled = !canChoose;
    }
  }

  _onChoiceButton(btn) {
    this._setChoice(this.currentIndex, Number.parseInt(btn.dataset.value, 10));
  }

  _canChoose(trialIndex) {
    const trial = this.trials[trialIndex];
    return this._playedSet(trialIndex).size >= trial.stimuli.length;
  }

  /** CMOS rates via its signed rating map rather than the base choose-A/B keys. */
  _handleChoiceKey(e) {
    const { rating } = this.shortcuts;
    if (Object.hasOwn(rating, e.key)) return this._applyChoiceKey(e, rating[e.key]);
    return false;
  }

  _choiceHintHtml() {
    return `${ratingKeysHint(this.shortcuts.rating)} ${t('trial_hint_rate')}`;
  }

  async _submit() {
    await submitPayload(this, () => ({
      choices: Array.from(this.choices.entries()).map(([trialIndex, rating]) => {
        const stimulus_ids = this.trials[trialIndex].stimuli.map((s) => s.id);
        return {
          stimulus_ids,
          rating,
          response_time: this._responseTimeOf(trialIndex),
        };
      }),
    }));
  }
}
