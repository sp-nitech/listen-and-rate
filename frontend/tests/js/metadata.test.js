/**
 * Tests for the form fields' length limits.
 *
 * The limit is the field config's max_length, which the server fills in when
 * the config gives none, so the form keeps no copy that could fall out of
 * step with the one the server enforces.
 */

import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import { stubDocument } from './_helpers.js';

const restore = stubDocument();
const { MetadataPage } = await import('../../js/metadata.js');

after(restore);

/** The maxlength attribute of the field's rendered input or textarea. */
function renderedMaxLength(field) {
  const html = new MetadataPage([field])._renderField(field);
  return html.match(/maxlength="([^"]*)"/)?.[1];
}

test('a text field is limited to its max_length', () => {
  const field = { key: 'listener', label: 'L', type: 'text', max_length: 64 };
  assert.equal(renderedMaxLength(field), '64');
});

test('a free_text field is limited to its max_length', () => {
  const field = { key: 'comment', label: 'C', type: 'free_text', max_length: 500 };
  assert.equal(renderedMaxLength(field), '500');
});
