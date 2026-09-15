/**
 * Tests for which class runs each test_type.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MOSTest } from '../../../js/test-types/mos.js';
import { testClassFor } from '../../../js/test-types/registry.js';

test("a config's test_type names the class that runs it", () => {
  assert.equal(testClassFor({ test_type: 'mos' }), MOSTest);
});

test('a test_type no class runs is refused rather than run as some other one', () => {
  assert.throws(() => testClassFor({ test_type: 'mos2' }), /Unknown test type: "mos2"/);
});
