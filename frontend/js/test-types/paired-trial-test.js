/**
 * Shared base for playback-gated, paired-trial listening tests (AB, ABX, XAB,
 * CMOS, DMOS): one trial per page, sequential prev/next navigation gated on a
 * choice being made, a progress bar, and the trial header.
 *
 * The page DOM is built once (_buildPage) and updated in place on every
 * navigation (_syncPage) rather than rebuilt, and each clip uses a custom
 * player (audio-player.js) around a bare <audio> - so nothing flickers on
 * prev/next and there's no native control to right-click-save. Subclasses
 * supply the type-specific pieces via hooks: _audioRegionHtml, _choiceButtonsHtml,
 * _ratingButtonsClass, _listenStepsHtml, _trialAudioClips, _syncChoiceButtons,
 * _onChoiceButton, _canChoose, _handleChoiceKey, _choiceHintHtml, _submit.
 * MUSHRA overrides _buildPage/_syncPage entirely (sliders, no native controls).
 */

import {
  audioPlayerHtml,
  bindAudioPlayer,
  resetAudioPlayer,
  rewindAudio,
} from '../audio-player.js';
import { escapeHtml } from '../dom.js';
import {
  finalButtonLabel,
  finalConfirmHint,
  practiceBadgeHtml,
  practiceBannerHtml,
  practiceCounterPrefix,
} from '../practice.js';

export class PairedTrialTest {
  constructor(config, sessionId, onSubmit) {
    this.config = config;
    this.sessionId = sessionId;
    this.onSubmit = onSubmit;
    this.trials = config.trials;
    this.currentIndex = 0;
    this.choices = new Map();
    this.played = new Map(); // trial index → Set of played local indices
    this._playCursor = new Map(); // trial index → audios[] position last started via the play shortcut
    this._boundKeydown = this._handleKeydown.bind(this);
  }

