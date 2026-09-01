/**
 * Tests for the labels on the last page's confirm button.
 *
 * Three states share one button, and the word has to match what pressing it
 * does: the practice round leads into the real test, a survey stands between
 * the last trial and the actual submission, and without one the button posts.
 */

import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import { stubDocument } from './_helpers.js';

// practiceBannerHtml renders prose, which reaches for document via escapeHtml.
const restore = stubDocument();
const practice = await import('../../js/practice.js');
const { finalButtonLabel, finalConfirmHint, practiceBadgeHtml, practiceBannerHtml } = practice;

after(restore);

const SURVEY = { fields: [{ key: 'trial_count' }] };

test('the practice round ends by starting the real test', () => {
  assert.equal(finalButtonLabel({ isPractice: true }), 'Start');
  // Practice wins even where a survey is configured: the survey comes after
  // the real test, not after the practice round.
  assert.equal(finalButtonLabel({ isPractice: true, survey: SURVEY }), 'Start');
});

test('a survey makes the last button finish rather than submit', () => {
  // "Submit" would be a lie with a questionnaire still to come.
  assert.equal(finalButtonLabel({ survey: SURVEY }), 'Finish');
  assert.equal(finalButtonLabel({}), 'Submit');
});

test('an empty survey block is not a survey', () => {
  // A survey with a title but no fields shows nothing, so nothing follows.
  assert.equal(finalButtonLabel({ survey: { title: 'Q', fields: [] } }), 'Submit');
});

test('the shortcut hint says the same thing as the button', () => {
  for (const config of [{ isPractice: true }, { survey: SURVEY }, {}]) {
    assert.equal(finalConfirmHint(config), finalButtonLabel(config).toLowerCase());
  }
});

// -- the practice markers ----------------------------------------------------

test('the practice badge and banner are absent from the real test', () => {
  assert.equal(practiceBadgeHtml({}), '');
  assert.equal(practiceBannerHtml({ practice_instructions: 'ignored' }), '');
});

test('the badge marks a practice page', () => {
  assert.match(practiceBadgeHtml({ isPractice: true }), /Practice/);
});

test('a practice stage with no wording shows no banner', () => {
  // The banner is a bordered, padded, coloured box - an empty one would sit
  // above the instructions saying nothing.
  assert.equal(practiceBannerHtml({ isPractice: true }), '');
  assert.equal(practiceBannerHtml({ isPractice: true, practice_instructions: '  ' }), '');
});

test('the banner carries the practice wording', () => {
  const html = practiceBannerHtml({
    isPractice: true,
    practice_instructions: 'Your ratings will not be recorded.',
  });
  assert.match(html, /class="practice-banner"/);
  assert.match(html, /Your ratings will not be recorded\./);
});
