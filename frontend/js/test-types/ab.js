/**
 * AB (paired forced-choice preference) listening test UI.
 *
 * Displays one trial (a pair of same-utterance samples from two systems) per
 * page. Listeners must play both clips to completion before the choice
 * buttons become active (playback-gated choice), mirroring MOSTest's UX.
 * Sample position within a trial is already randomized server-side, so the
 * labels here are purely positional ("A"/"B"), never system names. All
 * keyboard shortcuts are configurable via the server-side YAML config.
 */

import { escapeHtml } from '../dom.js';
import { submitPayload } from '../submit.js';
import { PairedTrialTest } from './paired-trial-test.js';

const SAMPLE_LETTERS = ['A', 'B'];

export class ABTest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`, `allow_tie`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {choices}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    this.allowTie = config.allow_tie ?? true;
    // choices: trial index → preferred local index (0/1) or 'tie'
    this.shortcuts = config.shortcuts ?? {
      play: 'Space',
      choose_a: '1',
      choose_b: '2',
      tie: '3',
      prev: 'ArrowLeft',
      next: 'ArrowRight',
      confirm: 'Enter',
    };
  }

  // -- build-once structure -------------------------------------------------

  _stimulusLabel(current) {
    return `Audio Pair ${current}`;
  }

  _listenStepsHtml() {
    return `
      <span class="step-listen">① Listen to both</span>
      <span class="step-sep">→</span>
      <span class="step-rate">② Choose</span>
    `;
  }

  _ratingButtonsClass() {
    return 'ab-choice-buttons';
  }

  _audioRegionHtml() {
    return `<div class="ab-pair">${SAMPLE_LETTERS.map((letter, i) => this._audioCardHtml(letter, i)).join('')}</div>`;
  }

  _choiceButtonsHtml() {
    const choiceButtons = SAMPLE_LETTERS.map(
      (letter, i) => `
      <button class="rating-btn ab-choice-btn" data-choice="${i}" type="button">
        <span class="rating-score">${letter}</span>
        <span class="rating-word">Prefer ${letter}</span>
      </button>
    `
    ).join('');
    const tieButton = this.allowTie
      ? `
      <button class="rating-btn ab-choice-btn" data-choice="tie" type="button">
        <span class="rating-score">=</span>
        <span class="rating-word">Same</span>
      </button>
    `
      : '';
    return `${choiceButtons}${tieButton}`;
  }

  // -- per-trial sync -------------------------------------------------------

  _trialAudioSrcs(trial) {
    return { 0: this._audioUrl(trial.stimuli[0]), 1: this._audioUrl(trial.stimuli[1]) };
  }

  _syncChoiceButtons() {
    const choice = this.choices.get(this.currentIndex);
    const canChoose = this._canChoose(this.currentIndex);
    for (const btn of this._el.buttons) {
      const raw = btn.dataset.choice;
      const value = raw === 'tie' ? 'tie' : Number.parseInt(raw, 10);
      btn.classList.toggle('selected', value === choice);
      btn.disabled = !canChoose;
    }
  }

  _onChoiceButton(btn) {
    const raw = btn.dataset.choice;
    this._setChoice(this.currentIndex, raw === 'tie' ? 'tie' : Number.parseInt(raw, 10));
  }

  _canChoose(trialIndex) {
    const trial = this.trials[trialIndex];
    return this._playedSet(trialIndex).size >= trial.stimuli.length;
  }

  /** The base choose-A/B keys, plus AB's tie response when enabled. */
  _handleChoiceKey(e) {
    if (super._handleChoiceKey(e)) return true;
    if (this.allowTie && e.key === this.shortcuts.tie) return this._applyChoiceKey(e, 'tie');
    return false;
  }

  _choiceHintHtml() {
    const tieHint = this.allowTie ? `, <kbd>${escapeHtml(this.shortcuts.tie)}</kbd> same` : '';
    return `${super._choiceHintHtml()}${tieHint}`;
  }

  async _submit() {
    await submitPayload(this, () => ({
      choices: Array.from(this.choices.entries()).map(([trialIndex, value]) => {
        const stimulus_ids = this.trials[trialIndex].stimuli.map((s) => s.id);
        const selected_stimulus_id = value === 'tie' ? null : stimulus_ids[value];
        return { stimulus_ids, selected_stimulus_id };
      }),
    }));
  }
}
