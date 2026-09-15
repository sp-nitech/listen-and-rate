/**
 * How a page load runs its stages: where it starts, the session it runs
 * under, and the hand-over from one stage to the next.
 *
 * The page runs one config, or several back to back as a sequence - config.php
 * then answers with a manifest naming the stages. Each stage runs as a lone
 * config would - its own practice, test, and survey, submitted to its own
 * results - under one session id and one set of metadata answers, asked
 * before the first. A lone config is a sequence of one.
 *
 * Only the order of the steps lives here. The screens and a stage's own run
 * are passed in (see app.js), so the order - which is what a resumed or
 * interrupted session depends on - is checked without a page
 * (tests/js/sequence.test.js).
 */

import { hasFormPage } from './metadata.js';
import { pageCount, stageSpans } from './progress.js';
import {
  buildRecord,
  clearStageRecords as clearAllStageRecords,
  findResumableStage,
  recordKey,
} from './resume.js';
import { generateSessionId } from './session.js';
import { Stage } from './stage.js';

/**
 * Decide where this page load starts, from the saved records.
 *
 * With nothing to resume, the first stage starts with a new session.
 * Otherwise the saved session is offered back - a stage in progress, or one
 * handed its session but not started yet (see runStages). Resuming continues
 * at that stage with the session id and metadata answers, restoring its
 * frozen config and answers when it was in progress. Starting over clears
 * every stage's record and begins the whole sequence again with a new
 * session, as a lone config does: keeping the old session instead would, on
 * a shared device, pass one listener's id and answers on to the next.
 *
 * @param {Object[]} configs - Each stage's freshly fetched config, in order.
 * @param {Map<string, Object>} records - pruneExpiredRecords()'s survivors.
 * @param {number} now - Date.now().
 * @param {{askResume: Function, clearStageRecords?: Function}} deps -
 *   askResume(record, index) offers the saved session and resolves true to
 *   resume it; clearStageRecords defaults to resume.js's.
 * @returns {Promise<{index: number, carried: Object|null, resumed: Object|null}>}
 *   carried: {sessionId, metadata} to continue with, or null for a new
 *   session. resumed: the saved record to restore, or null to start afresh.
 */
export async function chooseStart(
  configs,
  records,
  now,
  { askResume, clearStageRecords = clearAllStageRecords }
) {
  const found = findResumableStage(configs, records, now);
  if (!found) return { index: 0, carried: null, resumed: null };
  const { index, record } = found;
  if (await askResume(record, index)) {
    return {
      index,
      carried: { sessionId: record.sessionId, metadata: record.metadata ?? {} },
      resumed: record.progress ? record : null,
    };
  }
  clearStageRecords(configs);
  return { index: 0, carried: null, resumed: null };
}

/**
 * Return the stages this load runs, from the one it starts at.
 *
 * A resumed stage runs the frozen config it was started with - re-fetching
 * would re-sample and re-shuffle into a different test (and re-mint x
 * tokens); every other stage runs the config just fetched. The progress bar
 * spans the whole session, each stage its share of it - the stages already
 * submitted included, so a resumed session's bar starts where they left it.
 *
 * @param {Array<string|null>} stageIds - The manifest's ids, or [null] for a
 *   lone config's page, whose requests name no stage.
 * @param {Object[]} freshConfigs - Each stage's freshly fetched config.
 * @param {{index: number, resumed: Object|null}} start - chooseStart's answer.
 * @returns {Array<{index: number, stage: Stage, config: Object}>}
 */
export function planStages(stageIds, freshConfigs, start) {
  const configs = freshConfigs.map((config, i) =>
    i === start.index && start.resumed ? start.resumed.config : config
  );
  const spans = stageSpans(configs.map(pageCount));
  return stageIds
    .map((id, index) => ({ index, stage: new Stage(id, spans[index]), config: configs[index] }))
    .slice(start.index);
}

/**
 * Return the session this load runs under: the one carried on from a saved
 * record, or a new one - which asks the first config's metadata form, when
 * it has anything to show. Prose alone is reason enough to show the page: a
 * study may need to state what it collects without collecting anything on
 * that page itself.
 *
 * @param {{carried: Object|null}} start - chooseStart's answer.
 * @param {Object} firstConfig - The first stage's config, whose form it is.
 * @param {Function} askMetadata - askMetadata(form) resolves the answers.
 * @returns {Promise<{sessionId: string, metadata: Object}>}
 */
export async function openSession(start, firstConfig, askMetadata) {
  if (start.carried) return start.carried;
  const metadata = hasFormPage(firstConfig.metadata) ? await askMetadata(firstConfig.metadata) : {};
  return { sessionId: generateSessionId(), metadata };
}

/**
 * Run the planned stages one after another, then end the session.
 *
 * Between two stages the session is handed on to the next one - its record
 * saved with nothing done yet - before the listener is asked to go on, so a
 * tab closed on that screen offers to continue at the next stage.
 *
 * @param {Array<{index: number, stage: Stage, config: Object}>} planned - planStages's.
 * @param {string[]} sequence - Every stage's experiment_id, saved with each record.
 * @param {{sessionId: string, metadata: Object}} session
 * @param {Object|null} progress - Saved progress for the first planned stage.
 * @param {Object} deps - runStage(planned, progress) runs one stage;
 *   promptNextStage(stage, done, total) and showComplete(stage) are the
 *   screens after one; saveRecord and now are resume.js's and Date.now.
 * @returns {Promise<void>}
 */
export async function runStages(planned, sequence, session, progress, deps) {
  for (const [i, current] of planned.entries()) {
    await deps.runStage(current, i === 0 ? progress : null);
    const next = planned[i + 1];
    if (!next) break;
    if (next.config.resume.max_age_ms > 0) {
      deps.saveRecord(
        recordKey(next.config.experiment_id),
        buildRecord(next.config, sequence, session.sessionId, session.metadata, null, deps.now())
      );
    }
    await deps.promptNextStage(current.stage, current.index + 1, sequence.length);
  }
  deps.showComplete(planned[planned.length - 1].stage);
}
