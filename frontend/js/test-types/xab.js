/**
 * XAB (similarity to a reference) listening test UI.
 *
 * Displays one trial (a disclosed reference X on top, then a pair of
 * same-utterance samples from two systems below - the inverse layout of
 * ABX) per page. Listeners must play all three clips to completion before
 * choosing which of A/B sounds closer to X (playback-gated, forced
 * two-way choice - no tie).
 *
 * Unlike ABX, X is an independent reference recording served like any
 * other stimulus - there is no hidden-duplicate token machinery. A/B's
 * position within a trial is already randomized server-side, so the labels
 * here are purely positional ("A"/"B"), never system names. All keyboard
 * shortcuts are configurable via the server-side YAML config.
 */

import { submitPayload } from '../submit.js';
import { PairedTrialTest } from './paired-trial-test.js';

const SAMPLE_LETTERS = ['A', 'B'];

export class XABTest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {choices}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    // choices: trial index → closer local index (0/1)
    // played: trial index → Set of local indices (0/1/'x') played to completion
    this.shortcuts = config.shortcuts ?? {
      play: 'Space',
      choose_a: '1',
      choose_b: '2',
      prev: 'ArrowLeft',
      next: 'ArrowRight',
      confirm: 'Enter',
    };
  }

  // -- build-once structure -------------------------------------------------

  _stimulusLabel(current) {
    return `Audio Set ${current}`;
  }

  _listenStepsHtml() {
    return `
      <span class="step-listen">① Listen to X, A, and B</span>
      <span class="step-sep">→</span>
      <span class="step-rate">② Choose</span>
    `;
  }

  _ratingButtonsClass() {
    return 'ab-choice-buttons';
  }

  _audioRegionHtml() {
    const pairCards = SAMPLE_LETTERS.map((letter, i) => this._audioCardHtml(letter, i)).join('');
    return `
      <div class="abx-x-pair">${this._audioCardHtml('X (Reference)', 'x')}</div>
      <div class="ab-pair">${pairCards}</div>
    `;
  }

  _choiceButtonsHtml() {
    return SAMPLE_LETTERS.map(
      (letter, i) => `
      <button class="rating-btn ab-choice-btn" data-choice="${i}" type="button">
        <span class="rating-score">${letter}</span>
        <span class="rating-word">${letter} is closer</span>
      </button>
    `
    ).join('');
  }

  // -- per-trial sync -------------------------------------------------------

  _trialAudioClips(trial) {
    return {
      x: this._clip(trial.reference),
      0: this._clip(trial.stimuli[0]),
      1: this._clip(trial.stimuli[1]),
    };
  }

  _syncChoiceButtons() {
    const choice = this.choices.get(this.currentIndex);
    const canChoose = this._canChoose(this.currentIndex);
    for (const btn of this._el.buttons) {
      btn.classList.toggle('selected', Number.parseInt(btn.dataset.choice, 10) === choice);
      btn.disabled = !canChoose;
    }
  }

  _onChoiceButton(btn) {
    this._setChoice(this.currentIndex, Number.parseInt(btn.dataset.choice, 10));
  }

  _canChoose(trialIndex) {
    // 3 clips per trial: X, A, and B.
    return this._playedSet(trialIndex).size >= 3;
  }

  // Keyboard shortcuts: the base class's choose-A/B keydown handling and
  // shortcut hint are used as-is.

  async _submit() {
    await submitPayload(this, () => ({
      choices: Array.from(this.choices.entries()).map(([trialIndex, value]) => {
        const stimulus_ids = this.trials[trialIndex].stimuli.map((s) => s.id);
        return {
          stimulus_ids,
          selected_stimulus_id: stimulus_ids[value],
        };
      }),
    }));
  }
}
