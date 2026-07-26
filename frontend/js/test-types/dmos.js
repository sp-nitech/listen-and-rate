/**
 * DMOS (rating relative to a reference) listening test UI.
 *
 * Displays one trial (a Reference clip and a Test clip, same item) per
 * page. Listeners must play both clips to completion before rating buttons
 * become active (playback-gated rating), mirroring MOSTest's 1-5 scale.
 * Unlike ABX's hidden "X", the Reference/Test roles are never blinded - the
 * listener is explicitly told which clip is which. All keyboard shortcuts
 * are configurable via the server-side YAML config.
 */

import { escapeHtml } from '../dom.js';
import { ratingKeysHint } from '../hints.js';
import { submitPayload } from '../submit.js';
import { PairedTrialTest } from './paired-trial-test.js';

const DMOS_LABELS_DEFAULT = {
  5: 'Imperceptible',
  4: 'Not annoying',
  3: 'Slightly annoying',
  2: 'Annoying',
  1: 'Very annoying',
};

export class DMOSTest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {ratings}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    // choices: trial index → rating value (1-5)
    // played: trial index → Set of local indices (0 = reference, 1 = test)
    this.shortcuts = config.shortcuts ?? {
      play: 'Space',
      rating: { 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 },
      prev: 'ArrowLeft',
      next: 'ArrowRight',
      confirm: 'Enter',
    };
    this.dmosLabels = config.rating_labels
      ? Object.fromEntries(Object.entries(config.rating_labels).map(([k, v]) => [Number(k), v]))
      : DMOS_LABELS_DEFAULT;
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
    return '';
  }

  _audioRegionHtml() {
    return `<div class="ab-pair">${this._audioCardHtml('Reference', 0)}${this._audioCardHtml('Test', 1)}</div>`;
  }

  _choiceButtonsHtml() {
    return [1, 2, 3, 4, 5]
      .map(
        (v) => `
      <button class="rating-btn" data-value="${v}" type="button">
        <span class="rating-score">${v}</span>
        <span class="rating-word">${escapeHtml(this.dmosLabels[v] ?? '')}</span>
      </button>
    `
      )
      .join('');
  }

  // -- per-trial sync -------------------------------------------------------

  _trialAudioClips(trial) {
    return { 0: this._clip(trial.reference), 1: this._clip(trial.test) };
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
    return this._playedSet(trialIndex).size >= 2;
  }

  /** DMOS rates via its 1-5 rating map rather than the base choose-A/B keys. */
  _handleChoiceKey(e) {
    const { rating } = this.shortcuts;
    if (Object.hasOwn(rating, e.key)) return this._applyChoiceKey(e, rating[e.key]);
    return false;
  }

  _choiceHintHtml() {
    return `${ratingKeysHint(this.shortcuts.rating)} rate`;
  }

  async _submit() {
    await submitPayload(this, () => ({
      ratings: Array.from(this.choices.entries()).map(([trialIndex, rating]) => {
        const trial = this.trials[trialIndex];
        return {
          stimulus_id: trial.test.id,
          reference_id: trial.reference.id,
          rating,
          response_time: this._responseTimeOf(trialIndex),
        };
      }),
    }));
  }
}
