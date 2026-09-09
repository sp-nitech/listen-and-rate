/**
 * Shared base for every listening test UI (MOS and the paired-trial family).
 *
 * Owns the parts that are the same whatever a page happens to contain: the
 * header, sequential prev/next navigation gated on the current trial being
 * answered, the progress bar, the resume record, and the document-level
 * keyboard handling. A "trial" here is one presentation-and-response page -
 * one stimulus for MOS, one pair/set for the others - which is why the
 * counter can say "Trial N / M" for all of them.
 *
 * Subclasses own their page DOM (_buildPage/_syncPage) and describe their
 * answers to this class through a small set of hooks:
 *
 *   _trialCount()            how many pages there are
 *   _isAnswered(index)       whether page `index` may be navigated past
 *   _answeredCount()         how many pages are answered (drives the bar)
 *   _serializeAnswers()      \ the resume record's two halves; see
 *   _restoreAnswers(saved)   / getProgress/restoreProgress
 *   _serializePlayed()       \
 *   _restorePlayed(saved)    /
 *   _handlePlayShortcut()    what the play key does on this page
 *   _handleRewindShortcut()  what the rewind key does on this page
 *   _handleChoiceKey(e)      type-specific answer keys; true when consumed
 *   _choiceHintHtml()        that key group's segment of the shortcut hint
 *   _supportsResume()        false drops mid-clip resume and the rewind key
 *   _submit()                post the collected answers
 */

import { escapeHtml, proseHtml } from '../dom.js';
import {
  finalButtonLabel,
  finalConfirmHint,
  practiceBadgeHtml,
  practiceBannerHtml,
} from '../practice.js';
import { t } from '../strings.js';

export class ListeningTest {
  /**
   * @param {Object} config - Server config from /api/config.
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, answers).
   */
  constructor(config, sessionId, onSubmit) {
    this.config = config;
    this.sessionId = sessionId;
    this.onSubmit = onSubmit;
    this.currentIndex = 0;
    this._boundKeydown = this._handleKeydown.bind(this);
    // Dwell-time measurement (config.metrics.dwell_time); see _flushDwell for
    // what the numbers mean.
    this._dwell = new Map(); // trial index -> seconds accumulated so far
    this._enteredAt = null; // ms the running clock started, null while stopped
  }

  /** Mount the header, build the page DOM once, then sync it to the first trial. */
  render(container) {
    this.container = container;
    this._renderHeader();
    this._buildPage();
    this._syncPage();
    this._startDwellClock();
    document.addEventListener('keydown', this._boundKeydown);
  }

  /**
   * Start the clock on whichever page is now the live one.
   *
   * Called wherever a page becomes current: the first render, every
   * navigation, and a resume. Nothing runs while the tab is closed, which is
   * what keeps a session picked up the next day from being charged for the
   * night in between.
   */
  _startDwellClock() {
    if (!this._measuresDwellTime()) return;
    this._enteredAt = performance.now();
  }

  /** Settle the current page and leave the clock stopped. */
  _stopDwellClock() {
    this._flushDwell();
    this._enteredAt = null;
  }

  /**
   * Add the time since the clock started to the current page's running total.
   *
   * Every settling point goes through here and the clock restarts as it
   * leaves, so a second call straight after the first adds nothing. That is
   * what lets one method serve both the navigation boundary and the resume
   * record's mid-page flush.
   *
   * The total accumulates across visits rather than being fixed on the way
   * out. Navigation backwards is allowed, and time spent reconsidering an
   * earlier page is still time the test took - which is what makes the sum
   * over a session's answers the length of the test itself.
   */
  _flushDwell() {
    if (!this._measuresDwellTime() || this._enteredAt === null) return;
    const now = performance.now();
    const index = this.currentIndex;
    const seconds = (now - this._enteredAt) / 1000;
    this._dwell.set(index, (this._dwell.get(index) ?? 0) + seconds);
    this._enteredAt = now;
  }

  _measuresDwellTime() {
    return !!this.config.metrics?.dwell_time;
  }

  /** The seconds accumulated on a page, or null when it has none. */
  _dwellOf(index) {
    return this._dwell.get(index) ?? null;
  }

  _renderHeader() {
    const header = document.createElement('div');
    header.className = 'test-header';
    header.innerHTML = `
      <div class="test-title-row">
        <h1>${escapeHtml(this.config.title)}${practiceBadgeHtml(this.config)}</h1>
        <span class="page-counter"></span>
      </div>
      ${practiceBannerHtml(this.config)}
      ${proseHtml(this.config.instructions, 'instructions')}
    `;
    this.container.appendChild(header);
    this._pageSlot = document.createElement('div');
    this._pageSlot.className = 'page-slot';
    this.container.appendChild(this._pageSlot);
  }

