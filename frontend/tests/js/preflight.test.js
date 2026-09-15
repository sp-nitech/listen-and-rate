/**
 * Tests for the check run before anything is asked of the listener.
 *
 * A stage whose audio cannot be fetched, or whose results cannot be saved,
 * would strand the listener part-way through the session - so every stage
 * about to run is checked up front, each through its own stage's URLs.
 */

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { preflight } from '../../js/preflight.js';
import { Stage } from '../../js/stage.js';

const real = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = real;
});

/** Answer each URL from `failures` ({url: {status, body}}), else 200; record requests. */
function stubFetch(failures = {}) {
  const calls = [];
  globalThis.fetch = (url, init = {}) => {
    calls.push(`${init.method ?? 'GET'} ${url}`);
    const { status = 200, body = {} } = failures[url] ?? {};
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    });
  };
  return calls;
}

const mos = (ids, extra = {}) => ({
  test_type: 'mos',
  stimuli: ids.map((id) => ({ id })),
  ...extra,
});

test("every stage's audio and results are checked through its own stage", async () => {
  const calls = stubFetch();
  const problems = await preflight([
    { stage: new Stage('a'), config: mos(['s1']), withPractice: false },
    { stage: new Stage('b'), config: mos(['s1']), withPractice: false },
  ]);
  assert.deepEqual(problems, { missing: [], saveErrors: [] });
  assert.deepEqual(calls.sort(), [
    'GET save.php?stage=a',
    'GET save.php?stage=b',
    'HEAD /audio/s1?stage=a',
    'HEAD /audio/s1?stage=b',
  ]);
});

test('unreachable audio is listed, and a save problem shared by stages once', async () => {
  const saveDown = { status: 503, body: { error: 'Results directory is missing' } };
  stubFetch({
    '/audio/s2?stage=a': { status: 404 },
    'save.php?stage=a': saveDown,
    'save.php?stage=b': saveDown,
  });
  const problems = await preflight([
    { stage: new Stage('a'), config: mos(['s1', 's2']), withPractice: false },
    { stage: new Stage('b'), config: mos(['s1']), withPractice: false },
  ]);
  assert.deepEqual(problems, {
    missing: ['/audio/s2?stage=a'],
    saveErrors: ['Results directory is missing'],
  });
});

test("each test type's audio is found where its trials hold it", async () => {
  const s = (id) => ({ id });
  const configs = {
    mos: { stimuli: [s('m')] },
    dmos: { trials: [{ reference: s('r'), test: s('t') }] },
    cmos: { trials: [{ stimuli: [s('c1'), s('c2')] }] },
    ab: { trials: [{ stimuli: [s('a1'), s('a2')] }] },
    // X is always one of the trial's own A/B, so it is not fetched again.
    abx: { trials: [{ stimuli: [s('x1'), s('x2')] }] },
    xab: { trials: [{ reference: s('xr'), stimuli: [s('x3'), s('x4')] }] },
    mushra: {
      trials: [
        { reference: s('hr'), systems: [s('h1')], anchor: s('ha') },
        { reference: s('hr2'), systems: [s('h2')], anchor: null },
      ],
    },
  };
  for (const [testType, fields] of Object.entries(configs)) {
    const calls = stubFetch();
    await preflight([
      { stage: new Stage(null), config: { test_type: testType, ...fields }, withPractice: false },
    ]);
    const heads = calls.filter((c) => c.startsWith('HEAD')).map((c) => c.split('/').pop());
    const expected = {
      mos: ['m'],
      dmos: ['r', 't'],
      cmos: ['c1', 'c2'],
      ab: ['a1', 'a2'],
      abx: ['x1', 'x2'],
      xab: ['xr', 'x3', 'x4'],
      mushra: ['hr', 'h1', 'ha', 'hr2', 'h2'],
    }[testType];
    assert.deepEqual(heads, expected, testType);
  }
});

test('practice audio is checked only where the practice will run', async () => {
  const config = mos(['s1'], { practice_stimuli: [{ id: 'p1' }] });
  for (const withPractice of [false, true]) {
    const calls = stubFetch();
    await preflight([{ stage: new Stage(null), config, withPractice }]);
    assert.equal(calls.includes('HEAD /audio/p1'), withPractice);
  }
});
