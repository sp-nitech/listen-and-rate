/**
 * UI-chrome string lookup: en/ja translations of the fixed buttons,
 * headings, and hints the app itself renders (see strings/en.js,
 * strings/ja.js). Exactly two locales are supported - config.ui_language
 * validates to one of them at load time, so a typo is a config error, not a
 * silent English fallback (see listen_and_rate/config/base.py).
 *
 * Admin-authored config content (title, instructions, metadata/survey field
 * text, tie_label, rating_labels, practice_instructions, ...) never goes
 * through this table - the researcher writes that directly in whichever
 * language they choose, independent of ui_language.
 *
 * The current language is module-level state, set once by app.js's main()
 * right after the config is fetched (before any DOM is touched, since the
 * resume prompt itself needs translated strings) - not threaded as a
 * parameter through every constructor/helper down the call chain, since
 * exactly one language is active per page load, never per-component.
 * theme.js already uses the same kind of module-level singleton for its own
 * one-per-page setting.
 */

import { en } from './strings/en.js';
import { ja } from './strings/ja.js';

export const STRINGS = { en, ja };

let _lang = 'en';

/** Set the current language ('en'/'ja'); anything else falls back to 'en'. */
export function setLanguage(lang) {
  _lang = lang === 'ja' ? 'ja' : 'en';
}

/**
 * The language setLanguage() actually resolved to ('en'/'ja') - for a caller
 * (e.g. app.js's document.documentElement.lang) that wants the resolved
 * value itself, rather than re-deriving the same fallback rule from whatever
 * raw config.ui_language it was given.
 */
export function currentLanguage() {
  return _lang;
}

/**
 * Substitute {name} placeholders in `template` from `vars`.
 *
 * A placeholder with no matching var is left literal rather than throwing -
 * a visibly-wrong string during development beats a broken render. Named
 * (not positional %s) placeholders: ja can need to reorder a sentence's
 * parts relative to en, and named substitution survives that safely.
 */
function interpolate(template, vars) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    Object.hasOwn(vars, name) ? String(vars[name]) : match
  );
}

/**
 * Look up `key` in the current language, with {name} substitution from
 * `vars`. Falls back to English, then to the raw key, as a safety net - the
 * real guarantee that every key exists in both locales is
 * strings.test.js's completeness invariant, not this runtime fallback.
 */
export function t(key, vars) {
  const template = STRINGS[_lang]?.[key] ?? STRINGS.en[key] ?? key;
  return interpolate(template, vars);
}
