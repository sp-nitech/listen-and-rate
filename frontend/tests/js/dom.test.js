/**
 * Tests for how config-authored prose becomes displayed text.
 *
 * A YAML block scalar is wrapped for the config file's own readability, so
 * those newlines are not the author asking for line breaks - blank lines are.
 * Getting that distinction wrong either turns the file's wrapping into hard
 * breaks or leaves no way to break a line at all, and both look plausible
 * until someone reads the rendered page.
 *
 * The element carries `white-space: pre-line`, so what these assert is the
 * text handed to it, newlines and all.
 */

import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import { stubDocument } from './_helpers.js';

// dom.js reaches for `document` when its functions run, so the stub only has
// to be standing before the first test - but it is installed before the
// import anyway, since a module is free to touch the DOM at load time.
const restore = stubDocument();
const { proseHtml } = await import('../../js/dom.js');

after(restore);

/** The text inside the rendered element. */
function rendered(text, className = 'prose') {
  const html = proseHtml(text, className);
  const match = html.match(/^<p class="([^"]*)">([\s\S]*)<\/p>$/);
  assert.ok(match, `not a single element: ${html}`);
  assert.equal(match[1], className);
  return match[2];
}

test('a wrapped line reflows into one line', () => {
  // The line break belongs to the config file, not to the text.
  assert.equal(rendered('one line\nwrapped onto two.'), 'one line wrapped onto two.');
});

test('a blank line breaks the line', () => {
  assert.equal(rendered('first.\n\nsecond.'), 'first.\nsecond.');
});

test('n blank lines give n breaks', () => {
  // Two blank lines leave one blank line in the display, three leave two.
  assert.equal(rendered('first.\n\n\nsecond.'), 'first.\n\nsecond.');
  assert.equal(rendered('first.\n\n\n\nsecond.'), 'first.\n\n\nsecond.');
});

test('a whitespace-only line counts as blank', () => {
  // Trailing spaces on an "empty" line are invisible in an editor.
  assert.equal(rendered('first.\n   \nsecond.'), 'first.\nsecond.');
});

test('surrounding blank lines are dropped', () => {
  // A block scalar ends with a newline, which is not a break the author asked
  // for, and would otherwise render as a gap under the text.
  assert.equal(rendered('\n\nonly line.\n\n'), 'only line.');
});

test('the caller names the class the prose is styled by', () => {
  // Three blocks share this renderer and each is styled differently: the
  // trial instructions, a form page's description, and the practice banner.
  for (const name of ['instructions', 'metadata-description', 'practice-banner']) {
    assert.match(proseHtml('text.', name), new RegExp(`^<p class="${name}">`));
  }
});

test('ordinary prose passes through unchanged', () => {
  // An apostrophe is not escaped in text content, only inside an attribute
  // value - so real instructions read back exactly as written.
  assert.equal(rendered("You'll hear two samples."), "You'll hear two samples.");
});

test('prose with nothing in it renders no element at all', () => {
  // An empty element would still take up its margins on the page.
  for (const empty of ['', '   ', '\n\n', null, undefined]) {
    assert.equal(proseHtml(empty, 'prose'), '');
  }
});
