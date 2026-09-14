/**
 * Which config of a sequence the page is running, as the URLs it requests.
 *
 * A sequence runs several configs back to back from one page. Every stage is
 * served from the same config.php/save.php/audio routes, and the `stage`
 * query parameter - the stage's experiment_id - tells the server which
 * config to answer with. Mirrors frontend/stage.php and
 * listen_and_rate/dependencies.py. A lone config sets no stage, so its URLs
 * are exactly what they were before sequences existed.
 *
 * The current stage is module-level state, set by app.js as each stage
 * starts - like strings.js's language, and for the same reason: exactly one
 * stage runs at a time, so threading it through every constructor that
 * builds an audio URL would add parameters without adding information.
 */

/** Query parameter naming the stage; mirrors stage.php's STAGE_PARAM. */
const STAGE_PARAM = 'stage';

let _stage = null;

/** Set the stage whose config the page now runs (null for a lone config). */
export function setStage(stageId) {
  _stage = stageId ?? null;
}

/**
 * Return `path` naming the current stage, if any.
 *
 * @param {string} path - A backend URL, with or without a query already.
 * @returns {string}
 */
export function stageUrl(path) {
  if (_stage === null) return path;
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}${STAGE_PARAM}=${encodeURIComponent(_stage)}`;
}

/**
 * Resolve a stimulus's audio URL: the static file the PHP export put in the
 * bundle (audio_url, already specific to its stage), else the FastAPI /audio
 * route, which resolves the id within the named stage.
 *
 * @param {{id: string, audio_url?: string}} s
 * @returns {string}
 */
export function audioUrl(s) {
  return s.audio_url ?? stageUrl(`/audio/${encodeURIComponent(s.id)}`);
}
