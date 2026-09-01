/**
 * Tests for the session id, which names the result file on the server.
 *
 * Two listeners colliding would mean one of them losing their answers, so
 * every path has to produce a well-formed, distinct UUID. There are three:
 * crypto.randomUUID needs a secure context and so is missing over plain
 * HTTP, which is exactly when the fallbacks run.
 */

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { generateSessionId } from '../../js/session.js';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const real = globalThis.crypto;

/** Expose only the given crypto members, as a narrower context would. */
function withCrypto(members) {
  Object.defineProperty(globalThis, 'crypto', { value: members, configurable: true });
}

afterEach(() => {
  Object.defineProperty(globalThis, 'crypto', { value: real, configurable: true });
});

function assertGeneratesDistinctUuids(count = 200) {
  const ids = Array.from({ length: count }, generateSessionId);
  for (const id of ids) {
    assert.match(id, UUID_V4);
  }
  assert.equal(new Set(ids).size, count);
}

test('the native path yields distinct v4 uuids', () => {
  withCrypto({ randomUUID: real.randomUUID.bind(real) });
  assertGeneratesDistinctUuids();
});

test('without randomUUID it falls back to getRandomValues', () => {
  // The plain-HTTP case. Still cryptographically strong, unlike the last
  // resort below, which is why this path exists at all.
  withCrypto({ getRandomValues: real.getRandomValues.bind(real) });
  assertGeneratesDistinctUuids();
});

test('with no web crypto at all it still produces valid ids', () => {
  withCrypto(undefined);
  assertGeneratesDistinctUuids();
});
