/**
 * Tests for a stage: how its requests name it, and its share of the bar.
 *
 * Every stage of a sequence is served from the same config.php/save.php/
 * audio routes; only the `stage` query parameter tells the server which
 * config to answer with. A request that loses it reaches the wrong test - or
 * none - so each URL the page builds is checked here.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Stage } from '../../js/stage.js';

test('a lone config leaves URLs as they are', () => {
  const stage = new Stage(null);
  assert.equal(stage.url('config.php'), 'config.php');
  assert.equal(stage.audioUrl({ id: 's 1' }), '/audio/s%201');
});

test('a stage is named by the query parameter', () => {
  const stage = new Stage('a');
  assert.equal(stage.url('save.php'), 'save.php?stage=a');
  assert.equal(stage.url('audio_x.php?token=t'), 'audio_x.php?token=t&stage=a');
});

test("the FastAPI audio route names the stage, the export's static files need not", () => {
  const stage = new Stage('b');
  assert.equal(stage.audioUrl({ id: 's1' }), '/audio/s1?stage=b');
  assert.equal(stage.audioUrl({ id: 's1', audio_url: 'stages/b/clip.wav' }), 'stages/b/clip.wav');
});

test("a stage's progress is placed within its share of the bar", () => {
  const stage = new Stage('b', { start: 0.75, width: 0.25 });
  assert.equal(stage.progressAt(0), 0.75);
  assert.equal(stage.progressAt(0.5), 0.875);
  assert.equal(stage.progressAt(1), 1);
});

test('a stage given no share spans the whole bar', () => {
  assert.equal(new Stage(null).progressAt(0.5), 0.5);
});
