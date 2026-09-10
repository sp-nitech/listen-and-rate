/**
 * pair_survey listening test UI: one source clip and one generated clip per
 * page, answering whatever questions the server config declares about the
 * generated clip.
 *
 * Roles are disclosed (source_label / generated_label from the config), not
 * blinded as A/B. Playback is gated the same way as DMOS: both clips must
 * be heard in full before any question opens up. A page counts as answered
 * once every required question has a value, which is what gates Next and
 * drives the progress bar.
 */

import { escapeHtml } from '../dom.js';
import { t } from '../strings.js';
import { saveProgressPayload, submitPayload } from '../submit.js';
import { PairedTrialTest } from './paired-trial-test.js';

/** The answer buttons for one question, as {value, label} pairs. */
function optionsOf(question) {
  if (question.type === 'scale') {
    return question.values.map((v) => ({
      value: String(v),
      label: String(v),
      caption: question.labels?.[String(v)] ?? '',
    }));
  }
  return question.options.map((o) => ({ value: o, label: o, caption: '' }));
}

export class PairSurveyTest extends PairedTrialTest {
  /**
   * @param {Object} config - Server config from /api/config (has `trials`, `questions`).
   * @param {string} sessionId - UUID identifying this listener's session.
   * @param {Function} onSubmit - Async callback invoked with (sessionId, testType, {choices}).
   */
  constructor(config, sessionId, onSubmit) {
    super(config, sessionId, onSubmit);
    this.questions = config.questions ?? [];
    this.sourceLabel = config.source_label ?? 'Source';
    this.generatedLabel = config.generated_label ?? 'Generated';
    // choices: trial index → {key: value}. A plain object rather than a Map
    // so the resume record round-trips through JSON unchanged (see
    // _serializeAnswers on the base class).
    this.shortcuts = config.shortcuts ?? {};
  }

  // -- answer bookkeeping ----------------------------------------------------

  /** This trial's answers, created empty on first access. */
  _answersFor(trialIndex) {
    if (!this.choices.has(trialIndex)) {
      this.choices.set(trialIndex, {});
    }
    return this.choices.get(trialIndex);
  }

  /**
   * A page is answered when every required question has a value. Overrides
   * the base class's "any choice recorded", which cannot express a partly
   * filled page.
   */
  _isAnswered(trialIndex) {
    const answers = this.choices.get(trialIndex);
    if (!answers) return false;
    return this.questions
      .filter((q) => q.required)
      .every((q) => answers[q.key] !== undefined);
  }

  _answeredCount() {
    let n = 0;
    for (let i = 0; i < this._trialCount(); i++) if (this._isAnswered(i)) n++;
    return n;
  }

  // -- build-once structure --------------------------------------------------

  _listenStepsHtml() {
    return `
      <span class="step-listen">${t('pair_survey_step_listen')}</span>
      <span class="step-sep">→</span>
      <span class="step-rate">${t('pair_survey_step_answer')}</span>
    `;
  }

  _ratingButtonsClass() {
    return 'pair-survey-questions';
  }

  _audioRegionHtml() {
    return `<div class="ab-pair">${this._audioCardHtml(escapeHtml(this.sourceLabel), 0)}${this._audioCardHtml(escapeHtml(this.generatedLabel), 1)}</div>`;
  }

  _choiceButtonsHtml() {
    return this.questions.map((q) => this._questionHtml(q)).join('');
  }

  /**
   * One question: its label and a row of buttons. `data-question` is what
   * _onChoiceButton reads back - the base class hands it the clicked element
   * and nothing else, and with several questions on a page the button has to
   * say which one it belongs to.
   */
  _questionHtml(question) {
    const buttons = optionsOf(question)
      .map(
        (o) => `
        <button class="rating-btn" type="button"
                data-question="${escapeHtml(question.key)}"
                data-value="${escapeHtml(o.value)}">
          <span class="rating-score">${escapeHtml(o.label)}</span>
          ${o.caption ? `<span class="rating-word">${escapeHtml(o.caption)}</span>` : ''}
        </button>
      `
      )
      .join('');
    const optional = question.required
      ? ''
      : ` <span class="question-optional">${t('pair_survey_optional')}</span>`;
    const description = question.description
      ? `<p class="question-description">${escapeHtml(question.description)}</p>`
      : '';
    return `
      <div class="question-block" data-question="${escapeHtml(question.key)}">
        <p class="question-label">${escapeHtml(question.label)}${optional}</p>
        ${description}
        ${this._helpHtml(question)}
        <div class="question-options">${buttons}</div>
      </div>
    `;
  }

