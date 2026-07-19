/**
 * MUSHRA (ITU-R BS.1534) listening test UI.
 *
 * Displays one trial (all rateable systems' clips for one utterance, plus
 * an optional Reference clip) per page, with one vertical 0-100 slider per
 * rateable system, all laid out in a single horizontal row alongside a
 * shared tick/band-label axis (rendered once, not per slider). The
 * Reference (if configured) is a non-rateable, always-leftmost playback
 * clip - never a slider. The Anchor (if configured) is always rightmost
 * among the sliders and labeled "Anchor"; every other system is blind (no
 * label) and server-shuffled.
 *
 * The page is built once and updated in place on navigation (no full
 * re-render): the column layout is fixed across trials (same reference
 * presence, same slider count), so each trial only swaps audio srcs, the
 * per-column stimulus id, slider values, and unlock state.
 *
 * Each slider unlocks the moment its own clip STARTS playing, so listeners
 * can adjust the rating while the clip is still sounding. With a Reference
 * configured, every other clip's play button stays disabled (dimmed) until
 * the Reference has been heard to completion once - the reference anchors
 * the scale, so it must come first. Next/Submit requires every slider to
 * have been explicitly moved at least once; that transitively requires
 * hearing the Reference and starting every clip, so no separate
 * played-to-completion gate is needed. Playback never resumes mid-clip
 * (_supportsResume is false): every start plays from the beginning and the
 * play shortcut advances to the next clip after a pause, so successive
 * plays compare the same passage across systems.
 */

import { PAUSE_SVG, PLAY_SVG } from '../audio-player.js';
import { escapeHtml } from '../dom.js';
import { finalButtonLabel, practiceCounterPrefix } from '../practice.js';
import { submitPayload } from '../submit.js';
import { PairedTrialTest } from './paired-trial-test.js';

const MUSHRA_BAND_ORDER = ['80', '60', '40', '20', '0']; // top(100) → bottom(0) band lower-bounds
const MUSHRA_LABELS_DEFAULT = {
  0: 'Bad',
  20: 'Poor',
  40: 'Fair',
  60: 'Good',
  80: 'Excellent',
};
const MUSHRA_TICKS = [100, 80, 60, 40, 20, 0];

/**
 * Whether Shift is a FREE modifier for the given configured key - i.e. not
 * consumed by typing the key itself. Only then can Shift+key mean "big step":
 * for an uppercase letter (or a shifted symbol like "%"), producing the key
 * already requires Shift, so the x10 multiplier is not offered and (in the
 * hint) not advertised. Named keys (ArrowUp, ...) and Space are unaffected
 * by Shift, so they qualify.
 */
function shiftIsFree(key) {
  return key.length > 1 || key === ' ';
}

/** Reset a play button to its idle look (play icon, no now-playing marker). */
function resetPlayButton(btn) {
  btn.innerHTML = PLAY_SVG;
  btn.classList.remove('is-playing');
}

