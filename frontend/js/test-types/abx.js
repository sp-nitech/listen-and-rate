/**
 * ABX (discrimination) listening test UI.
 *
 * Displays one trial (A, B, and a hidden "X" reference - a duplicate of
 * either A or B) per page. Listeners must play all three clips to
 * completion before choosing which of A/B they believe X matches
 * (playback-gated choice), mirroring ABTest's UX.
 *
 * X's audio is resolved server-side from an opaque token (see
 * listen_and_rate/x_token.py) - its URL is never the same as A's or
 * B's own URL, and the token is never interpreted client-side, only echoed
 * back verbatim at submit time. A/B's position within a trial is already
 * randomized server-side. All keyboard shortcuts are configurable via the
 * server-side YAML config.
 */

import { submitPayload } from '../submit.js';
import { PairedTrialTest } from './paired-trial-test.js';

const SAMPLE_LETTERS = ['A', 'B'];

export class ABXTest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {choices}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    // choices: trial index → matched local index (0/1)
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

  /** Build X's audio URL from its opaque token - never the same URL as A's/B's own. */
  _xAudioUrl(trial) {
    const [idA, idB] = trial.stimuli.map((s) => s.id);
    const params = new URLSearchParams({ token: trial.x.token, a: idA, b: idB });
    return `audio_x.php?${params.toString()}`;
  }

  // -- build-once structure -------------------------------------------------

  _listenStepsHtml() {
    return `
      <span class="step-listen">① Listen to A, B, and X</span>
      <span class="step-sep">→</span>
      <span class="step-rate">② Choose</span>
    `;
  }

  _ratingButtonsClass() {
    return 'ab-choice-buttons';
  }

  _audioRegionHtml() {
    const referenceCards = SAMPLE_LETTERS.map((letter, i) => this._audioCardHtml(letter, i)).join(
      ''
    );
    return `
      <div class="ab-pair abx-references">${referenceCards}</div>
      <div class="abx-x-pair">${this._audioCardHtml('X', 'x')}</div>
    `;
  }

  _choiceButtonsHtml() {
    return SAMPLE_LETTERS.map(
      (letter, i) => `
      <button class="rating-btn ab-choice-btn" data-choice="${i}" type="button">
        <span class="rating-score">${letter}</span>
        <span class="rating-word">${letter} is X</span>
      </button>
    `
    ).join('');
  }

  // -- per-trial sync -------------------------------------------------------

  _trialAudioClips(trial) {
    return {
      0: this._clip(trial.stimuli[0]),
      1: this._clip(trial.stimuli[1]),
      // The X reference is a hidden duplicate of stimulus 0 or 1; showing its
      // length would leak which, so id is null - _syncAudioSrcs marks it
      // 'hidden' and the readout never reveals a total for it.
      x: { url: this._xAudioUrl(trial), id: null },
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
    // 3 clips per trial: A, B, and X.
    return this._playedSet(trialIndex).size >= 3;
  }

  // Keyboard shortcuts: the base class's choose-A/B keydown handling and
  // shortcut hint are used as-is.

  async _submit() {
    await submitPayload(this, () => ({
      choices: Array.from(this.choices.entries()).map(([trialIndex, value]) => {
        const trial = this.trials[trialIndex];
        const stimulus_ids = trial.stimuli.map((s) => s.id);
        return {
          stimulus_ids,
          selected_stimulus_id: stimulus_ids[value],
          x_token: trial.x.token,
          response_time: this._responseTimeOf(trialIndex),
        };
      }),
    }));
  }
}
