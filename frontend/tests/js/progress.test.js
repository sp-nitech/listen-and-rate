/**
 * Tests for how the shared progress bar is shared across a whole sequence.
 *
 * Each stage counts its own pages ("Trial 1 / 4"), while the bar spans every
 * stage, so each stage takes a share of it (and places its progress there -
 * see stage.test.js).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { pageCount, stageSpans } from '../../js/progress.js';

test('each stage takes a share of the bar in proportion to its pages', () => {
  assert.deepEqual(stageSpans([6, 2]), [
    { start: 0, width: 0.75 },
    { start: 0.75, width: 0.25 },
  ]);
});

test('pages are counted from the stimuli or the trials, whichever the test type has', () => {
  assert.equal(pageCount({ stimuli: [{}, {}, {}] }), 3);
  assert.equal(pageCount({ trials: [{}, {}] }), 2);
  assert.equal(pageCount({}), 0);
});
