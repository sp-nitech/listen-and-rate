/**
 * Tests for how requests name the config of a sequence they are for.
 *
 * Every stage of a sequence is served from the same config.php/save.php/
 * audio routes; only the `stage` query parameter tells the server which
 * config to answer with. A request that loses it reaches the wrong test - or
 * none - so each URL the page builds is checked here.
 */

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { audioUrl, setStage, stageUrl } from '../../js/stage.js';

afterEach(() => {
  setStage(null);
});

test('a lone config leaves URLs as they are', () => {
  assert.equal(stageUrl('config.php'), 'config.php');
  assert.equal(audioUrl({ id: 's 1' }), '/audio/s%201');
});

test('a stage is named by the query parameter', () => {
  setStage('a');
  assert.equal(stageUrl('save.php'), 'save.php?stage=a');
  assert.equal(stageUrl('audio_x.php?token=t'), 'audio_x.php?token=t&stage=a');
});

test("the FastAPI audio route names the stage, the export's static files need not", () => {
  setStage('b');
  assert.equal(audioUrl({ id: 's1' }), '/audio/s1?stage=b');
  assert.equal(audioUrl({ id: 's1', audio_url: 'stages/b/clip.wav' }), 'stages/b/clip.wav');
});
