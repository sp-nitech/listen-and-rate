/**
 * Tests for the resume record's lifecycle rules.
 *
 * These decide whether a listener who closed the tab is offered their
 * half-finished session back, and which abandoned records get cleaned up.
 * Both are pure given a clock, so they are checked here rather than by
 * driving a browser through a two-hour-old session.
 */

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { isResumable, pruneExpiredRecords, recordKey } from '../../js/resume.js';

const realLocalStorage = globalThis.localStorage;

afterEach(() => {
  globalThis.localStorage = realLocalStorage;
});

/** A Map-backed stand-in for localStorage, which is exactly a string store. */
function fakeLocalStorage(entries) {
  const store = new Map(entries);
  globalThis.localStorage = {
    get length() {
      return store.size;
    },
    key: (i) => [...store.keys()][i] ?? null,
    getItem: (k) => store.get(k) ?? null,
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  return store;
}

const fresh = (savedAt, fingerprint = 'v1') => JSON.stringify({ savedAt, fingerprint });

// -- isResumable -------------------------------------------------------------

test('a record is resumable only while it is fresh', () => {
  // Exclusive boundary: a record exactly maxAgeMs old has expired.
  const record = { fingerprint: 'v1', savedAt: 0 };
  assert.equal(isResumable(record, 'v1', 499, 500), true);
  assert.equal(isResumable(record, 'v1', 500, 500), false);
});

test('a record from a different config is never resumable', () => {
  // The config was edited under it, so its frozen trials no longer match the
  // test being served.
  const record = { fingerprint: 'v1', savedAt: 0 };
  assert.equal(isResumable(record, 'v2', 0, 500), false);
});

test('a missing or unusable record is not resumable', () => {
  assert.equal(isResumable(null, 'v1', 0, 500), false);
  assert.equal(isResumable(undefined, 'v1', 0, 500), false);
  // savedAt decides the age, so a record without a usable one can never pass.
  assert.equal(isResumable({ fingerprint: 'v1' }, 'v1', 0, 500), false);
  assert.equal(isResumable({ fingerprint: 'v1', savedAt: '0' }, 'v1', 0, 500), false);
});

test('maxAgeMs of 0 makes every record unresumable', () => {
  // How resume.max_age_hours: 0 turns resume off - even a record saved this
  // instant must not be offered back.
  const record = { fingerprint: 'v1', savedAt: 0 };
  assert.equal(isResumable(record, 'v1', 0, 0), false);
});

// -- recordKey ---------------------------------------------------------------

test('records are namespaced per experiment', () => {
  assert.notEqual(recordKey('study-a'), recordKey('study-b'));
});

test('an absent experiment id still yields a usable key', () => {
  assert.equal(recordKey(null), recordKey(undefined));
  assert.equal(typeof recordKey(undefined), 'string');
});

// -- pruneExpiredRecords -----------------------------------------------------

test('pruning drops expired records and keeps the rest', () => {
  const store = fakeLocalStorage([
    [recordKey('expired'), fresh(0)],
    [recordKey('current'), fresh(900)],
  ]);
  pruneExpiredRecords(1000, 500);
  assert.deepEqual([...store.keys()], [recordKey('current')]);
});

test('pruning leaves keys that are not resume records alone', () => {
  // The store is shared with whatever else the origin has saved.
  const store = fakeLocalStorage([
    [recordKey('expired'), fresh(0)],
    ['theme', 'dark'],
  ]);
  pruneExpiredRecords(1000, 500);
  assert.deepEqual([...store.keys()], ['theme']);
});

test('pruning drops records it cannot read an age from', () => {
  // These can never become resumable either, so they would otherwise sit
  // there forever, each holding a whole delivered config.
  const store = fakeLocalStorage([
    [recordKey('corrupt'), '{not json'],
    [recordKey('no-timestamp'), JSON.stringify({ fingerprint: 'v1' })],
    [recordKey('current'), fresh(900)],
  ]);
  pruneExpiredRecords(1000, 500);
  assert.deepEqual([...store.keys()], [recordKey('current')]);
});

test('pruning ignores a config change on its own', () => {
  // A fingerprint mismatch can be temporary - the config is edited back - so
  // only the age is grounds for removal.
  const store = fakeLocalStorage([[recordKey('other-config'), fresh(900, 'v2')]]);
  pruneExpiredRecords(1000, 500);
  assert.deepEqual([...store.keys()], [recordKey('other-config')]);
});

test("pruning judges a record by its own window, not the pruning experiment's", () => {
  // A long-window experiment's record must survive a short-window
  // experiment's prune sweep, and vice versa - each origin serves several
  // experiments that may configure resume differently.
  const store = fakeLocalStorage([
    [recordKey('long-window'), JSON.stringify({ savedAt: 900, fingerprint: 'v1', maxAgeMs: 2000 })],
    [recordKey('short-window'), JSON.stringify({ savedAt: 900, fingerprint: 'v1', maxAgeMs: 50 })],
  ]);
  // fallbackMaxAgeMs (500) would keep both if it were applied uniformly.
  pruneExpiredRecords(1000, 500);
  assert.deepEqual([...store.keys()], [recordKey('long-window')]);
});

test('pruning falls back to the given window for a record with no window of its own', () => {
  // A record saved before the window became configurable carries no maxAgeMs.
  const store = fakeLocalStorage([[recordKey('legacy'), fresh(900)]]);
  pruneExpiredRecords(1000, 50);
  assert.deepEqual([...store.keys()], []);
});
