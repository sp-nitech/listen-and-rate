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
 *   _gatedSeconds(index)     clip time the listener must sit through there
 *   _submit()                post the collected answers
 */

import { escapeHtml, proseHtml } from '../dom.js';
import {
  finalButtonLabel,
  finalConfirmHint,
  practiceBadgeHtml,
  practiceBannerHtml,
} from '../practice.js';

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
    // Response-time measurement (config.metrics.response_time); see
    // _startResponseClock/_stopResponseClock for what the numbers mean.
    this._playStartedAt = new Map(); // trial index -> ms at its first play
    this._responseTime = new Map(); // trial index -> seconds, once settled
  }

  /** Mount the header, build the page DOM once, then sync it to the first trial. */
  render(container) {
    this.container = container;
    this._renderHeader();
    this._buildPage();
    // Capture phase: media events do not bubble, so an ancestor only sees
    // them this way - which lets one listener here cover every test type
    // rather than each one wiring its own clips.
    this._pageSlot.addEventListener('play', () => this._startResponseClock(), true);
    this._syncPage();
    document.addEventListener('keydown', this._boundKeydown);
  }

  /**
   * Note when the listener first played audio on the current page.
   *
   * The clock starts here rather than on arrival so that reading the page,
   * or stepping away before engaging with it, is not counted as deciding.
   */
  _startResponseClock() {
    if (!this._measuresResponseTime()) return;
    if (!this._playStartedAt.has(this.currentIndex)) {
      this._playStartedAt.set(this.currentIndex, performance.now());
    }
  }

  /**
   * Settle the current page's response time, once, on the way forward.
   *
   * Time on the page, less the clip time the listener had to sit through to
   * be allowed to leave it (_gatedSeconds) - so what remains is deciding, not
   * listening. Only a forward move settles it, and only the first one:
   * forward is gated on having answered, which is what makes the result
   * non-negative, and a later revisit is re-reading rather than answering.
   */
  _stopResponseClock() {
    if (!this._measuresResponseTime()) return;
    const index = this.currentIndex;
    const startedAt = this._playStartedAt.get(index);
    if (startedAt === undefined || this._responseTime.has(index)) return;
    const elapsed = (performance.now() - startedAt) / 1000;
    this._responseTime.set(index, elapsed - this._gatedSeconds(index));
  }

  _measuresResponseTime() {
    return !!this.config.metrics?.response_time;
  }

  /** The settled response time for a trial, or null when it has none. */
  _responseTimeOf(index) {
    return this._responseTime.get(index) ?? null;
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
    this._el.counter.textContent = `Trial ${this.currentIndex + 1} / ${this._trialCount()}`;
    this._el.prev.disabled = this.currentIndex === 0;
    this._el.next.textContent = isLast ? finalButtonLabel(this.config) : 'Next →';
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
    if (delta > 0) this._stopResponseClock();
    this.currentIndex = next;
    this._syncPage();
  }

  _nextOrSubmit() {
    if (this.currentIndex < this._trialCount() - 1) {
      this._navigate(1);
    } else if (this._answeredCount() === this._trialCount()) {
      // The last page has no forward navigation to settle it.
      this._stopResponseClock();
      this._submit();
    }
  }

  /** Serialize progress for resume: current page, answers, and what was heard. */
  getProgress() {
    return {
      currentIndex: this.currentIndex,
      answers: this._serializeAnswers(),
      played: this._serializePlayed(),
      // Settled response times only: a page whose clock is still running is
      // one the listener has not answered, and it restarts on resume anyway.
      metrics: [...this._responseTime],
    };
  }

  /** Restore serialized progress (see getProgress) and re-sync the page. */
  restoreProgress(saved) {
    this._restoreAnswers(saved.answers ?? []);
    this._restorePlayed(saved.played ?? []);
    this._responseTime = new Map(saved.metrics ?? []);
    this.currentIndex = Math.min(saved.currentIndex ?? 0, this._trialCount() - 1);
    this._syncPage();
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
      `<kbd>${playKey}</kbd> play/pause`,
      ...(this._supportsResume() ? [`<kbd>${rewindKey}</kbd> rewind`] : []),
      this._choiceHintHtml(),
      `<kbd>${prevKey}</kbd><kbd>${nextKey}</kbd> navigate`,
      `<kbd>${confirmKey}</kbd> ${isLast ? finalConfirmHint(this.config) : 'next'}`,
    ];
    return segments.join(' &nbsp;·&nbsp;');
  }
}
