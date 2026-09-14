import { stageUrl } from './stage.js';

/**
 * Fetch the test configuration from the server - the current stage's (see
 * stage.js), or, before any stage is set, whatever the page is: a lone
 * config, or a sequence's manifest ({sequence: [stage ids]}).
 *
 * @returns {Promise<Object>} Config object with test_type, stimuli, shortcuts, etc.
 * @throws {Error} If the response is not OK.
 */
export async function fetchConfig() {
  const res = await fetch(stageUrl('config.php'));
  if (!res.ok) throw new Error(`Failed to load config: ${res.status}`);
  return res.json();
}

/**
 * Submit a completed set of listener responses to the current stage.
 *
 * @param {{ session_id: string, test_type: string, ratings?: Array, choices?: Array, metadata?: Object }} data
 *   - `ratings` for MOS/DMOS/MUSHRA, `choices` for CMOS/AB/ABX/XAB.
 * @returns {Promise<Object>} Server response { status: 'ok', session_id }
 * @throws {Error} If the server rejects the submission (4xx/5xx).
 */
export async function submitRatings(data) {
  const res = await fetch(stageUrl('save.php'), {
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
