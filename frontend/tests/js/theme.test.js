/**
 * Tests for which theme the page shows: the listener's own choice once they
 * make one, the system's until then, and dark when neither says.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { guardedStorage, mountTheme, themeFor } from '../../js/theme.js';

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
function page({ saved = null, systemLight = false, storage: given } = {}) {
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
  const storage = given ?? {
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

// -- guardedStorage -----------------------------------------------------------

/** What reading localStorage does in a browser that refuses to store anything. */
const refused = () => {
  throw new DOMException('Access is denied for this document.', 'SecurityError');
};

test('storage the browser refuses reads as no choice and keeps nothing', () => {
  const storage = guardedStorage(refused);
  assert.equal(storage.getItem('theme'), null);
  assert.doesNotThrow(() => storage.setItem('theme', 'light'));
});

test('storage the browser allows is read and written through', () => {
  const store = new Map();
  const storage = guardedStorage(() => ({
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
  }));
  storage.setItem('theme', 'light');
  assert.equal(storage.getItem('theme'), 'light');
});

test('without storage the theme follows the system and the toggle still works', () => {
  // Only the choice goes unsaved: the page itself, and the test on it, run.
  const p = page({ systemLight: true, storage: guardedStorage(refused) });
  p.mount();
  assert.equal(p.theme(), 'light');
  p.click();
  assert.equal(p.theme(), 'dark');
});
