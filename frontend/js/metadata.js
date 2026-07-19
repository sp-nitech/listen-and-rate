/**
 * MetadataPage - a standalone form page built from a field definition array.
 *
 * Used twice per experiment, once per {title, fields} form block: the
 * pre-test listener-information form (config.metadata) and the post-test
 * survey (config.survey). Both are built from the block's fields array plus
 * its title via the {title, submitLabel} options. Returns a Promise that
 * resolves with {key: value, ...} when the listener clicks the submit button.
 *
 * Supported field types:
 *   text   - free-text input; only [a-zA-Z0-9\-] allowed
 *   select - radio button group from options[]
 */

import { escapeHtml } from './dom.js';

const _TEXT_PATTERN = /^[a-zA-Z0-9-]+$/;

export class MetadataPage {
  /**
   * @param {Array<{key:string, label:string, type:string, options?:string[], required:boolean}>} fields
   * @param {{title?: string, submitLabel?: string}} [options] - Page heading
   *   and submit-button label; the defaults are the pre-test metadata form's.
   */
  constructor(fields, options = {}) {
    this.fields = fields;
    this.title = options.title ?? 'Listener Information';
    this.submitLabel = options.submitLabel ?? 'Start Test';
    this._values = {};
    // Pre-select a value ONLY when the config explicitly declares a default.
    // Auto-selecting the first option would bias answers toward it (default
    // bias - especially harmful for survey questions); without a default the
    // field starts unanswered, and a required one blocks submission until
    // the listener actively chooses.
    for (const f of fields) {
      if (f.default) {
        this._values[f.key] = f.default;
      }
    }
  }

  /**
   * Render the form into container.
   * @param {HTMLElement} container
   * @returns {Promise<Object>} Resolves with {key: value, ...} on submission.
   */
  collect(container) {
    return new Promise((resolve) => {
      container.innerHTML = '';

      const page = document.createElement('div');
      page.className = 'metadata-page';
      page.innerHTML = `
        <div class="metadata-form">
          <h2 class="metadata-title">${escapeHtml(this.title)}</h2>
          ${this.fields.map((f) => this._renderField(f)).join('')}
          <button class="btn btn-primary metadata-start" id="metadata-start" type="button" disabled>
            ${escapeHtml(this.submitLabel)}
          </button>
        </div>
      `;
      container.appendChild(page);
      this._bindEvents(page, resolve);
    });
  }

  _renderField(f) {
    const labelHtml = `${escapeHtml(f.label)}${f.required ? ' <span class="required-mark">*</span>' : ''}`;

    if (f.type === 'text') {
      return `
        <div class="metadata-field">
          <label class="metadata-label" for="meta-${escapeHtml(f.key)}">${labelHtml}</label>
          <input class="metadata-input" type="text" id="meta-${escapeHtml(f.key)}"
                 data-key="${escapeHtml(f.key)}" autocomplete="off" spellcheck="false"
                 placeholder="Letters, digits, hyphens only">
        </div>`;
    }

    if (f.type === 'select') {
      // No implicit first-option default: unchecked unless the config says so.
      const radios = (f.options ?? [])
        .map(
          (opt) => `
        <label class="radio-option">
          <input type="radio" name="meta-${escapeHtml(f.key)}"
                 data-key="${escapeHtml(f.key)}" value="${escapeHtml(opt)}"
                 ${opt === f.default ? 'checked' : ''}>
          <span>${escapeHtml(opt)}</span>
        </label>`
        )
        .join('');
      return `
        <div class="metadata-field">
          <p class="metadata-label">${labelHtml}</p>
          <div class="radio-group">${radios}</div>
        </div>`;
    }

    return '';
  }

  _bindEvents(page, resolve) {
    for (const input of page.querySelectorAll('input[type="text"]')) {
      input.addEventListener('input', () => {
        const clean = input.value.replace(/[^a-zA-Z0-9-]/g, '');
        if (clean !== input.value) input.value = clean;
        this._values[input.dataset.key] = clean;
        this._updateStart(page);
      });
    }

    for (const radio of page.querySelectorAll('input[type="radio"]')) {
      radio.addEventListener('change', () => {
        if (radio.checked) {
          this._values[radio.dataset.key] = radio.value;
          this._updateStart(page);
        }
      });
    }

    page.querySelector('#metadata-start')?.addEventListener('click', () => {
      resolve({ ...this._values });
    });

    // Set the button's initial state - without this, a form whose fields are
    // all optional (or all selects with defaults) would stay disabled until
    // the first input event, which never comes if the user changes nothing.
    this._updateStart(page);
  }

  _updateStart(page) {
    const allValid = this.fields
      .filter((f) => f.required)
      .every((f) => {
        const val = this._values[f.key] ?? '';
        return f.type === 'text' ? _TEXT_PATTERN.test(val) : val.length > 0;
      });
    const btn = page.querySelector('#metadata-start');
    if (btn) btn.disabled = !allValid;
  }
}
