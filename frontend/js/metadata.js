/**
 * MetadataPage - pre-test listener information form.
 *
 * Renders a form from a field definition array (from config.metadata).
 * Returns a Promise that resolves with {key: value, ...} when the listener
 * clicks "Start Test".
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
   */
  constructor(fields) {
    this.fields = fields;
    this._values = {};
    // Pre-select default value (or first option if no default) for select fields.
    for (const f of fields) {
      if (f.type === 'select' && f.options?.length > 0) {
        this._values[f.key] = f.default ?? f.options[0];
      }
      if (f.type === 'text' && f.default) {
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
          <h2 class="metadata-title">Listener Information</h2>
          ${this.fields.map((f) => this._renderField(f)).join('')}
          <button class="btn btn-primary metadata-start" id="metadata-start" type="button" disabled>
            Start Test
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
      const defaultVal = f.default ?? f.options?.[0];
      const radios = (f.options ?? [])
        .map(
          (opt) => `
        <label class="radio-option">
          <input type="radio" name="meta-${escapeHtml(f.key)}"
                 data-key="${escapeHtml(f.key)}" value="${escapeHtml(opt)}"
                 ${opt === defaultVal ? 'checked' : ''}>
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
