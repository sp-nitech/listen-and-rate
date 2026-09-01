/**
 * Tests for how server errors reach the listener.
 *
 * The two backends report a rejection under different keys - FastAPI's
 * `detail`, save.php's `error` - and submitRatings is the one place that
 * papers over the difference. Lose that and a listener whose submission was
 * refused sees a bare status code instead of the reason, with their answers
 * still unsent.
 */

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { fetchConfig, submitRatings } from '../../js/api.js';

const real = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = real;
});

/** Reply with `body` and `status`, recording what was requested. */
function stubFetch({ status = 200, body = {}, json = true } = {}) {
  const calls = [];
  globalThis.fetch = (url, init) => {
    calls.push({ url, init });
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => (json ? Promise.resolve(body) : Promise.reject(new Error('not json'))),
    });
  };
  return calls;
}

// -- fetchConfig -------------------------------------------------------------

test('fetchConfig returns the parsed config', async () => {
  stubFetch({ body: { test_type: 'mos' } });
  assert.deepEqual(await fetchConfig(), { test_type: 'mos' });
});

test('fetchConfig names the status when the config cannot be loaded', async () => {
  stubFetch({ status: 503 });
  await assert.rejects(fetchConfig, /503/);
});

// -- submitRatings -----------------------------------------------------------

test('submitRatings posts the payload as JSON', async () => {
  const calls = stubFetch({ body: { status: 'ok' } });
  await submitRatings({ session_id: 's1', test_type: 'mos' });
  assert.equal(calls[0].url, 'save.php');
  assert.equal(calls[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].init.body), { session_id: 's1', test_type: 'mos' });
});

test("submitRatings surfaces FastAPI's detail", async () => {
  stubFetch({ status: 400, body: { detail: 'ratings must be a non-empty array' } });
  await assert.rejects(() => submitRatings({}), /non-empty array/);
});

test("submitRatings surfaces save.php's error", async () => {
  // Same rejection, different key - the PHP bundle answers with `error`.
  stubFetch({ status: 400, body: { error: 'Unknown stimulus IDs' } });
  await assert.rejects(() => submitRatings({}), /Unknown stimulus IDs/);
});

test('submitRatings falls back to the status when the body explains nothing', async () => {
  // A proxy or a fatal error can answer with something that is not JSON at
  // all, which must not turn into an unhandled parse failure.
  stubFetch({ status: 500, json: false });
  await assert.rejects(() => submitRatings({}), /500/);
});
