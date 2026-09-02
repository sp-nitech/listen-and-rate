/**
 * English UI-chrome strings - the fixed buttons/headings/hints the app
 * itself renders, never the admin-authored config content (title,
 * instructions, metadata/survey field text, ...). See ../strings.js.
 *
 * Keys are named `<concern>_<leaf>`, where concern is always a bare noun -
 * no "Test"/"Prompt"/etc. suffix - naming the UI area the string belongs to
 * (metadata, practice, trial, submit, complete, resume), not the source
 * file's own name. A leaf's own English text never appears in its key, so a
 * later wording change never implies a rename. Grouped by concern below (not
 * alphabetical), in the same order as strings/ja.js - not a literal line-for-
 * line match, since only this file carries explanatory comments.
 */
export const en = {
  metadata_startButton: 'Start Test',
  metadata_textPlaceholder: 'Letters, digits, hyphens, dots only',

  practice_startButton: 'Start',
  practice_finishButton: 'Finish',

  // "Trial" is this codebase's own term for one presentation-and-response
  // page (see listening-test.js) - shared chrome for every test type, not
  // just MOS's, so the key names the concept rather than that one file.
  trial_counter: 'Trial {n} / {total}',
  trial_prev: '← Prev',
  trial_next: 'Next →',
  trial_hint_playPause: 'play/pause',
  trial_hint_rewind: 'rewind',
  trial_hint_rate: 'rate',
  trial_hint_navigate: 'navigate',
  trial_hint_next: 'next',
  trial_hint_chooseA: 'choose A',
  trial_hint_chooseB: 'choose B',
  trial_hint_same: 'same',

  submit_label: 'Submit',
  submit_busyLabel: 'Submitting…',

  complete_title: 'Thank you!',
  complete_body: 'Your ratings have been saved successfully.',

  resume_title: 'Resume previous session?',
  resume_body: 'An unfinished session was found on this device.',
  resume_progress: 'You were on item {page} of {total}.',
  resume_resumeButton: 'Resume',
  resume_startOverButton: 'Start over',
};
