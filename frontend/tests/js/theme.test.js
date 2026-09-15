/**
 * Tests for which theme the page shows: the listener's own choice once they
 * make one, the system's until then, and dark when neither says.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { mountTheme, themeFor } from '../../js/theme.js';

// -- themeFor -----------------------------------------------------------------

test("a saved choice wins over the system's preference", () => {
  assert.equal(themeFor('light', false), 'light');
  assert.equal(themeFor('dark', true), 'dark');
});

test("with no choice saved, the system's preference is followed", () => {
  assert.equal(themeFor(null, true), 'light');
  assert.equal(themeFor(null, false), 'dark');
});

test('a saved value that is no theme counts as no choice', () => {
  assert.equal(themeFor('blue', true), 'light');
});

// -- mountTheme ---------------------------------------------------------------

/** The page's parts mountTheme touches, each only as far as it uses them. */
function page({ saved = null, systemLight = false } = {}) {
  const attributes = new Map();
  const root = {
    getAttribute: (name) => attributes.get(name) ?? null,
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: (name) => attributes.delete(name),
  };
  const listeners = {};
  const button = {
    innerHTML: '',
    setAttribute() {},
    addEventListener: (type, fn) => (listeners[type] = fn),
  };
  const store = new Map(saved === null ? [] : [['theme', saved]]);
  const storage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
  };
  const media = {
    matches: systemLight,
    addEventListener: (type, fn) => (listeners[`system-${type}`] = fn),
  };
  return {
    theme: () => (root.getAttribute('data-theme') === 'light' ? 'light' : 'dark'),
    mount: () => mountTheme(root, button, storage, media),
    click: () => listeners.click(),
    systemChangesTo: (light) => {
      media.matches = light;
      listeners['system-change']();
    },
    store,
  };
}

test("the system's change is followed live until the listener chooses", () => {
  const p = page({ systemLight: false });
  p.mount();
  assert.equal(p.theme(), 'dark');
  p.systemChangesTo(true);
  assert.equal(p.theme(), 'light');
});

test('a choice made with the toggle is saved and outlasts a system change', () => {
  const p = page({ systemLight: true });
  p.mount();
  p.click();
  assert.equal(p.theme(), 'dark');
  assert.equal(p.store.get('theme'), 'dark');
  p.systemChangesTo(true);
  assert.equal(p.theme(), 'dark');
});
