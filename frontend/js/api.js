/**
 * The rater id this page was opened with (`?rater=alice`), or null.
 *
 * It comes from the URL rather than the pre-test metadata form because the
 * server needs it to pick which trials to build, and the form is not shown
 * until after the config response has arrived.
 *
 * @returns {string|null}
 */
export function currentRater() {
  return new URLSearchParams(window.location.search).get('rater') || null;
}

/**
 * Fetch the test configuration from the server.
 *
 * @param {string|null} [rater] - Whose task list to fetch; omitted when null.
 * @returns {Promise<Object>} Config object with test_type, stimuli, shortcuts, etc.
 * @throws {Error} If the response is not OK.
 */
export async function fetchConfig(rater = null) {
  const query = rater === null ? '' : `?rater=${encodeURIComponent(rater)}`;
  const res = await fetch(`config.php${query}`);
  if (!res.ok) {
    // The rater-assignment failures (no id, unknown id) are 400s whose detail
    // tells the listener what to do, so surface it instead of a bare status.
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to load config: ${res.status}`);
  }
  return res.json();
}

/**
 * Submit a completed set of listener responses.
 *
 * @param {{ session_id: string, test_type: string, ratings?: Array, choices?: Array, metadata?: Object }} data
 *   - `ratings` for MOS/DMOS/MUSHRA, `choices` for CMOS/AB/ABX/XAB.
 * @returns {Promise<Object>} Server response { status: 'ok', session_id }
 * @throws {Error} If the server rejects the submission (4xx/5xx).
 */
export async function submitRatings(data) {
  const res = await fetch('save.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Submit failed: ${res.status}`);
  }
  return res.json();
}