  /**
   * Update the page furniture that looks the same in every test type: the
   * trial counter, prev/next, and the shortcut hint, plus the progress bar
   * and the resume callback. Subclasses call this at the end of _syncPage,
   * after they have updated their own audio and answer widgets.
   */
  _syncChrome() {
    const isLast = this.currentIndex === this._trialCount() - 1;
    this._el.counter.textContent = t('trial_counter', {
      n: this.currentIndex + 1,
      total: this._trialCount(),
    });
    this._el.prev.disabled = this.currentIndex === 0;
    this._el.next.textContent = isLast ? finalButtonLabel(this.config) : t('trial_next');
    this._el.hint.innerHTML = this._shortcutHintHtml(isLast);
    this._syncNextEnabled();
    this._updateProgressBar();
    this._onChange?.();
  }

  /** Enable Next/Submit: current trial answered (intermediate) or all answered (last). */
  _syncNextEnabled() {
    const isLast = this.currentIndex === this._trialCount() - 1;
    this._el.next.disabled = isLast
      ? this._answeredCount() !== this._trialCount()
      : !this._isAnswered(this.currentIndex);
  }

  _updateProgressBar() {
    const pct = (this._answeredCount() / this._trialCount()) * 100;
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = `${pct}%`;
  }

  /** Move to an adjacent page; forward navigation is blocked while unanswered. */
  _navigate(delta) {
    if (delta > 0 && !this._isAnswered(this.currentIndex)) return;
    const next = this.currentIndex + delta;
    if (next < 0 || next >= this._trialCount()) return;
    // Settle before the index moves, in both directions: the elapsed time
    // belongs to the page being left, not the one being opened.
    this._flushDwell();
    this.currentIndex = next;
    this._syncPage();
    this._startDwellClock();
  }

  _nextOrSubmit() {
    if (this.currentIndex < this._trialCount() - 1) {
      this._navigate(1);
    } else if (this._answeredCount() === this._trialCount()) {
      // The last page has no forward navigation to settle it, and the clock
      // stays stopped from here: a rejected POST hands the page back so the
      // listener can press Finish again (see submit.js), and the wait in
      // between is the network's rather than theirs.
      this._stopDwellClock();
      this._submit();
    }
  }

  /** Serialize progress for resume: current page, answers, and what was heard. */
  getProgress() {
    // Bank the running clock first, so the record carries the time already
    // spent on the current page. This runs on each state change (app.js wires
    // it to _onChange), so a stretch with no answer, no playback and no
    // navigation in it is the one thing a closed tab can still lose.
    this._flushDwell();
    return {
      currentIndex: this.currentIndex,
      answers: this._serializeAnswers(),
      played: this._serializePlayed(),
      metrics: [...this._dwell],
    };
  }

  /** Restore serialized progress (see getProgress) and re-sync the page. */
  restoreProgress(saved) {
    this._restoreAnswers(saved.answers ?? []);
    this._restorePlayed(saved.played ?? []);
    this._dwell = new Map(saved.metrics ?? []);
    this.currentIndex = Math.min(saved.currentIndex ?? 0, this._trialCount() - 1);
    this._syncPage();
    this._startDwellClock();
  }

  // -- keyboard shortcuts ----------------------------------------------------

  /**
   * Shared document-level keydown handler: the play and rewind shortcuts,
   * then the type-specific answer keys (via _handleChoiceKey), then
   * prev/next/confirm.
   */
  _handleKeydown(e) {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    // Let buttons handle their own Enter activation; Space is reserved for audio below.
    if (tag === 'BUTTON' && e.key === 'Enter') return;

    const { shortcuts } = this;

    // play shortcut toggles audio playback regardless of which element has focus.
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
      `<kbd>${playKey}</kbd> ${t('trial_hint_playPause')}`,
      ...(this._supportsResume() ? [`<kbd>${rewindKey}</kbd> ${t('trial_hint_rewind')}`] : []),
      this._choiceHintHtml(),
      `<kbd>${prevKey}</kbd><kbd>${nextKey}</kbd> ${t('trial_hint_navigate')}`,
      `<kbd>${confirmKey}</kbd> ${isLast ? finalConfirmHint(this.config) : t('trial_hint_next')}`,
    ];
    return segments.join(' &nbsp;·&nbsp;');
  }
}