  /** Mount the header, build the trial page DOM once, then sync it to the first trial. */
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
    this.container.appendChild(this._pageSlot);
  }

  // -- Build once / sync in place (choice-button test types) ----------------

  /**
   * Build the static trial-page structure once and cache references to the
   * parts that change per trial. Subclasses provide the audio region and
   * choice buttons; navigation then mutates these in place (see _syncPage).
   */
  _buildPage() {
    this._pageSlot.innerHTML = `
      <div class="stimulus-page">
        <div class="stimulus-meta">
          <span class="page-counter"></span>
        </div>
        ${this._audioRegionHtml()}
        <div class="rating-section">
          <div class="listen-steps">${this._listenStepsHtml()}</div>
          <div class="rating-buttons ${this._ratingButtonsClass()}">${this._choiceButtonsHtml()}</div>
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
      ratingSection: this._pageSlot.querySelector('.rating-section'),
      buttons: [...this._pageSlot.querySelectorAll('.rating-btn')],
      audios: [...this._pageSlot.querySelectorAll('audio')],
      prev: this._pageSlot.querySelector('#btn-prev'),
      next: this._pageSlot.querySelector('#btn-next'),
      hint: this._pageSlot.querySelector('.shortcut-hint'),
    };

    for (const btn of this._el.buttons) {
      btn.addEventListener('click', () => {
        this._onChoiceButton(btn);
        // Drop focus so a subsequent Enter reaches the document-level confirm
        // shortcut (advance/submit) instead of re-activating this button.
        btn.blur();
      });
    }
    for (const audio of this._el.audios) {
      this._bindAudioElement(audio);
    }
    this._el.prev.addEventListener('click', () => this._navigate(-1));
    this._el.next.addEventListener('click', () => this._nextOrSubmit());
  }

  /** Resolve a stimulus's audio URL (server audio_url, else the FastAPI /audio route). */
  _audioUrl(s) {
    return s.audio_url ?? `/audio/${encodeURIComponent(s.id)}`;
  }

  /** A clip descriptor {url, id} for _trialAudioClips; id resolves the served duration. */
  _clip(s) {
    return { url: this._audioUrl(s), id: s.id };
  }

  /** One blinded audio card (persistent custom player; only its src changes per trial). */
  _audioCardHtml(label, localIndex) {
    const preload = this.config.audio_preload;
    return `
      <div class="audio-card">
        <span class="audio-card-label">${label}</span>
        ${audioPlayerHtml(localIndex, preload)}
        <p class="audio-error" hidden>⚠ Audio file could not be loaded. Please contact the administrator.</p>
      </div>
    `;
  }

  _bindAudioElement(audio) {
    const localIndex =
      audio.dataset.localIndex === 'x' ? 'x' : Number.parseInt(audio.dataset.localIndex, 10);

    // The custom player owns the play button, icon, and progress bar.
    bindAudioPlayer(audio);
    audio.addEventListener('play', () => this._recordPlayCursor(audio));

    // Show a per-card error without destroying the persistent <audio>;
    // _syncAudioSrcs restores it (and retries the load) on the next trial.
    audio.addEventListener('error', () => {
      const card = audio.closest('.audio-card');
      card.querySelector('.audio-player').hidden = true;
      card.querySelector('.audio-error').hidden = false;
    });

    // Enable choosing once every clip in the trial has been heard.
    audio.addEventListener('ended', () => {
      const played = this._playedSet(this.currentIndex);
      if (!played.has(localIndex)) {
        played.add(localIndex);
        if (this._canChoose(this.currentIndex)) this._enableChoosing();
        this._onChange?.();
      }
    });
  }

  _enableChoosing() {
    for (const btn of this._el.buttons) btn.disabled = false;
    this._el.ratingSection.classList.add('played');
  }

  /** Update the persistent page elements to reflect the current trial. */
  _syncPage() {
    const total = this.trials.length;
    const current = this.currentIndex + 1;
    const isLast = this.currentIndex === total - 1;

    this._el.counter.textContent = `${practiceCounterPrefix(this.config)}${current} / ${total}`;
    this._syncAudioSrcs();
    this._syncChoiceButtons();
    this._el.ratingSection.classList.toggle('played', this._canChoose(this.currentIndex));
    this._el.prev.disabled = this.currentIndex === 0;
    this._el.next.textContent = isLast ? finalButtonLabel(this.config) : 'Next →';
    this._el.hint.innerHTML = this._shortcutHintHtml(isLast);
    this._syncNextEnabled();
    this._updateProgressBar();
    this._onChange?.();
  }

  /**
   * Point a persistent <audio> at the current trial's url, rewound to the
   * start. A changed src resets currentTime to 0 via the load algorithm (and,
   * with preload="none", won't fetch until play). When the src is unchanged
   * across trials (e.g. DMOS reuses one Reference for several test systems),
   * the element would otherwise keep the previous play's ended position, so
   * rewind it explicitly - only when already loaded, so no extra fetch.
   */
  _resetAudio(audio, url) {
    if (url != null && audio.getAttribute('src') !== url) {
      audio.src = url;
    } else {
      audio.pause();
      if (audio.currentTime !== 0) audio.currentTime = 0;
    }
  }

  /** Swap only the src on each persistent <audio> for the current trial. */
  _syncAudioSrcs() {
    const clips = this._trialAudioClips(this.trials[this.currentIndex]);
    for (const audio of this._el.audios) {
      const clip = clips[audio.dataset.localIndex];
      this._resetAudio(audio, clip.url);
      // Served duration keeps the time bar from flickering '--' on swap. A clip
      // with no id (ABX's hidden X reference) is marked 'hidden' so its length
      // is never shown - revealing it would leak which stimulus X duplicates.
      audio.dataset.duration =
        clip.id == null ? 'hidden' : (this.config.durations?.[clip.id] ?? '');
      resetAudioPlayer(audio);
      const card = audio.closest('.audio-card');
      card.querySelector('.audio-player').hidden = false;
      card.querySelector('.audio-error').hidden = true;
    }
  }

  /** Enable Next/Submit: current trial chosen (intermediate) or all chosen (last). */
  _syncNextEnabled() {
    const isLast = this.currentIndex === this.trials.length - 1;
    const allChosen = this.choices.size === this.trials.length;
    this._el.next.disabled = isLast ? !allChosen : !this.choices.has(this.currentIndex);
  }

  /** Record a choice and reflect it on the buttons and Next state in place. */
  _setChoice(trialIndex, value) {
    this.choices.set(trialIndex, value);
    this._syncChoiceButtons();
    this._syncNextEnabled();
    this._updateProgressBar();
    this._onChange?.();
  }

  /**
   * Serialize progress for resume: current trial, choices, and which clips of
   * each trial have been heard (so restored answered trials aren't re-gated).
   * Choice values are JSON-safe (numbers or the 'tie' string), as are played
   * local indices (numbers, or 'x' for ABX).
   */
  getProgress() {
    return {
      currentIndex: this.currentIndex,
      answers: [...this.choices],
      played: [...this.played].map(([index, set]) => [index, [...set]]),
    };
  }

  /** Restore serialized progress (see getProgress) and re-sync the page. */
  restoreProgress(saved) {
    this.choices = new Map(saved.answers ?? []);
    this.played = new Map((saved.played ?? []).map(([index, arr]) => [index, new Set(arr)]));
    this.currentIndex = Math.min(saved.currentIndex ?? 0, this.trials.length - 1);
    this._syncPage();
  }

  _playedSet(index) {
    if (!this.played.has(index)) this.played.set(index, new Set());
    return this.played.get(index);
  }

  /** Move to an adjacent page; forward navigation is blocked without a choice. */
  _navigate(delta) {
    if (delta > 0 && !this.choices.has(this.currentIndex)) return;
    const next = this.currentIndex + delta;
    if (next < 0 || next >= this.trials.length) return;
    this.currentIndex = next;
    this._syncPage();
  }

  _nextOrSubmit() {
    const isLast = this.currentIndex === this.trials.length - 1;
    if (isLast) {
      if (this.choices.size === this.trials.length) this._submit();
    } else {
      this._navigate(1);
    }
  }

  _updateProgressBar() {
    const pct = (this.choices.size / this.trials.length) * 100;
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = `${pct}%`;
  }

  /**
   * Toggle/advance playback across this trial's audio clips: pause whichever
   * clip is currently playing, or otherwise resume/start the right one.
   * While any clip hasn't been played to completion yet, that's always the
   * target (so pausing partway through and pressing the shortcut again
   * resumes the SAME clip, rather than skipping ahead). Once every clip has
   * been played at least once, cycles back through them in the same order
   * (A → B → X → A → …) - unless the most recently started one was itself
   * paused partway through a repeat listen, in which case it resumes that
   * one first. Mirrors MOSTest's single-clip Space shortcut, generalized to
   * multiple clips.
   */
  _handlePlayShortcut() {
    const audios = [...this._pageSlot.querySelectorAll('audio')];
    if (audios.length === 0) return;

    const playing = audios.find((a) => !a.paused);
    if (playing) {
      playing.pause();
      return;
    }

    const localIndexOf = (a) =>
      a.dataset.localIndex === 'x' ? 'x' : Number.parseInt(a.dataset.localIndex, 10);
    const played = this._playedSet(this.currentIndex);
    const unplayed = audios.find((a) => !played.has(localIndexOf(a)));

    let target = unplayed;
    if (!target) {
      // Every clip has been played to completion at least once, so `played`
      // can no longer tell us whether the most recently started clip (this
      // repeat listen) finished or was only paused partway through - check
      // the clip itself instead of skipping past a stopped-mid-way clip.
      const lastPos = this._playCursor.get(this.currentIndex) ?? -1;
      const lastStarted = lastPos >= 0 ? audios[lastPos] : null;
      // Without resume there is nothing to come back to, so the shortcut
      // advances to the next clip instead of re-targeting the paused one.
      const resumable =
        this._supportsResume() && lastStarted && lastStarted.currentTime > 0 && !lastStarted.ended;
      target = resumable ? lastStarted : audios[(lastPos + 1) % audios.length];
    }
    this._startPlayback(target);
  }

  /**
   * Start playback of one clip. The seam the play shortcut goes through
   * (MUSHRA routes its own play buttons through it too; the standard
   * player's button is bound in audio-player.js and always resumes).
   */
  _startPlayback(audio) {
    if (!this._supportsResume()) rewindAudio(audio);
    audio.play();
  }

  /** Record that `audio` is the clip most recently started, for _handlePlayShortcut's cycling. */
  _recordPlayCursor(audio) {
    const audios = [...this._pageSlot.querySelectorAll('audio')];
    this._playCursor.set(this.currentIndex, audios.indexOf(audio));
  }

  /**
   * Whether pausing preserves the playback position. When false (MUSHRA),
   * one concept drives three behaviors: every start plays from the beginning
   * (_startPlayback), the play shortcut advances to the NEXT clip after a
   * pause rather than re-targeting the paused one (_handlePlayShortcut), and
   * the rewind shortcut/hint are dropped as redundant - restarting is what
   * plain play already does.
   */
  _supportsResume() {
    return true;
  }

  /**
   * Rewind the clip the listener is (or was most recently) listening to:
   * the currently playing clip if any, else the one last started via the
   * play cursor. A no-op before anything has been started on this trial -
   * every clip is still at its beginning then.
   */
  _handleRewindShortcut() {
    const audios = [...this._pageSlot.querySelectorAll('audio')];
    const playing = audios.find((a) => !a.paused);
    const lastPos = this._playCursor.get(this.currentIndex) ?? -1;
    const target = playing ?? (lastPos >= 0 ? audios[lastPos] : null);
    if (target) rewindAudio(target);
  }

  // -- keyboard shortcuts ----------------------------------------------------

  /**
   * Shared document-level keydown handler: the play shortcut, then the
   * type-specific choice keys (via _handleChoiceKey), then prev/next/confirm.
   */
  _handleKeydown(e) {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (tag === 'BUTTON' && e.key === 'Enter') return;

    const { shortcuts } = this;

    // play shortcut toggles/advances audio playback regardless of which
    // element has focus.
    const playKey = shortcuts.play === 'Space' ? ' ' : shortcuts.play;
    if (e.key === playKey) {
      e.preventDefault();
      this._handlePlayShortcut();
      return;
    }
    if (e.key === shortcuts.rewind && this._supportsResume()) {
      e.preventDefault();
      this._handleRewindShortcut();
      return;
    }

    if (this._handleChoiceKey(e)) return;

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

  /** Apply a matched choice-shortcut key: consume it, record the choice if playback-gating allows. */
  _applyChoiceKey(e, value) {
    e.preventDefault();
    if (this._canChoose(this.currentIndex)) this._setChoice(this.currentIndex, value);
    return true;
  }

  /**
   * Handle a type-specific choice key; returns true when the key was consumed.
   * Default: the choose-A/B keys shared by AB (which adds tie on top), ABX,
   * and XAB. CMOS/DMOS override with their rating maps; MUSHRA opts out.
   */
  _handleChoiceKey(e) {
    const { shortcuts } = this;
    if (e.key === shortcuts.choose_a) return this._applyChoiceKey(e, 0);
    if (e.key === shortcuts.choose_b) return this._applyChoiceKey(e, 1);
    return false;
  }

  /**
   * Build the shortcut hint from the live shortcuts config so the hint stays
   * accurate when the YAML config overrides default key bindings; the
   * type-specific middle segment comes from _choiceHintHtml().
   *
   * @param {boolean} isLast - Whether this is the final trial page.
   * @returns {string} HTML string for the hint paragraph content.
   */
  _shortcutHintHtml(isLast) {
    const { shortcuts } = this;
    const playKey = escapeHtml(shortcuts.play);
    const rewindKey = escapeHtml(shortcuts.rewind);
    const prevKey = shortcuts.prev === 'ArrowLeft' ? '←' : escapeHtml(shortcuts.prev);
    const nextKey = shortcuts.next === 'ArrowRight' ? '→' : escapeHtml(shortcuts.next);
    const confirmKey = shortcuts.confirm === 'Enter' ? 'Enter' : escapeHtml(shortcuts.confirm);
    const segments = [
      `<kbd>${playKey}</kbd> play/pause`,
      ...(this._supportsResume() ? [`<kbd>${rewindKey}</kbd> rewind`] : []),
      this._choiceHintHtml(),
      `<kbd>${prevKey}</kbd><kbd>${nextKey}</kbd> navigate`,
      `<kbd>${confirmKey}</kbd> ${isLast ? finalConfirmHint(this.config) : 'next'}`,
    ];
    return segments.join(' &nbsp;·&nbsp;');
  }

  /** The type-specific middle segment of the shortcut hint; default matches _handleChoiceKey's choose-A/B keys. */
  _choiceHintHtml() {
    const { shortcuts } = this;
    return `<kbd>${escapeHtml(shortcuts.choose_a)}</kbd> choose A, <kbd>${escapeHtml(shortcuts.choose_b)}</kbd> choose B`;
  }
}
