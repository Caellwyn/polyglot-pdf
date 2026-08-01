/**
 * Coverage/coupling tests for CONNECTION_TIMEOUT_TRANSLATIONS (bd
 * polyglot-pdf-vqy3).
 *
 * This map was the only one of the three per-component translation maps with no
 * automated completeness enforcement -- its siblings both have one
 * (overlayTranslations.test.tsx, DisclaimerModal.test.tsx). Without it, a future
 * language addition that misses this map, or a typo'd/empty value in it, would
 * silently fall back to English with nothing red in CI.
 *
 * The language set is anchored to SPOKEN_LANGUAGES because that is where a new
 * language actually gets added; the sibling map is checked too, so the three
 * stay in lockstep.
 */

import { describe, it, expect } from 'vitest';
import {
  CONNECTION_TIMEOUT_TRANSLATIONS,
  type ConnectionTimeoutCopy,
} from './connectionTimeoutTranslations';
import { SPOKEN_LANGUAGES } from '../../shared/languages';

describe('CONNECTION_TIMEOUT_TRANSLATIONS map', () => {
  it('every language carries every key, non-empty', () => {
    const englishKeys = Object.keys(
      CONNECTION_TIMEOUT_TRANSLATIONS['English']
    ).sort();
    // Guard against the degenerate case of English itself losing keys.
    expect(englishKeys).toEqual([
      'cancelButton',
      'message',
      'reconnectButton',
      'reconnectingMessage',
      'reconnectingTitle',
      'title',
    ]);

    for (const [lang, strings] of Object.entries(
      CONNECTION_TIMEOUT_TRANSLATIONS
    )) {
      expect(Object.keys(strings).sort(), `keys for ${lang}`).toEqual(
        englishKeys
      );
      for (const [key, value] of Object.entries(strings)) {
        expect(value, `${lang}.${key}`).toBeTruthy();
        expect(typeof value, `${lang}.${key} type`).toBe('string');
        expect(value.trim(), `${lang}.${key} is whitespace-only`).not.toBe('');
      }
    }
  });

  it('covers exactly the SPOKEN_LANGUAGES names', () => {
    // A language added to SPOKEN_LANGUAGES but missed here would silently
    // render the timeout modal in English for that user.
    expect(Object.keys(CONNECTION_TIMEOUT_TRANSLATIONS).sort()).toEqual(
      SPOKEN_LANGUAGES.map(l => l.name).sort()
    );
  });

  it('covers the same language names as the overlay map', async () => {
    const { OVERLAY_TRANSLATIONS } = await import(
      '../../demo/overlayTranslations'
    );
    expect(Object.keys(CONNECTION_TIMEOUT_TRANSLATIONS).sort()).toEqual(
      Object.keys(OVERLAY_TRANSLATIONS).sort()
    );
  });

  it('non-English entries are actually translated, not English copies', () => {
    // A copy-paste that leaves the English string in place is the failure this
    // map is most likely to suffer (the non-English strings are a machine draft).
    const english = CONNECTION_TIMEOUT_TRANSLATIONS['English'];
    const untranslated: string[] = [];
    for (const [lang, strings] of Object.entries(
      CONNECTION_TIMEOUT_TRANSLATIONS
    )) {
      if (lang === 'English') continue;
      const copy = strings as ConnectionTimeoutCopy;
      if (copy.title === english.title && copy.message === english.message) {
        untranslated.push(lang);
      }
    }
    expect(untranslated).toEqual([]);
  });

  it("ConnectionTimeoutModal's English fallback resolves for an unknown language", () => {
    // Mirrors the component's lookup (ConnectionTimeoutModal.tsx:53-54).
    const strings =
      CONNECTION_TIMEOUT_TRANSLATIONS['Klingon'] ||
      CONNECTION_TIMEOUT_TRANSLATIONS['English'];
    expect(strings).toBe(CONNECTION_TIMEOUT_TRANSLATIONS['English']);
  });
});
