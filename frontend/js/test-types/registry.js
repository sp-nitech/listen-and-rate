/**
 * Which class runs each test_type - shared by whatever needs a test type's
 * own knowledge: stage-runner.js to run it, preflight.js to find its audio.
 */

import { ABTest } from './ab.js';
import { ABXTest } from './abx.js';
import { CMOSTest } from './cmos.js';
import { DMOSTest } from './dmos.js';
import { MOSTest } from './mos.js';
import { MUSHRATest } from './mushra.js';
import { XABTest } from './xab.js';

/** Map test_type strings to their corresponding test class constructors. */
const testTypeMap = {
  mos: MOSTest,
  dmos: DMOSTest,
  cmos: CMOSTest,
  ab: ABTest,
  abx: ABXTest,
  xab: XABTest,
  mushra: MUSHRATest,
};

/** Return the test class for the config's test_type; throws on an unknown one. */
export function testClassFor(config) {
  const TestClass = testTypeMap[config.test_type];
  if (!TestClass) throw new Error(`Unknown test type: "${config.test_type}"`);
  return TestClass;
}
