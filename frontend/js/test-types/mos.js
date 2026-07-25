/**
 * MOS (Mean Opinion Score) listening test UI.
 *
 * Displays one stimulus per page - the only test type whose page holds a
 * single clip, so it builds on ListeningTest directly rather than on
 * PairedTrialTest's multi-clip machinery. Listeners must play each audio
 * file to completion before rating buttons become active (playback-gated
 * rating). All keyboard shortcuts are configurable via the server-side
 * YAML config.
 */

import {
  audioPlayerHtml,
  bindAudioPlayer,
  resetAudioPlayer,
  rewindAudio,
} from '../audio-player.js';
import { escapeHtml } from '../dom.js';
import { ratingKeysHint } from '../hints.js';
import { submitPayload } from '../submit.js';
import { ListeningTest } from './listening-test.js';

const MOS_LABELS_DEFAULT = { 1: 'Bad', 2: 'Poor', 3: 'Fair', 4: 'Good', 5: 'Excellent' };

export class MOSTest extends ListeningTest {
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    this.stimuli = config.stimuli;
    this.ratings = new Map(); // stimulus id → rating value
    this.played = new Set(); // stimulus ids played to completion (enables rating)
    this.shortcuts = config.shortcuts ?? {
      rating: { 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 },
      next: ['ArrowRight'],
      prev: ['ArrowLeft'],
      submit: 'Enter',
    };
    this.mosLabels = config.rating_labels
      ? Object.fromEntries(Object.entries(config.rating_labels).map(([k, v]) => [Number(k), v]))
      : MOS_LABELS_DEFAULT;
  }

  _trialCount() {
    return this.stimuli.length;
  }

  _isAnswered(index) {
    return this.ratings.has(this.stimuli[index].id);
  }

  _answeredCount() {
    return this.ratings.size;
  }

  /**
   * Build the stimulus-page DOM once and cache references to the parts that
   * change between stimuli. Navigation then mutates these in place (_syncPage)
   * rather than replacing innerHTML, so the native <audio> control is never
   * recreated - eliminating the flicker that a full re-render caused.
   */
  _buildPage() {
    const ratingButtons = [1, 2, 3, 4, 5]
      .map(
        (v) => `
      <button class="rating-btn" data-value="${v}" type="button">
        <span class="rating-score">${v}</span>
        <span class="rating-word">${escapeHtml(this.mosLabels[v] ?? '')}</span>
      </button>
    `
      )
      .join('');

    this._pageSlot.innerHTML = `
      <div class="stimulus-page">
        <span class="stimulus-label"></span>
        <div class="audio-card">
          ${audioPlayerHtml(0, this.config.audio_preload)}
          <p class="audio-error" hidden>⚠ Audio file could not be loaded. Please contact the administrator.</p>
        </div>
        <div class="rating-section">
          <div class="listen-steps">
            <span class="step-listen">① Listen</span>
            <span class="step-sep">→</span>
            <span class="step-rate">② Rate</span>
          </div>
          <div class="rating-buttons">${ratingButtons}</div>
        </div>
        <div class="navigation">
          <button class="btn btn-secondary" id="btn-prev" type="button">← Prev</button>
          <button class="btn btn-primary" id="btn-next" type="button"></button>
        </div>
        <p class="shortcut-hint"></p>
      </div>
    `;

    this._el = {
      counter: this.container.querySelector('.page-counter'),
      label: this._pageSlot.querySelector('.stimulus-label'),
      audio: this._pageSlot.querySelector('audio'),
      player: this._pageSlot.querySelector('.audio-player'),
      audioError: this._pageSlot.querySelector('.audio-error'),
      ratingSection: this._pageSlot.querySelector('.rating-section'),
      ratingBtns: [...this._pageSlot.querySelectorAll('.rating-btn')],
      prev: this._pageSlot.querySelector('#btn-prev'),
      next: this._pageSlot.querySelector('#btn-next'),
      hint: this._pageSlot.querySelector('.shortcut-hint'),
    };

    this._bindPersistentEvents();
  }

  /** Bind listeners once to the persistent page elements (see _buildPage). */
  _bindPersistentEvents() {
    for (const btn of this._el.ratingBtns) {
      btn.addEventListener('click', () => {
        const s = this.stimuli[this.currentIndex];
        this._setRating(s.id, Number.parseInt(btn.dataset.value, 10));
        // Drop focus so a subsequent Enter reaches the document-level confirm
        // shortcut (advance/submit) instead of re-activating this button.
        btn.blur();
      });
    }

    const { audio } = this._el;
    // The custom player owns the play button, icon, and progress bar.
    bindAudioPlayer(audio);

    // Show a visible error if the browser cannot load the current audio file;
    // _syncPage hides it again (and retries the load) on the next navigation.
    audio.addEventListener('error', () => {
      this._el.player.hidden = true;
      this._el.audioError.hidden = false;
    });

    // Enable rating only after the listener has heard the full current sample.
    audio.addEventListener('ended', () => {
      const s = this.stimuli[this.currentIndex];
      if (!this.played.has(s.id)) {
        this.played.add(s.id);
        this._syncRatingState();
        this._onChange?.();
      }
    });

    this._el.prev.addEventListener('click', () => this._navigate(-1));
    this._el.next.addEventListener('click', () => this._nextOrSubmit());
  }

  /** Update the persistent page elements to reflect the current stimulus. */
  _syncPage() {
    const s = this.stimuli[this.currentIndex];

    this._el.label.textContent = s.label ?? '';

    // Swap only the src on the persistent <audio>, rewound to the start, and
    // reset the custom player's icon/progress.
    const url = s.audio_url ?? `/audio/${encodeURIComponent(s.id)}`;
    if (this._el.audio.getAttribute('src') !== url) {
      this._el.audio.src = url;
    } else {
      this._el.audio.pause();
      if (this._el.audio.currentTime !== 0) this._el.audio.currentTime = 0;
    }
    // Served duration for the current clip, so the time bar shows length
    // immediately (no '--' flicker) before the audio metadata loads.
    this._el.audio.dataset.duration = this.config.durations?.[s.id] ?? '';
    resetAudioPlayer(this._el.audio);
    this._el.player.hidden = false;
    this._el.audioError.hidden = true;

    this._syncRatingState();
    this._syncChrome();
  }

  /** Sync the rating buttons' selected/enabled state to the current stimulus. */
  _syncRatingState() {
    const s = this.stimuli[this.currentIndex];
    const rated = this.ratings.get(s.id);
    const canRate = this._canRate(s.id);
    for (const btn of this._el.ratingBtns) {
      btn.classList.toggle('selected', Number.parseInt(btn.dataset.value, 10) === rated);
      btn.disabled = !canRate;
    }
    this._el.ratingSection.classList.toggle('played', canRate);
  }

  _canRate(stimulusId) {
    return this.played.has(stimulusId);
  }

  /** Record a rating and reflect it on the buttons and Next state in place. */
  _setRating(stimulusId, value) {
    this.ratings.set(stimulusId, value);

    for (const btn of this._el.ratingBtns) {
      btn.classList.toggle('selected', Number.parseInt(btn.dataset.value, 10) === value);
    }

    this._syncNextEnabled();
    this._updateProgressBar();
    this._onChange?.();
  }

  /** The resume record's two halves: ratings by stimulus id, and heard ids. */
  _serializeAnswers() {
    return [...this.ratings];
  }

  _restoreAnswers(saved) {
    this.ratings = new Map(saved);
  }

  _serializePlayed() {
    return [...this.played];
  }

  _restorePlayed(saved) {
    this.played = new Set(saved);
  }

  // -- keyboard shortcuts ----------------------------------------------------

  /** The page holds a single clip, so the play shortcut just toggles it. */
  _handlePlayShortcut() {
    const audio = this._el?.audio;
    if (!audio) return;
    audio.paused ? audio.play() : audio.pause();
  }

  _handleRewindShortcut() {
    const audio = this._el?.audio;
    if (audio) rewindAudio(audio);
  }

  /** Rating keys: record the current stimulus's rating when playback-gating allows. */
  _handleChoiceKey(e) {
    const { shortcuts } = this;
    if (!Object.hasOwn(shortcuts.rating, e.key)) return false;
    e.preventDefault();
    const s = this.stimuli[this.currentIndex];
    if (this._canRate(s.id)) this._setRating(s.id, shortcuts.rating[e.key]);
    return true;
  }

  /** The rating-key segment of ListeningTest's shortcut hint. */
  _choiceHintHtml() {
    return `${ratingKeysHint(this.shortcuts.rating)} rate`;
  }

  async _submit() {
    // system/item are never sent: the server enriches each rating from
    // its own stimulus map, and the config response withholds both anyway.
    await submitPayload(this, () => ({
      ratings: Array.from(this.ratings.entries()).map(([stimulus_id, rating]) => ({
        stimulus_id,
        rating,
      })),
    }));
  }
}
