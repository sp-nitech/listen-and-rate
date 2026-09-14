/**
 * Tests for how a page load runs its stages: where it starts, the session it
 * runs under, and the hand-over from one stage to the next.
 *
 * The screens and a stage's own run are passed in, so the order of the steps
 * - which is what a resumed or interrupted session depends on - is checked
 * here without a page.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { recordKey } from '../../js/resume.js';
import { chooseStart, openSession, planStages, runStages } from '../../js/sequence.js';

/** A delivered stage config, as far as the sequence reads it. */
const stageConfig = (id, pages = 2, extra = {}) => ({
  experiment_id: id,
  config_version: 'v1',
  resume: { max_age_ms: 500 },
  stimuli: Array.from({ length: pages }, () => ({})),
  metadata: { fields: [] },
  ...extra,
});

const saved = (extra) => ({ fingerprint: 'v1', sequence: ['a', 'b'], savedAt: 900, ...extra });

// -- chooseStart --------------------------------------------------------------

test('with nothing saved, a load starts the first stage with a new session', async () => {
  const configs = [stageConfig('a'), stageConfig('b')];
  const askResume = () => assert.fail('nothing to offer');
  const start = await chooseStart(configs, new Map(), 1000, { askResume });
  assert.deepEqual(start, { index: 0, carried: null, resumed: null });
});

test('resuming a stage in progress restores it under its session', async () => {
  const configs = [stageConfig('a'), stageConfig('b')];
  const record = saved({
    sessionId: 's1',
    metadata: { device: 'HP' },
    progress: { currentIndex: 1 },
  });
  const asked = [];
  const start = await chooseStart(configs, new Map([[recordKey('b'), record]]), 1000, {
    askResume: async (r, index) => {
      asked.push([r, index]);
      return true;
    },
  });
  assert.deepEqual(asked, [[record, 1]]);
  assert.deepEqual(start, {
    index: 1,
    carried: { sessionId: 's1', metadata: { device: 'HP' } },
    resumed: record,
  });
});

test('resuming a stage handed its session but not started starts it afresh', async () => {
  const configs = [stageConfig('a'), stageConfig('b')];
  const record = saved({ sessionId: 's1', metadata: {}, progress: null });
  const start = await chooseStart(configs, new Map([[recordKey('b'), record]]), 1000, {
    askResume: async () => true,
  });
  assert.equal(start.index, 1);
  assert.equal(start.resumed, null);
  assert.deepEqual(start.carried, { sessionId: 's1', metadata: {} });
});

test('starting over clears every stage and begins the whole sequence anew', async () => {
  const configs = [stageConfig('a'), stageConfig('b')];
  const cleared = [];
  const start = await chooseStart(
    configs,
    new Map([[recordKey('b'), saved({ progress: null })]]),
    1000,
    {
      askResume: async () => false,
      clearStageRecords: (c) => cleared.push(c),
    }
  );
  assert.deepEqual(cleared, [configs]);
  assert.deepEqual(start, { index: 0, carried: null, resumed: null });
});

// -- planStages ---------------------------------------------------------------

test('a load plans the stages from where it starts, each with its share of the bar', () => {
  const fresh = [stageConfig('a', 6), stageConfig('b', 2)];
  const frozen = stageConfig('b', 2, { title: 'frozen' });
  const planned = planStages(['a', 'b'], fresh, { index: 1, resumed: { config: frozen } });
  assert.equal(planned.length, 1);
  assert.equal(planned[0].index, 1);
  // A resumed stage runs the config it was started with.
  assert.equal(planned[0].config, frozen);
  assert.equal(planned[0].stage.id, 'b');
  // Its share still counts the stage before it, which is done.
  assert.deepEqual(planned[0].stage.span, { start: 0.75, width: 0.25 });
});

test("a lone config's page plans one stage naming none", () => {
  const planned = planStages([null], [stageConfig('a')], { index: 0, resumed: null });
  assert.equal(planned[0].stage.id, null);
  assert.deepEqual(planned[0].stage.span, { start: 0, width: 1 });
});

// -- openSession --------------------------------------------------------------

test('a session carried on keeps its id and answers, and asks nothing', async () => {
  const carried = { sessionId: 's1', metadata: { device: 'HP' } };
  const session = await openSession({ carried }, stageConfig('a'), () => assert.fail('asked'));
  assert.equal(session, carried);
});

test("a new session asks the first config's form once", async () => {
  const form = { fields: [{ key: 'device' }] };
  const asked = [];
  const session = await openSession(
    { carried: null },
    stageConfig('a', 2, { metadata: form }),
    async (f) => {
      asked.push(f);
      return { device: 'HP' };
    }
  );
  assert.deepEqual(asked, [form]);
  assert.deepEqual(session.metadata, { device: 'HP' });
  assert.equal(typeof session.sessionId, 'string');
});

test('a new session with no form to show asks nothing', async () => {
  const session = await openSession({ carried: null }, stageConfig('a'), () =>
    assert.fail('asked')
  );
  assert.deepEqual(session.metadata, {});
});

// -- runStages ----------------------------------------------------------------

/** Record every step runStages takes, in order. */
function recorder() {
  const steps = [];
  return {
    steps,
    deps: {
      runStage: async (planned, progress) => steps.push(['run', planned.stage.id, progress]),
      promptNextStage: async (stage, done, total) => steps.push(['next', stage.id, done, total]),
      showComplete: (stage) => steps.push(['complete', stage.id]),
      saveRecord: (key, record) =>
        steps.push(['save', key, record.progress, record.sequence, record.sessionId]),
      now: () => 900,
    },
  };
}

test('each stage is handed the session before the listener is asked to go on', async () => {
  const planned = planStages(['a', 'b'], [stageConfig('a'), stageConfig('b')], {
    index: 0,
    resumed: null,
  });
  const { steps, deps } = recorder();
  await runStages(planned, ['a', 'b'], { sessionId: 's1', metadata: {} }, null, deps);
  assert.deepEqual(steps, [
    ['run', 'a', null],
    ['save', recordKey('b'), null, ['a', 'b'], 's1'],
    ['next', 'a', 1, 2],
    ['run', 'b', null],
    ['complete', 'b'],
  ]);
});

test('only the stage a load resumes gets its saved progress back', async () => {
  const planned = planStages(['a', 'b'], [stageConfig('a'), stageConfig('b')], {
    index: 0,
    resumed: null,
  });
  const { steps, deps } = recorder();
  await runStages(
    planned,
    ['a', 'b'],
    { sessionId: 's1', metadata: {} },
    { currentIndex: 1 },
    deps
  );
  assert.deepEqual(
    steps.filter(([step]) => step === 'run'),
    [
      ['run', 'a', { currentIndex: 1 }],
      ['run', 'b', null],
    ]
  );
});

test('a stage with resume turned off is handed nothing to resume', async () => {
  const b = stageConfig('b', 2, { resume: { max_age_ms: 0 } });
  const planned = planStages(['a', 'b'], [stageConfig('a'), b], { index: 0, resumed: null });
  const { steps, deps } = recorder();
  await runStages(planned, ['a', 'b'], { sessionId: 's1', metadata: {} }, null, deps);
  assert.equal(steps.filter(([step]) => step === 'save').length, 0);
});
