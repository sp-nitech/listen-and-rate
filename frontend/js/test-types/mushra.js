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
 * Each slider unlocks individually as soon as its own clip has played to
 * completion once (not gated on every other clip first). Next/Submit still
 * requires every clip in the trial to have played at least once (including
 * the Reference) and every slider to have been explicitly moved at least
 * once, mirroring DMOSTest's playback-gated rating.
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

export class MUSHRATest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {ratings}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    // choices: trial index → Map<stimulus_id, value> (one trial has N sliders)
    // played: trial index → Set of local indices (reused from PairedTrialTest)
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

  /** All audio clips for a trial, in DOM/playback order: reference first, then every slider stimulus. */
  _audioStimuli(trial) {
    const sliders = this._sliderStimuli(trial);
    return trial.reference ? [trial.reference, ...sliders] : sliders;
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
    const preload = this.config.preload_audio ? 'auto' : 'none';

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

      audio.addEventListener('play', () => {
        this._recordPlayCursor(audio);
        if (playBtn) playBtn.innerHTML = PAUSE_SVG;
      });
      audio.addEventListener('pause', () => {
        if (playBtn) playBtn.innerHTML = PLAY_SVG;
      });

      audio.addEventListener('error', () => {
        audio.closest('.mushra-col')?.classList.add('audio-error-state');
      });

      // Unlock only this clip's own slider (if it has one - the Reference
      // doesn't) as soon as it finishes, rather than waiting for every clip
      // in the trial to be played first.
      audio.addEventListener('ended', () => {
        const played = this._playedSet(this.currentIndex);
        if (!played.has(localIndex)) {
          played.add(localIndex);
          const range = audio.closest('.mushra-slider-col')?.querySelector('.mushra-range');
          if (range) {
            range.classList.remove('is-disabled');
            range.setAttribute('aria-disabled', 'false');
            range.tabIndex = 0;
          }
          this._updateNextButtonState();
          this._onChange?.();
        }
        // Advance the step indicator to "② Listen to others and rate" once
        // the Reference itself has been heard.
        if (audio.closest('.mushra-reference-col')) {
          this._el.steps?.classList.add('played');
        }
      });

      if (playBtn) {
        playBtn.addEventListener('click', () => {
          if (audio.paused) {
            // Only one clip plays at a time - pause whatever else is playing.
            for (const other of this._pageSlot.querySelectorAll('audio')) {
              if (other !== audio && !other.paused) other.pause();
            }
            audio.play();
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
      if (refBtn) refBtn.innerHTML = PLAY_SVG;
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
      range.classList.toggle('is-disabled', !enabled);
      range.setAttribute('aria-disabled', enabled ? 'false' : 'true');
      range.tabIndex = enabled ? 0 : -1;

      const audio = col.querySelector('audio');
      const url = this._audioUrl(s);
      if (audio.getAttribute('src') !== url) audio.src = url;
      col.classList.remove('audio-error-state');
      const playBtn = col.querySelector('.mushra-play-btn');
      if (playBtn) playBtn.innerHTML = PLAY_SVG;
    });

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
   * (shortcuts.rate_up/rate_down by 1, Shift+ for 10 - configurable, like
   * prev/next). The "is-active" class (double-ring thumb outline) is only
   * applied while a drag or key-adjustment is actually in progress, not as
   * a persistent focus indicator.
   */
  _bindRangeSlider(el) {
    const setValue = (rawValue) => {
      const value = Math.max(0, Math.min(100, Math.round(rawValue)));
      this._setSliderValue(el, value);
      this._setChoice(this.currentIndex, el.dataset.stimulusId, value);
    };

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
      const current = Number.parseInt(el.dataset.value, 10);
      const step = e.shiftKey ? 10 : 1;
      if (e.key === this.shortcuts.rate_up) {
        e.preventDefault();
        e.stopPropagation();
        activate();
        setValue(current + step);
      } else if (e.key === this.shortcuts.rate_down) {
        e.preventDefault();
        e.stopPropagation();
        activate();
        setValue(current - step);
      }
    });
    el.addEventListener('keyup', (e) => {
      if (e.key === this.shortcuts.rate_up || e.key === this.shortcuts.rate_down) deactivate();
    });
    el.addEventListener('blur', deactivate);
  }

  /** True once every clip (reference + all sliders) in this trial has played to completion at least once. */
  _canChoose(trialIndex) {
    const trial = this.trials[trialIndex];
    return this._playedSet(trialIndex).size >= this._audioStimuli(trial).length;
  }

  _isTrialFullyRated(trialIndex, sliderStimuli) {
    const rated = this.choices.get(trialIndex);
    return !!rated && sliderStimuli.every((s) => rated.has(s.id));
  }

  /** A trial counts as done once every clip has played AND every slider has been explicitly moved. */
  _isTrialComplete(trialIndex) {
    const trial = this.trials[trialIndex];
    return (
      this._canChoose(trialIndex) && this._isTrialFullyRated(trialIndex, this._sliderStimuli(trial))
    );
  }

  _allTrialsComplete() {
    return this.trials.every((_, i) => this._isTrialComplete(i));
  }

  /**
   * Override PairedTrialTest's weaker "has any entry" gate: MUSHRA requires
   * the whole trial to be complete (every clip played, every slider moved)
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

  /** MUSHRA has no document-level choice keys - ratings are adjusted on the focused slider (rate_up/rate_down, see _bindSlider). */
  _handleChoiceKey() {
    return false;
  }

  _choiceHintHtml() {
    const { shortcuts } = this;
    const rateUpKey = shortcuts.rate_up === 'ArrowUp' ? '↑' : escapeHtml(shortcuts.rate_up);
    const rateDownKey = shortcuts.rate_down === 'ArrowDown' ? '↓' : escapeHtml(shortcuts.rate_down);
    return `<kbd>${rateUpKey}</kbd><kbd>${rateDownKey}</kbd> rate`;
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
