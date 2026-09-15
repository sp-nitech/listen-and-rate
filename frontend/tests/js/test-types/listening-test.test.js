/**
 * Tests for the page-level bookkeeping every test type shares: dwell-time
 * accumulation (config.metrics.dwell_time) and the progress bar.
 *
 * The sum of a session's dwell times is meant to be the length of the test,
 * which only holds if every stretch on a page is counted exactly once: both
 * directions of navigation settle it, revisits add to it rather than being
 * dropped, and the stretch while the tab was closed is not in it at all.
 *
 * Driven through a subclass that stubs the DOM hooks, so the arithmetic is
 * exercised without a page. performance.now is replaced with a hand-advanced
 * clock: real elapsed time cannot be asserted on.
 */

import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';

import { Stage } from '../../../js/stage.js';
import { ListeningTest } from '../../../js/test-types/listening-test.js';

let now = 0;
const realNow = performance.now;

beforeEach(() => {
  now = 0;
  performance.now = () => now;
});

afterEach(() => {
  performance.now = realNow;
});

/** Advance the stubbed clock by `seconds`. */
function tick(seconds) {
  now += seconds * 1000;
}

/** A ListeningTest with every DOM and answer hook stubbed out. */
class StubTest extends ListeningTest {
  constructor({ dwellTime = true, trials = 3, isPractice = false, stage } = {}) {
    super({ metrics: { dwell_time: dwellTime }, isPractice }, 'session', () => {}, stage);
    this.trials = trials;
    this.submitted = false;
  }

  _trialCount() {
    return this.trials;
  }

  _isAnswered() {
    return true;
  }

  _answeredCount() {
    return this.trials;
  }

  _syncPage() {}

  _serializeAnswers() {
    return [];
  }

  _serializePlayed() {
    return [];
  }

  _restoreAnswers() {}

  _restorePlayed() {}

  _submit() {
    this.submitted = true;
  }

  /** Stand in for render(), which needs a container. */
  start() {
    this._startDwellClock();
    return this;
  }
}

test('time on a page lands on that page', () => {
  const test = new StubTest().start();
  tick(4);
  test._navigate(1);
  assert.equal(test._dwellOf(0), 4);
});

test('each page keeps its own total', () => {
  const test = new StubTest().start();
  tick(4);
  test._navigate(1);
  tick(6);
  test._navigate(1);
  assert.equal(test._dwellOf(0), 4);
  assert.equal(test._dwellOf(1), 6);
});

test('going back settles the page being left', () => {
  // Backward navigation has to settle too, or the time between arriving on a
  // page and stepping back off it would never be counted anywhere.
  const test = new StubTest().start();
  tick(4);
  test._navigate(1);
  tick(3);
  test._navigate(-1);
  assert.equal(test._dwellOf(1), 3);
});

test('a revisit adds to the page rather than being dropped', () => {
  // The sum is the length of the test, so time spent reconsidering an earlier
  // page belongs to it - unlike a metric settled once on the way out.
  const test = new StubTest().start();
  tick(4);
  test._navigate(1);
  tick(1);
  test._navigate(-1);
  tick(5);
  assert.equal(test._dwellOf(0), 4);
  test._navigate(1);
  assert.equal(test._dwellOf(0), 9);
});

test('the last page is settled before the answers are posted', () => {
  // It has no forward navigation to settle it.
  const test = new StubTest({ trials: 1 }).start();
  tick(7);
  test._nextOrSubmit();
  assert.ok(test.submitted);
  assert.equal(test._dwellOf(0), 7);
});

test('the sum over the pages is the time the test took', () => {
  const test = new StubTest({ trials: 3 }).start();
  tick(4);
  test._navigate(1);
  tick(6);
  test._navigate(1);
  tick(5);
  test._nextOrSubmit();
  const total = [...test._dwell.values()].reduce((a, b) => a + b, 0);
  assert.equal(total, 15);
});

test('saved progress includes the running clock without double counting', () => {
  const test = new StubTest().start();
  tick(4);
  assert.equal(test.getProgress().metrics[0][1], 4);
  tick(3);
  test._navigate(1);
  assert.equal(test._dwellOf(0), 7);
});

test('the clock does not run while the session is away', () => {
  // A session resumed the next day must not be charged for the night: the
  // record carries what was banked, and the clock restarts on return.
  const test = new StubTest().start();
  tick(4);
  const saved = test.getProgress();

  const resumed = new StubTest();
  tick(60 * 60 * 8); // the tab is closed for eight hours
  resumed.restoreProgress(saved);
  tick(2);
  resumed._navigate(1);
  assert.equal(resumed._dwellOf(0), 6);
});

test('a failed submission does not charge the wait to the last page', () => {
  // submit.js hands the page back on a rejection, so the listener can press
  // Finish again. The clock must not still be running across the network
  // wait, or one bad connection reads as a listener who stared at the last
  // trial for a minute.
  const test = new StubTest({ trials: 1 }).start();
  tick(7);
  test._nextOrSubmit();
  tick(60); // the POST fails and the listener waits, then retries
  test._nextOrSubmit();
  assert.equal(test._dwellOf(0), 7);
});

test('nothing is measured when the config does not ask for it', () => {
  const test = new StubTest({ dwellTime: false }).start();
  tick(4);
  test._navigate(1);
  assert.equal(test._dwellOf(0), null);
  assert.deepEqual(test.getProgress().metrics, []);
});

// -- progress bar -------------------------------------------------------------

/** Install a `document` holding just the progress bar; returns the bar. */
function stubProgressBar(width) {
  const bar = { style: { width } };
  globalThis.document = { getElementById: (id) => (id === 'progress-bar' ? bar : null) };
  return bar;
}

afterEach(() => {
  delete globalThis.document;
});

test("answering moves the bar within the stage's share of the whole session", () => {
  const bar = stubProgressBar('0%');
  new StubTest({
    trials: 2,
    stage: new Stage('b', { start: 0.25, width: 0.5 }),
  })._updateProgressBar();
  assert.equal(bar.style.width, '75%');
});

test('practice pages leave the bar where it is', () => {
  // They are no part of the test, so the bar keeps showing the real progress.
  const bar = stubProgressBar('40%');
  new StubTest({ isPractice: true })._updateProgressBar();
  assert.equal(bar.style.width, '40%');
});
