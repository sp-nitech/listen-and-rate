/**
 * MOS (Mean Opinion Score) listening test UI.
 *
 * Displays one stimulus per page. Listeners must play each audio file to
 * completion before rating buttons become active (playback-gated rating).
 * All keyboard shortcuts are configurable via the server-side YAML config.
 */

import {
  audioPlayerHtml,
  bindAudioPlayer,
  resetAudioPlayer,
  rewindAudio,
} from '../audio-player.js';
import { escapeHtml } from '../dom.js';
import { ratingKeysHint } from '../hints.js';
import {
  finalButtonLabel,
  finalConfirmHint,
  practiceBadgeHtml,
  practiceBannerHtml,
  practiceCounterPrefix,
} from '../practice.js';
import { submitPayload } from '../submit.js';

const MOS_LABELS_DEFAULT = { 1: 'Bad', 2: 'Poor', 3: 'Fair', 4: 'Good', 5: 'Excellent' };

export class MOSTest {
  /**
   * @param {Object} config - Server config from /api/config.
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, ratings).
   */
  constructor(config, sessionId, onSubmit) {
    this.config = config;
    this.sessionId = sessionId;
    this.onSubmit = onSubmit;
    this.stimuli = config.stimuli;
    this.currentIndex = 0;
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
    this._boundKeydown = this._handleKeydown.bind(this);
  }

  /** Mount the test header, build the stimulus page DOM once, then sync it. */
  render(container) {
    this.container = container;
    this._renderHeader();
    this._buildPage();
    this._syncPage();
    document.addEventListener('keydown', this._boundKeydown);
  }

