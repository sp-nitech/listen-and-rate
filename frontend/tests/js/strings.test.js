/**
 * Tests for the UI-chrome string table (frontend/js/strings.js): locale
 * lookup, {name} interpolation, and the en/ja completeness invariant.
 *
 * Admin-authored config content (title, instructions, metadata/survey field
 * text, tie_label, rating_labels, ...) never goes through this table - it is
 * only for the fixed chrome the app itself renders (buttons, headings,
 * hints). See listen_and_rate/config/base.py's ui_language field.
 */

import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import { currentLanguage, STRINGS, setLanguage, t } from '../../js/strings.js';

after(() => setLanguage('en'));

test('en and ja carry the same set of keys', () => {
  // The real completeness guarantee behind t()'s STRINGS.en fallback - a key
  // added to one locale and forgotten in the other fails here, not silently
  // at render time.
  assert.deepEqual(new Set(Object.keys(STRINGS.ja)), new Set(Object.keys(STRINGS.en)));
});

test('t() reads the table for the language set by setLanguage()', () => {
  STRINGS.en.__test_key__ = 'hello';
  STRINGS.ja.__test_key__ = 'konnichiwa';
  try {
    setLanguage('en');
    assert.equal(t('__test_key__'), 'hello');
    setLanguage('ja');
    assert.equal(t('__test_key__'), 'konnichiwa');
  } finally {
    delete STRINGS.en.__test_key__;
    delete STRINGS.ja.__test_key__;
  }
});

test('t() substitutes named placeholders', () => {
  STRINGS.en.__test_key__ = 'Hello {name}, you have {count} messages';
  try {
    setLanguage('en');
    assert.equal(
      t('__test_key__', { name: 'World', count: 3 }),
      'Hello World, you have 3 messages'
    );
  } finally {
    delete STRINGS.en.__test_key__;
  }
});

test('t() leaves an unmatched placeholder literal rather than throwing', () => {
  // A visibly-wrong string during development beats a broken render.
  STRINGS.en.__test_key__ = 'Hello {name}';
  try {
    setLanguage('en');
    assert.equal(t('__test_key__', {}), 'Hello {name}');
    assert.equal(t('__test_key__'), 'Hello {name}');
  } finally {
    delete STRINGS.en.__test_key__;
  }
});

test('t() falls back to the literal key when it exists in neither language', () => {
  assert.equal(t('__totally_missing_key__'), '__totally_missing_key__');
});

test('setLanguage() rejects an unknown language by falling back to en', () => {
  setLanguage('fr');
  STRINGS.en.__test_key__ = 'hello';
  STRINGS.ja.__test_key__ = 'konnichiwa';
  try {
    assert.equal(t('__test_key__'), 'hello');
  } finally {
    delete STRINGS.en.__test_key__;
    delete STRINGS.ja.__test_key__;
  }
});

test('currentLanguage() reflects what setLanguage() actually resolved to', () => {
  // Lets a caller (e.g. app.js's document.documentElement.lang) read back
  // the resolved language instead of re-deriving the same undefined/unknown
  // fallback rule itself.
  setLanguage('ja');
  assert.equal(currentLanguage(), 'ja');
  setLanguage(undefined);
  assert.equal(currentLanguage(), 'en');
  setLanguage('fr');
  assert.equal(currentLanguage(), 'en');
});

// -- app.js's resume prompt / survey submit / completion screen -------------

test('the resume prompt is translated', () => {
  setLanguage('ja');
  assert.equal(t('resume_title'), '前回の続きから再開しますか？');
  assert.equal(t('resume_resumeButton'), '再開する');
  assert.equal(t('resume_progress', { page: 3, total: 10 }), '3 / 10 件目まで進んでいます。');
  setLanguage('en');
  assert.equal(t('resume_title'), 'Resume previous session?');
  assert.equal(t('resume_resumeButton'), 'Resume');
  assert.equal(t('resume_progress', { page: 3, total: 10 }), 'You were on item 3 of 10.');
});

test('the survey submit button and completion screen are translated', () => {
  setLanguage('ja');
  assert.equal(t('submit_label'), '送信');
  assert.equal(t('complete_title'), 'ありがとうございました！');
  setLanguage('en');
  assert.equal(t('submit_label'), 'Submit');
  assert.equal(t('complete_title'), 'Thank you!');
});

// -- metadata.js's default submit button and text-field placeholder ---------

test('the metadata form submit button and placeholder are translated', () => {
  setLanguage('ja');
  assert.equal(t('metadata_startButton'), 'テストを開始');
  assert.equal(t('metadata_textPlaceholder'), '半角英数字・ハイフン・ピリオドのみ使用可');
  setLanguage('en');
  assert.equal(t('metadata_startButton'), 'Start Test');
  assert.equal(t('metadata_textPlaceholder'), 'Letters, digits, hyphens, dots only');
});

// -- paired-trial-test.js's Prev button and choose-A/B hint ------------------

test('the Prev button and choose-A/B hint are translated', () => {
  setLanguage('ja');
  assert.equal(t('trial_prev'), '← 戻る');
  assert.equal(t('trial_hint_chooseA'), 'Aを選択');
  assert.equal(t('trial_hint_chooseB'), 'Bを選択');
  setLanguage('en');
  assert.equal(t('trial_prev'), '← Prev');
  assert.equal(t('trial_hint_chooseA'), 'choose A');
  assert.equal(t('trial_hint_chooseB'), 'choose B');
});

// -- ab.js's tie-hint segment -------------------------------------------------

test('the tie hint is translated', () => {
  setLanguage('ja');
  assert.equal(t('trial_hint_same'), '同じ');
  setLanguage('en');
  assert.equal(t('trial_hint_same'), 'same');
});

// -- mos.js's and mushra.js's rate hint, mushra's Shift-step hint -----------

test('the rate hint word is translated (shared by mos.js and mushra.js)', () => {
  setLanguage('ja');
  assert.equal(t('trial_hint_rate'), '評価');
  setLanguage('en');
  assert.equal(t('trial_hint_rate'), 'rate');
});

// -- listening-test.js's chrome (trial counter, Next, shortcut hint) --------

test('the trial counter and Next button are translated', () => {
  setLanguage('ja');
  assert.equal(t('trial_counter', { n: 3, total: 10 }), '評価 3 / 10');
  assert.equal(t('trial_next'), '次へ →');
  setLanguage('en');
  assert.equal(t('trial_counter', { n: 3, total: 10 }), 'Trial 3 / 10');
  assert.equal(t('trial_next'), 'Next →');
});

// -- practice.js's final button label ----------------------------------------

test('the practice final-button labels are translated', () => {
  setLanguage('ja');
  assert.equal(t('practice_startButton'), '開始');
  assert.equal(t('practice_finishButton'), '終了');
  setLanguage('en');
  assert.equal(t('practice_startButton'), 'Start');
  assert.equal(t('practice_finishButton'), 'Finish');
});

test('the shortcut hint words are translated', () => {
  setLanguage('ja');
  assert.equal(t('trial_hint_playPause'), '再生/一時停止');
  assert.equal(t('trial_hint_rewind'), '巻き戻し');
  assert.equal(t('trial_hint_navigate'), '移動');
  assert.equal(t('trial_hint_next'), '次へ');
  setLanguage('en');
  assert.equal(t('trial_hint_playPause'), 'play/pause');
  assert.equal(t('trial_hint_rewind'), 'rewind');
  assert.equal(t('trial_hint_navigate'), 'navigate');
  assert.equal(t('trial_hint_next'), 'next');
});
