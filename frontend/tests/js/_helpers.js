/**
 * Shared stand-ins for the browser globals the frontend reaches for.
 *
 * Only what the code under test actually uses, and only where a stub can be
 * faithful. Anything the browser does that a stub would have to reinvent is
 * deliberately made to fail loudly rather than be approximated.
 */

/**
 * Install a `document` just able to serve escapeHtml (createElement, then
 * textContent in and innerHTML out).
 *
 * The escaping itself is the browser's serialization, not something this
 * stub reimplements - a hand-written version would only ever prove itself
 * right. So the stub is the identity, and it throws on anything that would
 * need escaping, which keeps a test from quietly depending on behaviour that
 * is not being exercised here. Escaping stays verified in a real browser.
 *
 * @returns {Function} restores the previous global.
 */
export function stubDocument() {
  const previous = globalThis.document;
  globalThis.document = {
    createElement: () => ({
      textContent: '',
      get innerHTML() {
        // Serializing a text node rewrites exactly these: the markup
        // characters and the no-break space. Quotes are left alone, since
        // they only matter inside an attribute value.
        if (/[<>&\u00a0]/.test(this.textContent)) {
          throw new Error(
            'this input needs escaping, which the stub does not do - test it in a browser'
          );
        }
        return this.textContent;
      },
    }),
  };
  return () => {
    globalThis.document = previous;
  };
}
