/**
 * Entry point: fetches the configs, then runs the page's stages with this
 * page's screens (see sequence.js for the order of the steps). Shows an error
 * screen on any failure.
 */

import { fetchConfig } from './api.js';
import { MetadataPage } from './metadata.js';
import { practiceItems } from './practice.js';
import { preflight } from './preflight.js';
import { pruneExpiredRecords, saveRecord } from './resume.js';
import {
  applyConfigChrome,
  promptNextStage,
  promptResume,
  showComplete,
  showLoadError,
  showPreflightErrors,
} from './screens.js';
import { chooseStart, openSession, planStages, runStages } from './sequence.js';
import { Stage } from './stage.js';
import { runStage, testClassFor } from './stage-runner.js';
import { setLanguage } from './strings.js';

async function main() {
  const container = document.getElementById('app');
  // Before any stage is named, config.php answers with what the page is: a
  // lone config, or a sequence's manifest listing its stages in order.
  const first = await fetchConfig(new Stage(null));
  const stageIds = first.sequence ?? [null];
  const freshConfigs = first.sequence
    ? await Promise.all(stageIds.map((id) => fetchConfig(new Stage(id))))
    : [first];
  // Set before any DOM is touched - the resume prompt needs translated
  // strings too. Re-set as each stage runs (see applyConfigChrome).
  setLanguage(freshConfigs[0].ui_language);

  const now = Date.now();
  const start = await chooseStart(freshConfigs, pruneExpiredRecords(now), now, {
    askResume: (record, index) => {
      setLanguage(freshConfigs[index].ui_language);
      return promptResume(container, record);
    },
  });
  const planned = planStages(stageIds, freshConfigs, start);
  applyConfigChrome(planned[0].config);

  for (const { config } of planned) testClassFor(config);
  const problems = await preflight(
    planned.map(({ stage, config }, i) => ({
      stage,
      config,
      withPractice: !(i === 0 && start.resumed) && practiceItems(config).length > 0,
    }))
  );
  if (problems.missing.length > 0 || problems.saveErrors.length > 0) {
    showPreflightErrors(container, problems);
    return;
  }

  container.innerHTML = '';
  const session = await openSession(start, freshConfigs[0], async (form) => {
    const metaPage = new MetadataPage(form.fields, {
      title: form.title,
      description: form.description,
    });
    const answers = await metaPage.collect(container);
    container.innerHTML = '';
    return answers;
  });

  // Saved with every record, so only this same sequence resumes it.
  const sequence = freshConfigs.map((config) => config.experiment_id);
  await runStages(planned, sequence, session, start.resumed?.progress ?? null, {
    runStage: (current, progress) => runStage(container, current, sequence, session, progress),
    promptNextStage: (stage, done, total) => promptNextStage(container, stage, done, total),
    showComplete: (stage) => showComplete(container, stage),
    saveRecord,
    now: Date.now,
  });
}

main().catch((err) => showLoadError(document.getElementById('app'), err));
