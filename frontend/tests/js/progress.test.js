/**
 * Tests for how the shared progress bar measures a whole sequence.
 *
 * Each stage counts its own pages ("Trial 1 / 4"), while the bar spans every
 * stage, so a stage's progress has to be placed within its share of the bar.
 */

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { overallFraction, pageCount, setStageSpan, stageSpans } from '../../js/progress.js';

afterEach(() => {
  setStageSpan({ start: 0, width: 1 });
});

test('each stage takes a share of the bar in proportion to its pages', () => {
  assert.deepEqual(stageSpans([6, 2]), [
    { start: 0, width: 0.75 },
    { start: 0.75, width: 0.25 },
  ]);
});

test('a lone config spans the whole bar', () => {
  assert.deepEqual(stageSpans([4]), [{ start: 0, width: 1 }]);
  assert.equal(overallFraction(0.5), 0.5);
});

test("a stage's progress is placed within its share", () => {
  setStageSpan({ start: 0.75, width: 0.25 });
  assert.equal(overallFraction(0), 0.75);
  assert.equal(overallFraction(0.5), 0.875);
  assert.equal(overallFraction(1), 1);
});

test('pages are counted from the stimuli or the trials, whichever the test type has', () => {
  assert.equal(pageCount({ stimuli: [{}, {}, {}] }), 3);
  assert.equal(pageCount({ trials: [{}, {}] }), 2);
  assert.equal(pageCount({}), 0);
});
