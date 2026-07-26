import { escapeHtml } from './dom.js';

/**
 * Shared submit flow for every test-type class: disable the Submit button,
 * detach the keyboard shortcuts, send the payload, and - if the server
 * rejects the submission - restore the button/shortcuts and show the error
 * inline so the listener can retry without losing their responses.
 *
 * @param {Object} test - Test instance (uses _pageSlot, _boundKeydown, onSubmit, sessionId, config).
 * @param {Function} buildPayload - Returns the type-specific {ratings}/{choices} payload.
 */
export async function submitPayload(test, buildPayload) {
  // Practice ratings are discarded: skip the network (and the "Submitting…"
  // state) entirely and hand control straight back to the practice runner.
  if (test.config.isPractice) {
    document.removeEventListener('keydown', test._boundKeydown);
    await test.onSubmit();
    return;
  }

  const btn = test._pageSlot.querySelector('#btn-next');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Submitting\u2026';
  }
  document.removeEventListener('keydown', test._boundKeydown);

  try {
    await test.onSubmit(test.sessionId, test.config.test_type, buildPayload());
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Submit';
    }
    document.addEventListener('keydown', test._boundKeydown);
    test._pageSlot.insertAdjacentHTML(
      'beforeend',
      `<p style="color:var(--color-error);margin-top:12px;text-align:center">
        Error: ${escapeHtml(err.message)}
      </p>`
    );
  }
}
