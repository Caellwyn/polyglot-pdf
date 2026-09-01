// @vitest-environment jsdom
//
// The save/resume strings (bd polyglot-pdf-dft1).
//
// The failure this prevents is silent: a missing key renders as `undefined` or
// blank to a client who cannot read English, on the one screen that tells them
// how not to lose their work. Derived from the shipped maps, so adding a
// language with a hole fails here rather than in front of a client.
import { describe, it, expect } from 'vitest';

import { RESUME_TRANSLATIONS, resumeStrings } from './resumeStrings';
import { DISCLAIMER_TRANSLATIONS } from './components/DisclaimerModal';

const KEYS = Object.keys(RESUME_TRANSLATIONS.English);

describe('resume strings', () => {
  it('covers every language the disclaimer already covers', () => {
    // The disclaimer is the app's existing client-facing translation set. A
    // client who reads the disclaimer in their language must not hit English
    // when told how to save their work.
    const disclaimerLangs = Object.keys(DISCLAIMER_TRANSLATIONS).sort();
    const resumeLangs = Object.keys(RESUME_TRANSLATIONS).sort();
    expect(resumeLangs).toEqual(disclaimerLangs);
  });

  it.each(Object.keys(RESUME_TRANSLATIONS))(
    '%s has every key, non-empty',
    (language) => {
      const strings = RESUME_TRANSLATIONS[language] as unknown as Record<string, string>;
      for (const key of KEYS) {
        expect(typeof strings[key], `${language}.${key}`).toBe('string');
        expect(strings[key].trim().length, `${language}.${key} is empty`).toBeGreaterThan(0);
      }
    },
  );

  it.each(Object.keys(RESUME_TRANSLATIONS).filter((l) => l !== 'English'))(
    '%s is actually TRANSLATED, not copied English',
    (language) => {
      // A copy-paste that leaves English text under another language name
      // looks translated in review and reads as broken to the client.
      const strings = RESUME_TRANSLATIONS[language] as unknown as Record<string, string>;
      const english = RESUME_TRANSLATIONS.English as unknown as Record<string, string>;
      const identical = KEYS.filter((k) => strings[k] === english[k]);
      expect(identical, `${language} has untranslated keys`).toEqual([]);
    },
  );

  it('falls back to English for an unknown or absent language', () => {
    // 18 languages today, growing toward ~90. An unsupported language must
    // degrade to readable English, never to blank text.
    expect(resumeStrings('Klingon')).toBe(RESUME_TRANSLATIONS.English);
    expect(resumeStrings(undefined)).toBe(RESUME_TRANSLATIONS.English);
    expect(resumeStrings('')).toBe(RESUME_TRANSLATIONS.English);
  });

  it('resolves a supported language to its own strings', () => {
    expect(resumeStrings('Spanish')).toBe(RESUME_TRANSLATIONS.Spanish);
  });

  it('never promises that saving happens on our servers', () => {
    // The privacy claim is load-bearing: the client's file stays on their
    // device. Text implying server storage would be false.
    for (const [language, strings] of Object.entries(RESUME_TRANSLATIONS)) {
      const body = (strings as unknown as Record<string, string>).saveNudgeBody;
      expect(body.length, `${language} save nudge is too terse to explain`).toBeGreaterThan(40);
    }
  });
});
