/**
 * Client-side resume: persist an in-progress session to localStorage so a
 * listener who closes the tab, reloads, or steps away can pick up where they
 * left off. The server holds no state - the entire delivered config response
 * (its already-sampled, already-shuffled subset, and any x tokens) is frozen
 * into the record alongside the answers, because re-fetching config would
 * re-sample and re-shuffle into a different test.
 *
 * A record is offered for resume only when it still matches the current config
 * (fingerprint) and was last touched within RESUME_MAX_AGE_MS.
 */

/** Two hours, measured from the last save (refreshed on every answer/navigation). */
export const RESUME_MAX_AGE_MS = 2 * 60 * 60 * 1000;

/** localStorage key, namespaced per experiment so distinct tests don't collide. */
export function recordKey(experimentId) {
  return `lar:session:${experimentId ?? ''}`;
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
 * Whether `record` may be offered for resume: it exists, its fingerprint still
 * matches the freshly fetched config_version, and it was saved recently enough.
 *
 * @param {Object|null} record
 * @param {string} freshVersion - config_version from the current /config fetch.
 * @param {number} now - Date.now().
 * @param {number} [maxAgeMs]
 */
export function isResumable(record, freshVersion, now, maxAgeMs = RESUME_MAX_AGE_MS) {
  return (
    !!record &&
    record.fingerprint === freshVersion &&
    typeof record.savedAt === 'number' &&
    now - record.savedAt < maxAgeMs
  );
}
