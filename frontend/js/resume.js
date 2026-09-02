/**
 * Client-side resume: persist an in-progress session to localStorage so a
 * listener who closes the tab, reloads, or steps away can pick up where they
 * left off. The server holds no state - the entire delivered config response
 * (its already-sampled, already-shuffled subset, and any x tokens) is frozen
 * into the record alongside the answers, because re-fetching config would
 * re-sample and re-shuffle into a different test.
 *
 * A record is offered for resume only when it still matches the current config
 * (fingerprint) and was last touched within the window the config asks for
 * (resume.max_age_hours, delivered as resume.max_age_ms). Every window here is
 * a parameter rather than a constant: the default belongs to the config schema
 * (see ResumeConfig), and a second copy of it in this file could drift from it.
 */

/** Shared prefix of every saved record's key, so they can be enumerated. */
const RECORD_KEY_PREFIX = 'lar:session:';

/** localStorage key, namespaced per experiment so distinct tests don't collide. */
export function recordKey(experimentId) {
  return `${RECORD_KEY_PREFIX}${experimentId ?? ''}`;
}

/** Load and parse the saved record, or null if absent/corrupt. */
export function loadRecord(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/** Persist the record (best-effort; storage may be full or disabled). */
export function saveRecord(key, record) {
  try {
    localStorage.setItem(key, JSON.stringify(record));
  } catch {
    // Ignore: resume is a convenience, never a correctness requirement.
  }
}

/** Remove the saved record (on completion or an explicit start-over). */
export function clearRecord(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignore.
  }
}

/**
 * Drop every saved record past its own window, across all experiments.
 *
 * A record is otherwise only removed when the listener declines the prompt or
 * finishes the test. One that merely expired - or whose config changed under
 * it - is never offered again yet stays forever, and each record holds a whole
 * delivered config, so an origin that has served several experiments keeps
 * accumulating dead weight. saveRecord() swallows the resulting quota error,
 * which would silently disable resume for the session actually running.
 *
 * Each record is judged against its own window - read off its own frozen
 * config.resume.max_age_ms, never against the window of the experiment doing
 * the pruning: this runs over every experiment served from the origin, and
 * one with a short window must not delete a still-resumable session
 * belonging to an experiment with a long one. A record with no window of its
 * own (saved before config carried one at all) is dropped outright: it can
 * never become resumable again either way - isResumable() also needs the
 * fresh config's window - so there is nothing to gain by guessing at what its
 * window might have been.
 *
 * Only the age is used beyond that: a fingerprint mismatch can be temporary
 * (the config is edited back), so an unexpired record is left alone whether
 * or not it matches the config being served right now.
 *
 * Returns every surviving record, keyed by its storage key: the scan already
 * parses each one's JSON to judge its age, so a caller that needs its own
 * record back (see app.js) can read it from here instead of parsing the same
 * blob a second time.
 *
 * @param {number} now - Date.now().
 * @returns {Map<string, Object>}
 */
export function pruneExpiredRecords(now) {
  const records = new Map();
  try {
    const stale = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key?.startsWith(RECORD_KEY_PREFIX)) continue;
      const record = loadRecord(key);
      const maxAgeMs = record?.config?.resume?.max_age_ms;
      // A record with no usable savedAt, or no window of its own, can never
      // become resumable either.
      if (
        !record ||
        typeof record.savedAt !== 'number' ||
        typeof maxAgeMs !== 'number' ||
        now - record.savedAt >= maxAgeMs
      ) {
        stale.push(key);
      } else {
        records.set(key, record);
      }
    }
    for (const key of stale) localStorage.removeItem(key);
  } catch {
    // Ignore: pruning is housekeeping, never a correctness requirement.
  }
  return records;
}

/**
 * Whether `record` may be offered for resume: it exists, its fingerprint still
 * matches the freshly fetched config_version, and it was saved recently enough.
 *
 * `maxAgeMs` is the window from the config just fetched rather than the one the
 * record was saved with, so an edited window takes effect on the next visit in
 * both directions - a widened one rescues a record that had aged out, and 0
 * (resume off) stops offering every record immediately.
 *
 * @param {Object|null} record
 * @param {string} freshVersion - config_version from the current /config fetch.
 * @param {number} now - Date.now().
 * @param {number} maxAgeMs - resume.max_age_ms from the current config (0 = off).
 */
export function isResumable(record, freshVersion, now, maxAgeMs) {
  return (
    !!record &&
    record.fingerprint === freshVersion &&
    typeof record.savedAt === 'number' &&
    now - record.savedAt < maxAgeMs
  );
}
