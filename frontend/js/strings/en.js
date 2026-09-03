/**
 * English UI-chrome strings - the fixed buttons/headings/hints the app
 * itself renders, never the admin-authored config content (title,
 * instructions, metadata/survey field text, ...). See ../strings.js.
 *
 * Keys are named `<concern>` or `<concern>_<leaf>`, where concern is a bare
 * noun - no "Test"/"Prompt"/etc. suffix - naming the UI area the string
 * belongs to, not the source file's own name. The leaf distinguishes the
 * strings within one area, and is dropped where an area has only one. It
 * says which string this is, never what it happens to say: no "label" or
 * "text" suffix, since every value here is one. Grouped by concern below
 * (not alphabetical), in the same order as strings/ja.js - not a literal
 * line-for-line match, since only this file carries explanatory comments.
 */
export const en = {
  metadata_textPlaceholder: 'Letters, digits, hyphens, dots only',
  metadata_startTest: 'Start Test',

  practice_startTest: 'Start',

  trial_counter: 'Trial {n} / {total}',
  trial_prev: '← Prev',
  trial_next: 'Next →',
  trial_finish: 'Finish',
  trial_hint_playPause: 'play/pause',
  trial_hint_rewind: 'rewind',
  trial_hint_rate: 'rate',
  trial_hint_chooseA: 'choose A',
  trial_hint_chooseB: 'choose B',
  trial_hint_same: 'same',
  trial_hint_navigate: 'navigate',
  trial_hint_next: 'next',

  submit_idle: 'Submit',
  submit_busy: 'Submitting…',

  complete_title: 'Thank you!',
  complete_body: 'Your ratings have been saved successfully.',

  resume_title: 'Resume previous session?',
  resume_body: 'An unfinished session was found on this device.',
  resume_progress: 'You were on item {page} of {total}.',
  resume_resume: 'Resume',
  resume_startOver: 'Start over',
};