  /** Expandable list of each scale point's long rubric text. */
  _helpHtml(question) {
    const help = question.help;
    if (!help || Object.keys(help).length === 0) return '';
    const values = [...(question.values ?? [])].reverse();
    const rows = values
      .filter((v) => help[String(v)])
      .map((v) => {
        const key = String(v);
        const name = question.labels?.[key] ?? '';
        const title = name ? `${key} ${name}` : key;
        return `<li><span class="question-help-score">${escapeHtml(title)}</span> ${escapeHtml(help[key])}</li>`;
      })
      .join('');
    if (!rows) return '';
    return `
      <details class="question-help">
        <summary class="question-help-summary">${escapeHtml(t('pair_survey_help'))}</summary>
        <ul class="question-help-list">${rows}</ul>
      </details>
    `;
  }

  // -- per-trial sync --------------------------------------------------------

  _trialAudioClips(trial) {
    return { 0: this._clip(trial.source), 1: this._clip(trial.generated) };
  }

  _syncChoiceButtons() {
    const canChoose = this._canChoose(this.currentIndex);
    const current = this.choices.get(this.currentIndex) ?? {};
    for (const btn of this._el.buttons) {
      btn.classList.toggle('selected', current[btn.dataset.question] === btn.dataset.value);
      btn.disabled = !canChoose;
    }
  }

  _onChoiceButton(btn) {
    const answers = this._answersFor(this.currentIndex);
    answers[btn.dataset.question] = btn.dataset.value;
    this._syncChoiceButtons();
    this._syncNextEnabled();
    this._updateProgressBar();
    this._onChange?.();
  }

  _canChoose(trialIndex) {
    return this._playedSet(trialIndex).size >= 2;
  }

  /**
   * No answer keys: with several questions on a page, a single keypress
   * cannot say which one it is answering. Play/rewind/navigate still work.
   */
  _handleChoiceKey() {
    return false;
  }

  _choiceHintHtml() {
    return t('pair_survey_hint_answer');
  }

  /** Answered trials in the shape POST /api/submit expects. */
  _choicesPayload() {
    return {
      choices: Array.from(this.choices.entries())
        .filter(([trialIndex]) => this._isAnswered(trialIndex))
        .map(([trialIndex, answers]) => {
          const trial = this.trials[trialIndex];
          return {
            stimulus_ids: [trial.source.id, trial.generated.id],
            answers,
            dwell_time: this._dwellOf(trialIndex),
          };
        }),
    };
  }

  /**
   * Persist the current answers before leaving a pair. Failure stays on this
   * page so the rating is not dropped. Practice skips the network (see
   * saveProgressPayload).
   */
  async _nextOrSubmit() {
    if (this._saving) return;
    if (this.currentIndex < this._trialCount() - 1) {
      if (!this._isAnswered(this.currentIndex)) return;
      this._stopDwellClock();
      this._saving = true;
      try {
        await saveProgressPayload(this, () => this._choicesPayload());
        this._navigate(1);
      } catch {
        // Error already shown; stay on this pair and keep measuring dwell.
        this._startDwellClock();
      } finally {
        this._saving = false;
      }
    } else if (this._answeredCount() === this._trialCount()) {
      this._stopDwellClock();
      this._submit();
    }
  }

  /** ArrowRight must save too, not only the Next button. */
  _onNextShortcut() {
    this._nextOrSubmit();
  }

  async _submit() {
    await submitPayload(this, () => this._choicesPayload());
  }
}
