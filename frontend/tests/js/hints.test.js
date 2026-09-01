/**
 * Tests for the rating-key fragment of the keyboard shortcut hint.
 *
 * The compact "1-5" dash form is only honest when every key between the ends
 * really does work. Print it for a set with a gap, or for letters, and the
 * hint tells the listener about shortcuts that do nothing.
 */

import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import { stubDocument } from './_helpers.js';

const restore = stubDocument();
const { ratingKeysHint } = await import('../../js/hints.js');

after(restore);

/** The keys the hint actually names, in the order it names them. */
function keysIn(html) {
  return [...html.matchAll(/<kbd>([^<]*)<\/kbd>/g)].map((m) => m[1]);
}

const DASH = '\u2013'; // en dash, as hints.js writes it

test('a contiguous digit run collapses to its two ends', () => {
  // The map is the browser-facing direction: pressed key -> rating value.
  const html = ratingKeysHint({ 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 });
  assert.deepEqual(keysIn(html), ['1', '5']);
  assert.ok(html.includes(DASH));
});

test('a gap in the digits lists every key', () => {
  // "1-4" would claim 3 works when nothing is bound to it.
  const html = ratingKeysHint({ 1: 1, 2: 2, 4: 3 });
  assert.deepEqual(keysIn(html), ['1', '2', '4']);
  assert.ok(!html.includes(DASH));
});

test('letters are listed even when they run consecutively', () => {
  // "a-e" reads ambiguously whether or not the letters between are bound.
  const html = ratingKeysHint({ a: 1, b: 2, c: 3 });
  assert.deepEqual(keysIn(html), ['a', 'b', 'c']);
  assert.ok(!html.includes(DASH));
});

test('multi-character keys are listed', () => {
  const html = ratingKeysHint({ 1: 1, F2: 2 });
  assert.deepEqual(keysIn(html), ['1', 'F2']);
});

test('a lone key is not a range', () => {
  const html = ratingKeysHint({ 1: 1 });
  assert.deepEqual(keysIn(html), ['1']);
  assert.ok(!html.includes(DASH));
});

test('keys are ordered by the rating they give, not by the key itself', () => {
  // CMOS binds keys 1..7 to ratings -3..+3, so the keys are ordered by the
  // rating they give - which is the order the scale reads on screen.
  const html = ratingKeysHint({ 1: -3, 2: -2, 3: -1, 4: 0 });
  assert.deepEqual(keysIn(html), ['1', '4']);
});

test('a descending key order still reads low rating first', () => {
  // Object insertion order is not rating order.
  const html = ratingKeysHint({ e: 5, a: 1, c: 3 });
  assert.deepEqual(keysIn(html), ['a', 'c', 'e']);
});