  _renderHeader() {
    const header = document.createElement('div');
    header.className = 'test-header';
    header.innerHTML = `
      <h1>${escapeHtml(this.config.title)}${practiceBadgeHtml(this.config)}</h1>
      ${practiceBannerHtml(this.config)}
      <p class="instructions">${escapeHtml(this.config.instructions)}</p>
    `;
    this.container.appendChild(header);
    this._pageSlot = document.createElement('div');
    this._pageSlot.className = 'page-slot';
    this.container.appendChild(this._pageSlot);
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
        <div class="stimulus-meta">
          <span class="page-counter"></span>
          <span class="stimulus-label"></span>
        </div>
        <div class="audio-card">
          ${audioPlayerHtml(0, this.config.preload_audio ? 'auto' : 'none')}
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
      counter: this._pageSlot.querySelector('.page-counter'),
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
    const total = this.stimuli.length;
    const current = this.currentIndex + 1;
    const isFirst = this.currentIndex === 0;
    const isLast = this.currentIndex === total - 1;

    this._el.counter.textContent = `${practiceCounterPrefix(this.config)}${current} / ${total}`;
    this._el.label.textContent = s.label ?? `Audio Sample ${current}`;

    // Swap only the src on the persistent <audio>, rewound to the start, and
    // reset the custom player's icon/progress.
    const url = s.audio_url ?? `/audio/${encodeURIComponent(s.id)}`;
    if (this._el.audio.getAttribute('src') !== url) {
      this._el.audio.src = url;
    } else {
      this._el.audio.pause();
      if (this._el.audio.currentTime !== 0) this._el.audio.currentTime = 0;
    }
    resetAudioPlayer(this._el.audio);
    this._el.player.hidden = false;
    this._el.audioError.hidden = true;

    this._syncRatingState();

    this._el.prev.disabled = isFirst;
    this._el.next.textContent = isLast ? finalButtonLabel(this.config) : 'Next →';
    this._el.hint.innerHTML = this._shortcutHintHtml(isLast);
    this._syncNextEnabled();

    this._updateProgressBar();
    this._onChange?.();
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

  /** Enable Next/Submit per the gating rule (current rated, or all rated on the last page). */
  _syncNextEnabled() {
    const s = this.stimuli[this.currentIndex];
    const isLast = this.currentIndex === this.stimuli.length - 1;
    const allRated = this.ratings.size === this.stimuli.length;
    this._el.next.disabled = isLast ? !allRated : !this.ratings.has(s.id);
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

  /** Serialize progress for resume: current page, ratings, and heard stimuli. */
  getProgress() {
    return {
      currentIndex: this.currentIndex,
      answers: [...this.ratings],
      played: [...this.played],
    };
  }

  /** Restore serialized progress (see getProgress) and re-sync the page. */
  restoreProgress(saved) {
    this.ratings = new Map(saved.answers ?? []);
    this.played = new Set(saved.played ?? []);
    this.currentIndex = Math.min(saved.currentIndex ?? 0, this.stimuli.length - 1);
    this._syncPage();
  }

  /** Move to an adjacent page; forward navigation is blocked without a rating. */
  _navigate(delta) {
    if (delta > 0 && !this.ratings.has(this.stimuli[this.currentIndex].id)) return;
    const next = this.currentIndex + delta;
    if (next < 0 || next >= this.stimuli.length) return;
    this.currentIndex = next;
    this._syncPage();
  }

  _nextOrSubmit() {
    const isLast = this.currentIndex === this.stimuli.length - 1;
    if (isLast) {
      if (this.ratings.size === this.stimuli.length) this._submit();
    } else {
      this._navigate(1);
    }
  }

  _handleKeydown(e) {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    // Let buttons handle their own Enter activation; Space is reserved for audio below.
    if (tag === 'BUTTON' && e.key === 'Enter') return;

    // play shortcut toggles audio play/pause regardless of which element has focus.
    const playKey = this.shortcuts.play === 'Space' ? ' ' : this.shortcuts.play;
    if (e.key === playKey) {
      e.preventDefault();
      const audio = this._el?.audio;
      if (audio) {
        audio.paused ? audio.play() : audio.pause();
      }
      return;
    }
    if (e.key === this.shortcuts.rewind) {
      e.preventDefault();
      const audio = this._el?.audio;
      if (audio) rewindAudio(audio);
      return;
    }

    const { shortcuts } = this;
    const s = this.stimuli[this.currentIndex];

    if (Object.hasOwn(shortcuts.rating, e.key)) {
      e.preventDefault();
      if (this._canRate(s.id)) this._setRating(s.id, shortcuts.rating[e.key]);
      return;
    }
    if (e.key === shortcuts.next) {
      e.preventDefault();
      this._navigate(1);
      return;
    }
    if (e.key === shortcuts.prev) {
      e.preventDefault();
      this._navigate(-1);
      return;
    }
    if (e.key === shortcuts.confirm) {
      e.preventDefault();
      this._nextOrSubmit();
    }
  }

  /**
   * Build the shortcut hint text from the live shortcuts config so the hint
   * stays accurate when the YAML config overrides default key bindings.
   *
   * @param {boolean} isLast - Whether this is the final stimulus page.
   * @returns {string} HTML string for the hint paragraph content.
   */
  _shortcutHintHtml(isLast) {
    const { shortcuts } = this;
    const ratingHint = ratingKeysHint(shortcuts.rating);
    const prevKey = shortcuts.prev === 'ArrowLeft' ? '←' : escapeHtml(shortcuts.prev);
    const nextKey = shortcuts.next === 'ArrowRight' ? '→' : escapeHtml(shortcuts.next);
    const confirmKey = shortcuts.confirm === 'Enter' ? 'Enter' : escapeHtml(shortcuts.confirm);
    const playKey = escapeHtml(shortcuts.play);
    const rewindKey = escapeHtml(shortcuts.rewind);
    return `<kbd>${playKey}</kbd> play/pause &nbsp;·&nbsp;<kbd>${rewindKey}</kbd> rewind &nbsp;·&nbsp;${ratingHint} rate &nbsp;·&nbsp;<kbd>${prevKey}</kbd><kbd>${nextKey}</kbd> navigate &nbsp;·&nbsp;<kbd>${confirmKey}</kbd> ${isLast ? finalConfirmHint(this.config) : 'next'}`;
  }

  _updateProgressBar() {
    const pct = (this.ratings.size / this.stimuli.length) * 100;
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = `${pct}%`;
  }

  async _submit() {
    // system/utterance are never sent: the server enriches each rating from
    // its own stimulus map, and the config response withholds both anyway.
    await submitPayload(this, () => ({
      ratings: Array.from(this.ratings.entries()).map(([stimulus_id, rating]) => ({
        stimulus_id,
        rating,
      })),
    }));
  }
}
