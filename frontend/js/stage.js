/**
 * One config of the sequence the page runs, as the page reaches it.
 *
 * A sequence runs several configs back to back from one page - a lone config
 * being a sequence of one. Every stage is served from the same config.php/
 * save.php/audio routes, and the `stage` query parameter - the stage's
 * experiment_id - tells the server which config to answer with. Mirrors
 * frontend/stage.php and listen_and_rate/dependencies.py. A lone config's
 * page names no stage, so its URLs stay bare.
 *
 * Each stage also takes a share of the shared progress bar (see progress.js),
 * so a Stage places its own progress there.
 *
 * Passed to whatever builds a URL or moves the bar for the stage, rather than
 * held as the page's current stage: a URL then names the stage it was built
 * for, however the requests around it are ordered.
 */

import { paintProgressBar } from './progress.js';

/** Query parameter naming the stage; mirrors stage.php's STAGE_PARAM. */
const STAGE_PARAM = 'stage';

export class Stage {
  /**
   * @param {string|null} id - The stage's experiment_id; null for a lone
   *   config's page, whose requests name no stage.
   * @param {{start: number, width: number}} [span] - The stage's share of the
   *   progress bar, as fractions of it (see progress.js's stageSpans).
   */
  constructor(id, span = { start: 0, width: 1 }) {
    this.id = id;
    this.span = span;
  }

  /**
   * Return `path` naming this stage, if the page runs several.
   *
   * @param {string} path - A backend URL, with or without a query already.
   * @returns {string}
   */
  url(path) {
    if (this.id === null) return path;
    const separator = path.includes('?') ? '&' : '?';
    return `${path}${separator}${STAGE_PARAM}=${encodeURIComponent(this.id)}`;
  }

  /**
   * Resolve a stimulus's audio URL: the static file the PHP export put in the
   * bundle (audio_url, already specific to its stage), else the FastAPI
   * /audio route, which resolves the id within this stage.
   *
   * @param {{id: string, audio_url?: string}} s
   * @returns {string}
   */
  audioUrl(s) {
    return s.audio_url ?? this.url(`/audio/${encodeURIComponent(s.id)}`);
  }

  /**
   * Return the fraction of the whole bar reached by `fraction` of this stage.
   *
   * @param {number} fraction - How much of this stage is done, 0 to 1.
   * @returns {number}
   */
  progressAt(fraction) {
    return this.span.start + this.span.width * fraction;
  }

  /** Show `fraction` (0 to 1) of this stage done on the shared bar. */
  showProgress(fraction) {
    paintProgressBar(this.progressAt(fraction));
  }
}
