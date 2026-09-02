/**
 * Shared base for the playback-gated, multi-clip listening tests (AB, ABX,
 * XAB, CMOS, DMOS, MUSHRA): one trial per page, several clips per trial, and
 * choosing gated on every clip having been heard. Navigation, the progress
 * bar, the resume record, and the keyboard handler come from ListeningTest;
 * this layer adds the clip handling those types share.
 *
 * The page DOM is built once (_buildPage) and updated in place on every
 * navigation (_syncPage) rather than rebuilt, and each clip uses a custom
 * player (audio-player.js) around a bare <audio> - so nothing flickers on
 * prev/next and there's no native control to right-click-save. Subclasses
 * supply the type-specific pieces via hooks: _audioRegionHtml, _choiceButtonsHtml,
 * _ratingButtonsClass, _listenStepsHtml, _trialAudioClips, _syncChoiceButtons,
 * _onChoiceButton, _canChoose, plus ListeningTest's own hooks.
 * MUSHRA overrides _buildPage/_syncPage entirely (sliders, no native controls).
 */

import {
  audioPlayerHtml,
  bindAudioPlayer,
  resetAudioPlayer,
  rewindAudio,
} from '../audio-player.js';
import { escapeHtml } from '../dom.js';
import { t } from '../strings.js';
import { ListeningTest } from './listening-test.js';

export class PairedTrialTest extends ListeningTest {
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    this.trials = config.trials;
    this.choices = new Map();
    this.played = new Map(); // trial index → Set of played local indices
    this._playCursor = new Map(); // trial index → audios[] position last started via the play shortcut
  }

  _trialCount() {
    return this.trials.length;
  }

  _isAnswered(index) {
    return this.choices.has(index);
  }

  _answeredCount() {
    return this.choices.size;
  }

  /**
   * Every clip of the trial: _canChoose waits for all of them to reach
   * 'ended', so that whole stretch is time the listener had no choice about.
   *
   * A clip's own element carries the length even where the served durations
   * do not - ABX withholds its hidden X's, and the browser knows it anyway
   * (see listen_and_rate/x_token.py's threat model).
   */
  _gatedSeconds(index) {
    const clips = this._trialAudioClips(this.trials[index]);
    let total = 0;
    for (const audio of this._el?.audios ?? []) {
      const clip = clips[audio.dataset.localIndex];
      const served = clip?.id == null ? null : this.config.durations?.[clip.id];
      const length = served ?? audio.duration;
      if (Number.isFinite(length)) total += length;
    }
    return total;
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
        ${this._audioRegionHtml()}
        <div class="rating-section">
          <div class="listen-steps">${this._listenStepsHtml()}</div>
          <div class="rating-buttons ${this._ratingButtonsClass()}">${this._choiceButtonsHtml()}</div>
        </div>
        <div class="navigation">
          <button class="btn btn-secondary" id="btn-prev" type="button">${t('trial_prev')}</button>
          <button class="btn btn-primary" id="btn-next" type="button"></button>
        </div>
        <p class="shortcut-hint"></p>
      </div>
    `;

    this._el = {
      counter: this.container.querySelector('.page-counter'),
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
    this._syncAudioSrcs();
    this._syncChoiceButtons();
    this._el.ratingSection.classList.toggle('played', this._canChoose(this.currentIndex));
    this._syncChrome();
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

  /** Record a choice and reflect it on the buttons and Next state in place. */
  _setChoice(trialIndex, value) {
    this.choices.set(trialIndex, value);
    this._syncChoiceButtons();
    this._syncNextEnabled();
    this._updateProgressBar();
    this._onChange?.();
  }

  /**
   * The resume record's two halves. Choice values are JSON-safe (numbers or
   * the 'tie' string), as are played local indices (numbers, or 'x' for ABX);
   * played is per trial so restored answered trials aren't re-gated.
   */
  _serializeAnswers() {
    return [...this.choices];
  }

  _restoreAnswers(saved) {
    this.choices = new Map(saved);
  }

  _serializePlayed() {
    return [...this.played].map(([index, set]) => [index, [...set]]);
  }

  _restorePlayed(saved) {
    this.played = new Map(saved.map(([index, arr]) => [index, new Set(arr)]));
  }

  _playedSet(index) {
    if (!this.played.has(index)) this.played.set(index, new Set());
    return this.played.get(index);
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

  /** The type-specific middle segment of the shortcut hint; default matches _handleChoiceKey's choose-A/B keys. */
  _choiceHintHtml() {
    const { shortcuts } = this;
    return `<kbd>${escapeHtml(shortcuts.choose_a)}</kbd> ${t('trial_hint_chooseA')}, <kbd>${escapeHtml(shortcuts.choose_b)}</kbd> ${t('trial_hint_chooseB')}`;
  }
}
