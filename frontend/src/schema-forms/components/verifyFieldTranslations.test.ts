/**
 * Coverage tests for VERIFY_FIELD_TRANSLATIONS (bd polyglot-pdf-96um6).
 *
 * The verify modal is the KEYBOARD-ONLY way to make the audit claim this product
 * rests on, so shipping it untranslated is a regression for the non-English user,
 * not a follow-up. These mirror the sibling suites
 * (connectionTimeoutTranslations.test.ts, overlayTranslations.test.tsx) rather
 * than inventing a fourth shape.
 *
 * All three guards are DERIVED, never hand-listed (CLAUDE.md scar #8 -- pin the
 * SET, not the instance):
 *   1. the language set equals SPOKEN_LANGUAGES, which is where a language
 *      actually gets added;
 *   2. every language carries exactly the English key set, non-empty;
 *   3. no value is left as bare English, which is how a Tagalog label once
 *      shipped untranslated while its neighbour was fine. Presence is not
 *      translation.
 */

import { describe, it, expect } from 'vitest';
import { VERIFY_FIELD_TRANSLATIONS, getVerifyFieldCopy } from './verifyFieldTranslations';
import { SPOKEN_LANGUAGES } from '../../shared/languages';

describe('VERIFY_FIELD_TRANSLATIONS coverage (bd polyglot-pdf-96um6)', () => {
  it('covers exactly the SPOKEN_LANGUAGES names', () => {
    // Derived from the constant, never a hardcoded count: the list is growing
    // toward ~90, and a language added upstream but missed here would silently
    // render this modal in English for that user.
    expect(Object.keys(VERIFY_FIELD_TRANSLATIONS).sort()).toEqual(
      SPOKEN_LANGUAGES.map(l => l.name).sort()
    );
  });

  it('every language carries the full English key set, all non-empty', () => {
    const englishKeys = Object.keys(VERIFY_FIELD_TRANSLATIONS['English']).sort();
    for (const [lang, strings] of Object.entries(VERIFY_FIELD_TRANSLATIONS)) {
      expect(Object.keys(strings).sort(), `keys for ${lang}`).toEqual(englishKeys);
      for (const [key, value] of Object.entries(strings)) {
        expect(typeof value, `${lang}.${key} type`).toBe('string');
        expect(value.trim(), `${lang}.${key} is blank`).not.toBe('');
      }
    }
  });

  it('no value is left as untranslated English (allowlisted exceptions aside)', () => {
    // An ALLOWLIST of pairs that legitimately match English, not a ban on
    // particular words: a blacklist is one synonym from defeat, and a blanket
    // "must differ" rule would be wrong for real loanwords. Adding an identical
    // value forces a deliberate entry here, and the entry is where you say WHY.
    const english = VERIFY_FIELD_TRANSLATIONS['English'] as unknown as Record<string, string>;
    const SAME_AS_ENGLISH_BY_DESIGN: Record<string, string> = {
      // (none today -- every language differs from English on every key)
    };

    const unexpected: string[] = [];
    for (const [lang, strings] of Object.entries(VERIFY_FIELD_TRANSLATIONS)) {
      if (lang === 'English') continue;
      for (const [key, value] of Object.entries(strings as unknown as Record<string, string>)) {
        const id = `${lang}.${key}`;
        if (value === english[key] && !(id in SAME_AS_ENGLISH_BY_DESIGN)) {
          unexpected.push(id);
        }
      }
    }
    expect(
      unexpected,
      'these are byte-identical to the English string -- translate them, or add an ' +
        'entry to SAME_AS_ENGLISH_BY_DESIGN saying why they legitimately match'
    ).toEqual([]);

    // The allowlist must not rot: every entry has to still describe a real match.
    for (const id of Object.keys(SAME_AS_ENGLISH_BY_DESIGN)) {
      const [lang, key] = id.split('.');
      const strings = VERIFY_FIELD_TRANSLATIONS[lang] as unknown as Record<string, string>;
      expect(strings?.[key], `${id} is allowlisted but no longer matches English`).toBe(
        english[key]
      );
    }
  });

  it('falls back to English for an unknown language', () => {
    // The modal renders in the language chosen at form start; an unrecognised
    // value must not blank the copy.
    expect(getVerifyFieldCopy('Klingon')).toBe(VERIFY_FIELD_TRANSLATIONS['English']);
    expect(getVerifyFieldCopy('German')).toBe(VERIFY_FIELD_TRANSLATIONS['German']);
  });

  it('the checkbox label states WHAT is being asserted, not just assent', () => {
    // This is the sentence the audit record rests on. "OK" would not be a claim
    // that the answer was checked, which is the whole point of the gesture --
    // so the English copy must say more than a bare acknowledgement.
    const label = VERIFY_FIELD_TRANSLATIONS['English'].checkboxLabel;
    expect(label.length, 'the assertion must be a sentence, not a token').toBeGreaterThan(20);
    expect(label.toLowerCase()).toContain('correct');
  });
});