export class MUSHRATest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {ratings}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    // choices: trial index → Map<stimulus_id, value> (one trial has N sliders)
    // played: trial index → Set of local indices whose listening requirement
    // is met (reused from PairedTrialTest, persisted for resume). The
    // requirement differs per role: the Reference must play to COMPLETION
    // (it anchors the scale and gates the other play buttons); a slider's
    // clip only has to START (its slider unlocks so the listener can rate
    // while listening).
    this.shortcuts = config.shortcuts ?? {
      play: 'Space',
      prev: 'ArrowLeft',
      next: 'ArrowRight',
      confirm: 'Enter',
      rate_up: 'ArrowUp',
      rate_down: 'ArrowDown',
    };
    this.bandLabels = config.rating_labels
      ? { ...MUSHRA_LABELS_DEFAULT, ...config.rating_labels }
      : MUSHRA_LABELS_DEFAULT;
  }

  /** All rateable (slider-bearing) stimuli for a trial, in render order: blind systems, then the anchor last. */
  _sliderStimuli(trial) {
    return trial.anchor ? [...trial.systems, trial.anchor] : trial.systems;
  }

  // -- build once -----------------------------------------------------------

  /**
   * Build the fixed column layout once (axis, optional reference, N sliders)
   * and cache the elements each trial updates. All trials share this shape;
   * _syncPage swaps only per-trial content (audio srcs, stimulus ids, values,
   * unlock state).
   */
  _buildPage() {
    const trial0 = this.trials[0];
    this._hasReference = !!trial0.reference;
    this._hasAnchor = !!trial0.anchor;
    const sliderCount = this._sliderStimuli(trial0).length;
    const preload = this.config.audio_preload;

    // Ticks/bands are positioned as percentages of the track's own height
    // (not fixed pixels), so they always land exactly on the gridlines drawn
    // on .mushra-track-row (also percentage-based) regardless of the track's
    // actual height (220px desktop, shorter on mobile).
    const tickHtml = MUSHRA_TICKS.map(
      (t, i) => `<span style="top:${(i * 100) / (MUSHRA_TICKS.length - 1)}%">${t}</span>`
    ).join('');
    const bandHtml = MUSHRA_BAND_ORDER.map((k, i) => {
      const bandPct = 100 / MUSHRA_BAND_ORDER.length;
      const top = i * bandPct + bandPct / 2;
      return `<span style="top:${top}%">${escapeHtml(this.bandLabels[k] ?? '')}</span>`;
    }).join('');
    const axisColHtml = `
      <div class="mushra-col mushra-axis-col">
        <div class="mushra-track-row">
          <div class="mushra-tick-col">${tickHtml}</div>
          <div class="mushra-band-col">${bandHtml}</div>
        </div>
      </div>
    `;

    // Reference's/Anchor's labels are absolutely-positioned tabs straddling
    // the card's top border - not a row of their own - so columns without a
    // label stay vertically aligned. Playback uses a compact square button,
    // not the browser's native <audio controls> bar (the <audio> here has no
    // `controls` attribute), keeping every column narrow enough for the
    // shared gridlines to read as one continuous grid.
    const referenceColHtml = this._hasReference
      ? `
      <div class="mushra-col mushra-reference-col">
        <span class="audio-card-label">Reference</span>
        <div class="mushra-track-row">
          <div class="mushra-range-fixed" aria-hidden="true">
            <div class="mushra-range-fill" style="height:100%"></div>
            <div class="mushra-range-thumb" style="top:0%"></div>
          </div>
        </div>
        <div class="mushra-value-row"><span class="mushra-slider-value">100</span></div>
        <div class="mushra-audio-row">
          <button class="mushra-play-btn" type="button" aria-label="Play Reference clip">${PLAY_SVG}</button>
          <audio data-local-index="0" preload="${preload}"></audio>
        </div>
      </div>
    `
      : '';

    // A hand-built slider (track div + thumb div), not a native
    // <input type=range>: positioning our own thumb via the exact same
    // `top: (100-value)%` math the gridlines use guarantees they always line
    // up exactly (native vertical range thumbs are inset from the track ends).
    const sliderColsHtml = Array.from({ length: sliderCount }, (_, i) => {
      const localIndex = (this._hasReference ? 1 : 0) + i;
      const isAnchorCol = this._hasAnchor && i === sliderCount - 1;
      return `
        <div class="mushra-col mushra-slider-col">
          ${isAnchorCol ? '<span class="audio-card-label">Anchor</span>' : ''}
          <div class="mushra-track-row">
            <div class="mushra-range is-disabled" role="slider"
                 aria-orientation="vertical" aria-valuemin="0" aria-valuemax="100"
                 aria-valuenow="0" aria-disabled="true" tabindex="-1"
                 data-local-index="${localIndex}" data-value="0">
              <div class="mushra-range-track">
                <div class="mushra-range-fill" style="height:0%"></div>
                <div class="mushra-range-thumb" style="top:100%"></div>
              </div>
            </div>
          </div>
          <div class="mushra-value-row"><span class="mushra-slider-value">0</span></div>
          <div class="mushra-audio-row">
            <button class="mushra-play-btn" type="button" aria-label="Play clip">${PLAY_SVG}</button>
            <audio data-local-index="${localIndex}" preload="${preload}"></audio>
          </div>
        </div>
      `;
    }).join('');

    const stepsHtml = this._hasReference
      ? `
      <div class="listen-steps">
        <span class="step-listen">① Listen to reference</span>
        <span class="step-sep">→</span>
        <span class="step-rate">② Listen to others and rate</span>
      </div>
    `
      : `
      <div class="listen-steps">
        <span class="step-listen">① Listen and rate</span>
      </div>
    `;

    this._pageSlot.innerHTML = `
      <div class="stimulus-page">
        <div class="stimulus-meta">
          <span class="page-counter"></span>
          <span class="stimulus-label"></span>
        </div>
        ${stepsHtml}
        <div class="mushra-trial">
          ${axisColHtml}
          ${referenceColHtml}
          ${sliderColsHtml}
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
      steps: this._pageSlot.querySelector('.listen-steps'),
      sliderCols: [...this._pageSlot.querySelectorAll('.mushra-slider-col')],
      referenceAudio: this._pageSlot.querySelector('.mushra-reference-col audio'),
      prev: this._pageSlot.querySelector('#btn-prev'),
      next: this._pageSlot.querySelector('#btn-next'),
      hint: this._pageSlot.querySelector('.shortcut-hint'),
    };

    this._bindPageEvents();
  }

  _bindPageEvents() {
    for (const range of this._pageSlot.querySelectorAll('.mushra-range')) {
      this._bindRangeSlider(range);
    }

    for (const audio of this._pageSlot.querySelectorAll('audio')) {
      const localIndex = Number.parseInt(audio.dataset.localIndex, 10);
      const playBtn = audio.parentElement.querySelector('.mushra-play-btn');
      const isReference = !!audio.closest('.mushra-reference-col');

      // A slider clip's listening requirement is met the moment it STARTS:
      // unlock its slider right away so the listener can rate while the clip
      // is still sounding. (The Reference has no slider; its requirement is
      // completion, handled in 'ended' below.)
      audio.addEventListener('play', () => {
        this._recordPlayCursor(audio);
        if (playBtn) {
          playBtn.innerHTML = PAUSE_SVG;
          // Now-playing marker (solid primary fill via CSS .is-playing).
          playBtn.classList.add('is-playing');
        }
        if (isReference) return;
        const played = this._playedSet(this.currentIndex);
        if (!played.has(localIndex)) {
          played.add(localIndex);
          const range = audio.closest('.mushra-slider-col')?.querySelector('.mushra-range');
          if (range) {
            range.classList.remove('is-disabled');
            range.setAttribute('aria-disabled', 'false');
            range.tabIndex = 0;
          }
          this._onChange?.();
        }
      });
      audio.addEventListener('pause', () => {
        if (playBtn) resetPlayButton(playBtn);
      });

      audio.addEventListener('error', () => {
        audio.closest('.mushra-col')?.classList.add('audio-error-state');
      });

      // The Reference anchors the rating scale, so it must be heard to
      // completion once before anything else: only then are the other play
      // buttons enabled (and the step indicator advanced to step ②).
      audio.addEventListener('ended', () => {
        // Browsers fire 'pause' before 'ended' (which already resets the
        // button), but reset here too so neither the icon nor the marker
        // can ever stick after a natural end.
        if (playBtn) resetPlayButton(playBtn);
        if (!isReference) return;
        const played = this._playedSet(this.currentIndex);
        if (!played.has(localIndex)) {
          played.add(localIndex);
          this._onChange?.();
        }
        this._setSystemPlayButtonsEnabled(true);
        this._el.steps?.classList.add('played');
      });

      if (playBtn) {
        playBtn.addEventListener('click', () => {
          if (audio.paused) {
            // Only one clip plays at a time - pause whatever else is playing.
            for (const other of this._pageSlot.querySelectorAll('audio')) {
              if (other !== audio && !other.paused) other.pause();
            }
            this._startPlayback(audio);
          } else {
            audio.pause();
          }
        });
      }
    }

    this._el.prev.addEventListener('click', () => this._navigate(-1));
    this._el.next.addEventListener('click', () => this._nextOrSubmit());
  }

  // -- per-trial sync -------------------------------------------------------

  /**
   * Enable/disable every system clip's play button (never the Reference's).
   * Disabled buttons are dimmed via CSS (.mushra-play-btn:disabled) while the
   * Reference hasn't been heard to completion yet.
   */
  _setSystemPlayButtonsEnabled(enabled) {
    for (const col of this._el.sliderCols) {
      const btn = col.querySelector('.mushra-play-btn');
      if (btn) btn.disabled = !enabled;
    }
  }

  /** Step size for one rate keypress: x10 with Shift, but only when Shift isn't consumed producing `key`. */
  _rateStep(e, key) {
    return e.shiftKey && shiftIsFree(key) ? 10 : 1;
  }

  /**
   * Show whether this slider has been rated yet. Unrated sliders hide their
   * thumb/fill (CSS .is-unrated) and read "–" instead of a number - a thumb
   * parked at 0 with a "0" readout could be misread as a deliberate
   * lowest-possible score rather than "not rated yet". aria-valuetext keeps
   * the same distinction audible: without it a screen reader would announce
   * the placeholder aria-valuenow of 0 as if it were a real score.
   */
  _setSliderRated(range, hasRating) {
    range.classList.toggle('is-unrated', !hasRating);
    if (hasRating) {
      range.removeAttribute('aria-valuetext');
    } else {
      range.setAttribute('aria-valuetext', 'not rated yet');
      const valueEl = range.closest('.mushra-slider-col')?.querySelector('.mushra-slider-value');
      if (valueEl) valueEl.textContent = '–';
    }
  }

  /**
   * The single write path for every user-initiated rating: clamp the value,
   * update the slider DOM, mark it rated, and record the choice. Pointer
   * drags pass an absolute value; the rate keys go through _nudgeSlider.
   */
  _applySliderValue(range, rawValue) {
    const value = Math.max(0, Math.min(100, Math.round(rawValue)));
    this._setSliderValue(range, value);
    this._setSliderRated(range, true);
    this._setChoice(this.currentIndex, range.dataset.stimulusId, value);
  }

  /** Step a slider's value by delta relative to its current position. */
  _nudgeSlider(range, delta) {
    this._applySliderValue(range, Number.parseInt(range.dataset.value, 10) + delta);
  }

  /** Apply value to a hand-built slider's DOM (thumb, fill, readout, aria/data). */
  _setSliderValue(range, value) {
    range.dataset.value = String(value);
    range.setAttribute('aria-valuenow', String(value));
    const thumb = range.querySelector('.mushra-range-thumb');
    if (thumb) thumb.style.top = `${100 - value}%`;
    const fill = range.querySelector('.mushra-range-fill');
    if (fill) fill.style.height = `${value}%`;
    const valueEl = range.closest('.mushra-slider-col')?.querySelector('.mushra-slider-value');
    if (valueEl) valueEl.textContent = String(value);
  }

  _syncPage() {
    const trial = this.trials[this.currentIndex];
    const total = this.trials.length;
    const current = this.currentIndex + 1;
    const isLast = this.currentIndex === total - 1;
    const played = this._playedSet(this.currentIndex);
    const rated = this.choices.get(this.currentIndex);

    this._el.counter.textContent = `${practiceCounterPrefix(this.config)}${current} / ${total}`;
    this._el.label.textContent = `Audio Set ${current}`;

    if (this._el.referenceAudio) {
      const url = this._audioUrl(trial.reference);
      if (this._el.referenceAudio.getAttribute('src') !== url) this._el.referenceAudio.src = url;
      const refCol = this._el.referenceAudio.closest('.mushra-col');
      refCol?.classList.remove('audio-error-state');
      const refBtn = refCol?.querySelector('.mushra-play-btn');
      if (refBtn) resetPlayButton(refBtn);
    }

    const sliderStimuli = this._sliderStimuli(trial);
    this._el.sliderCols.forEach((col, i) => {
      const s = sliderStimuli[i];
      const localIndex = (this._hasReference ? 1 : 0) + i;
      const value = rated?.get(s.id) ?? 0;
      const enabled = played.has(localIndex);

      col.dataset.stimulusId = s.id;
      const range = col.querySelector('.mushra-range');
      range.dataset.stimulusId = s.id;
      this._setSliderValue(range, value);
      this._setSliderRated(range, !!rated?.has(s.id));
      range.classList.toggle('is-disabled', !enabled);
      range.setAttribute('aria-disabled', enabled ? 'false' : 'true');
      range.tabIndex = enabled ? 0 : -1;

      const audio = col.querySelector('audio');
      const url = this._audioUrl(s);
      if (audio.getAttribute('src') !== url) audio.src = url;
      col.classList.remove('audio-error-state');
      const playBtn = col.querySelector('.mushra-play-btn');
      if (playBtn) resetPlayButton(playBtn);
    });

    // Reference-first gating: system play buttons stay disabled until this
    // trial's Reference has been heard to completion (no-op without one).
    this._setSystemPlayButtonsEnabled(!this._hasReference || played.has(0));
    this._el.steps?.classList.toggle('played', this._hasReference && played.has(0));

    this._el.prev.disabled = this.currentIndex === 0;
    this._el.next.textContent = isLast ? finalButtonLabel(this.config) : 'Next →';
    this._el.hint.innerHTML = this._shortcutHintHtml(isLast);
    this._updateNextButtonState();
    this._updateProgressBar();
    this._onChange?.();
  }

  /**
   * Wire up one hand-built vertical slider: pointer drag (via pointer
   * capture, so movement outside the element still tracks) and keyboard
   * (shortcuts.rate_up/rate_down by 1; Shift steps by 10 when it isn't
   * consumed producing the key itself - see _rateStep/shiftIsFree). The
   * "is-active" class (double-ring thumb outline) is only applied while a
   * drag or key-adjustment is actually in progress, not as a persistent
   * focus indicator.
   */
  _bindRangeSlider(el) {
    const setValue = (rawValue) => this._applySliderValue(el, rawValue);

    const isDisabled = () => el.getAttribute('aria-disabled') === 'true';
    const activate = () => el.classList.add('is-active');
    const deactivate = () => el.classList.remove('is-active');

    // Measured against .mushra-track-row (not el itself): el's own hit box
    // is deliberately taller than the track (see the CSS), so its thumb can
    // still be grabbed when sitting right at the 0/100 edge.
    const trackRow = el.closest('.mushra-track-row');
    const valueFromClientY = (clientY) => {
      const rect = trackRow.getBoundingClientRect();
      return (1 - (clientY - rect.top) / rect.height) * 100;
    };

    // Tracks whether a drag actually STARTED on this element - pointer
    // capture alone doesn't prevent a drag that began elsewhere from also
    // firing pointermove on this slider merely because the pointer (with its
    // button still held) happened to pass over it.
    let isDragging = false;

    el.addEventListener('pointerdown', (e) => {
      if (isDisabled()) return;
      isDragging = true;
      el.focus();
      el.setPointerCapture(e.pointerId);
      activate();
      setValue(valueFromClientY(e.clientY));
    });
    el.addEventListener('pointermove', (e) => {
      if (!isDragging || isDisabled() || e.buttons === 0) return;
      setValue(valueFromClientY(e.clientY));
    });
    const endDrag = () => {
      isDragging = false;
      deactivate();
    };
    el.addEventListener('pointerup', endDrag);
    el.addEventListener('pointercancel', endDrag);
    el.addEventListener('lostpointercapture', endDrag);

    el.addEventListener('keydown', (e) => {
      if (isDisabled()) return;
      if (e.key === this.shortcuts.rate_up) {
        e.preventDefault();
        e.stopPropagation();
        activate();
        this._nudgeSlider(el, this._rateStep(e, this.shortcuts.rate_up));
      } else if (e.key === this.shortcuts.rate_down) {
        e.preventDefault();
        e.stopPropagation();
        activate();
        this._nudgeSlider(el, -this._rateStep(e, this.shortcuts.rate_down));
      }
    });
    el.addEventListener('keyup', (e) => {
      if (e.key === this.shortcuts.rate_up || e.key === this.shortcuts.rate_down) deactivate();
    });
    el.addEventListener('blur', deactivate);
  }

  /**
   * A trial counts as done once every slider has been explicitly moved at
   * least once. A slider only unlocks when its clip starts, and no clip can
   * start before the Reference (if any) has been heard to completion, so
   * all-sliders-moved transitively implies the whole listening flow.
   */
  _isTrialComplete(trialIndex) {
    const rated = this.choices.get(trialIndex);
    const sliderStimuli = this._sliderStimuli(this.trials[trialIndex]);
    return !!rated && sliderStimuli.every((s) => rated.has(s.id));
  }

  _allTrialsComplete() {
    return this.trials.every((_, i) => this._isTrialComplete(i));
  }

  /**
   * Override PairedTrialTest's weaker "has any entry" gate: MUSHRA requires
   * the whole trial to be complete (every slider moved at least once)
   * before advancing, not just one slider touched.
   */
  _navigate(delta) {
    if (delta > 0 && !this._isTrialComplete(this.currentIndex)) return;
    const next = this.currentIndex + delta;
    if (next < 0 || next >= this.trials.length) return;
    this.currentIndex = next;
    this._syncPage();
  }

  _nextOrSubmit() {
    const isLast = this.currentIndex === this.trials.length - 1;
    if (isLast) {
      if (this._allTrialsComplete()) this._submit();
    } else {
      this._navigate(1);
    }
  }

  /** Record a slider's value without a full re-render (avoids flicker). */
  _setChoice(trialIndex, stimulusId, value) {
    if (!this.choices.has(trialIndex)) this.choices.set(trialIndex, new Map());
    this.choices.get(trialIndex).set(stimulusId, value);
    this._updateNextButtonState();
    this._updateProgressBar();
    this._onChange?.();
  }

  /**
   * Serialize progress for resume. Overrides PairedTrialTest because MUSHRA's
   * choices are nested (trial -> Map<stimulus_id, value>); each inner Map is
   * flattened to entries so the record is plain JSON.
   */
  getProgress() {
    return {
      currentIndex: this.currentIndex,
      answers: [...this.choices].map(([index, valuesById]) => [index, [...valuesById]]),
      played: [...this.played].map(([index, set]) => [index, [...set]]),
    };
  }

  /** Restore serialized progress (see getProgress) and re-sync the page. */
  restoreProgress(saved) {
    this.choices = new Map(
      (saved.answers ?? []).map(([index, entries]) => [index, new Map(entries)])
    );
    this.played = new Map((saved.played ?? []).map(([index, arr]) => [index, new Set(arr)]));
    this.currentIndex = Math.min(saved.currentIndex ?? 0, this.trials.length - 1);
    this._syncPage();
  }

  /** Update the Next/Submit button once the current trial's completeness may have changed. */
  _updateNextButtonState() {
    const isLast = this.currentIndex === this.trials.length - 1;
    this._el.next.disabled = isLast
      ? !this._allTrialsComplete()
      : !this._isTrialComplete(this.currentIndex);
  }

  /** Progress bar reflects how many trials are complete, not just visited. */
  _updateProgressBar() {
    const completeCount = this.trials.filter((_, i) => this._isTrialComplete(i)).length;
    const pct = (completeCount / this.trials.length) * 100;
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = `${pct}%`;
  }

  /**
   * Pausing never preserves position in MUSHRA: comparing systems means
   * re-listening to the same passage (often just the opening) clip after
   * clip, and a mid-clip resume would silently compare different passages.
   * Via the base class this single choice makes every start play from the
   * beginning, makes the play shortcut advance to the NEXT clip after a
   * pause, and drops the redundant rewind shortcut/hint.
   */
  _supportsResume() {
    return false;
  }

  /**
   * rate_up/rate_down adjust the slider of the clip being listened to (the
   * playing clip, or the most recently started one), so listeners can rate
   * without moving focus off the play controls. A focused slider still
   * handles its own keys first (its keydown handler stops propagation), so
   * explicit slider-by-slider keyboard operation keeps working. Consumed
   * even without a target slider (e.g. the Reference is playing) so the
   * arrows never scroll the page mid-trial.
   */
  _handleChoiceKey(e) {
    const { shortcuts } = this;
    const isUp = e.key === shortcuts.rate_up;
    if (!isUp && e.key !== shortcuts.rate_down) return false;
    e.preventDefault();
    const audios = [...this._pageSlot.querySelectorAll('audio')];
    const lastPos = this._playCursor.get(this.currentIndex) ?? -1;
    const target = audios.find((a) => !a.paused) ?? (lastPos >= 0 ? audios[lastPos] : null);
    const range = target?.closest('.mushra-slider-col')?.querySelector('.mushra-range');
    if (range && range.getAttribute('aria-disabled') !== 'true') {
      const key = isUp ? shortcuts.rate_up : shortcuts.rate_down;
      this._nudgeSlider(range, (isUp ? 1 : -1) * this._rateStep(e, key));
    }
    return true;
  }

  _choiceHintHtml() {
    const { shortcuts } = this;
    const rateUpKey = shortcuts.rate_up === 'ArrowUp' ? '↑' : escapeHtml(shortcuts.rate_up);
    const rateDownKey = shortcuts.rate_down === 'ArrowDown' ? '↓' : escapeHtml(shortcuts.rate_down);
    const base = `<kbd>${rateUpKey}</kbd><kbd>${rateDownKey}</kbd> rate`;
    // Advertise the x10 modifier only when it actually works for BOTH keys
    // (see shiftIsFree) - the hint must never promise an unreachable step.
    return shiftIsFree(shortcuts.rate_up) && shiftIsFree(shortcuts.rate_down)
      ? `${base} (<kbd>Shift</kbd>: ±10)`
      : base;
  }

  async _submit() {
    await submitPayload(this, () => {
      const ratings = [];
      for (const valuesById of this.choices.values()) {
        for (const [stimulus_id, rating] of valuesById.entries()) {
          ratings.push({ stimulus_id, rating });
        }
      }
      return { ratings };
    });
  }
}
