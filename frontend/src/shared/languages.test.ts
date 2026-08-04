// Enforcement test (bd polyglot-pdf-ow1e): supported spoken languages must be
// code-backed. Quechua -- the one SPOKEN_LANGUAGES entry with no BCP-47 code --
// was removed (maintainer decision, 2026-07-16); this list now mirrors the
// backend's SPOKEN_LANGUAGE_BCP47 map (backend/utils/language_codes.py) exactly,
// enforced there by test_map_covers_all_spoken_languages. Adding a language
// here without updating the backend map (and vice versa) must fail a test.
import { describe, it, expect } from 'vitest'
import {
	SPOKEN_LANGUAGES,
	SPOKEN_LANGUAGE_BCP47,
	kitTranslationKeys,
} from './languages'

// Mirror of backend SPOKEN_LANGUAGE_BCP47 keys (title-cased), in modal order.
const CODE_BACKED_LANGUAGES = [
	'English', 'Spanish', 'Chinese', 'Tagalog', 'Arabic', 'French',
	'Korean', 'German', 'Portuguese', 'Hindi', 'Italian', 'Urdu',
	'Persian', 'Dutch', 'Ukrainian', 'Russian', 'Swedish', 'Afrikaans',
]

describe('SPOKEN_LANGUAGES (bd polyglot-pdf-ow1e: supported == code-backed)', () => {
	it('contains exactly the 18 code-backed languages, no Quechua', () => {
		const names = SPOKEN_LANGUAGES.map((l) => l.name)
		expect(names).toEqual(CODE_BACKED_LANGUAGES)
		expect(names).not.toContain('Quechua')
		expect(names).toHaveLength(18)
	})
})

// bd polyglot-pdf-thun: SPOKEN_LANGUAGE_BCP47 is a hand-copied mirror of
// backend/utils/language_codes.py, read by kitTranslationKeys so the frontend
// hint resolves the same label_translations keys the backend does. Drift is the
// two-languages-on-one-turn bug that bead exists to prevent, so the map needs
// its own guard -- its docstring claimed one existed here before this suite
// actually asserted anything about it (Opus outer review, bd 575i PR).
describe('SPOKEN_LANGUAGE_BCP47 (mirror of backend/utils/language_codes.py)', () => {
	// Verbatim from the backend map. Update BOTH sides together.
	const BACKEND_MAP: Record<string, string> = {
		english: 'en-US', spanish: 'es-US', chinese: 'cmn-CN', tagalog: 'fil-PH',
		arabic: 'ar-XA', french: 'fr-FR', korean: 'ko-KR', german: 'de-DE',
		portuguese: 'pt-BR', hindi: 'hi-IN', italian: 'it-IT', urdu: 'ur-PK',
		persian: 'fa-IR', dutch: 'nl-NL', ukrainian: 'uk-UA', russian: 'ru-RU',
		swedish: 'sv-SE', afrikaans: 'af-ZA',
	}

	it('matches the backend map key-for-key and value-for-value', () => {
		expect(SPOKEN_LANGUAGE_BCP47).toEqual(BACKEND_MAP)
	})

	it('covers every SPOKEN_LANGUAGES entry (supported == code-backed)', () => {
		for (const { name } of SPOKEN_LANGUAGES) {
			expect(SPOKEN_LANGUAGE_BCP47[name.toLowerCase()]).toBeTruthy()
		}
		expect(Object.keys(SPOKEN_LANGUAGE_BCP47)).toHaveLength(SPOKEN_LANGUAGES.length)
	})
})

describe('kitTranslationKeys (mirrors backend _kit_translation_keys)', () => {
	it('returns the lowercase name, the BCP-47 code, and its stem', () => {
		expect(kitTranslationKeys('Spanish')).toEqual(['spanish', 'es-us', 'es'])
		expect(kitTranslationKeys('  UKRAINIAN  ')).toEqual(['ukrainian', 'uk-ua', 'uk'])
	})

	it('emits the stem even when it differs from the ISO-639-1 code', () => {
		// Backend parity: the accepted short forms are the BCP-47 STEMS, so a
		// kit keyed 'zh'/'tl' resolves on NEITHER side -- consistent, which is
		// the property that matters.
		expect(kitTranslationKeys('Chinese')).toEqual(['chinese', 'cmn-cn', 'cmn'])
		expect(kitTranslationKeys('Tagalog')).toEqual(['tagalog', 'fil-ph', 'fil'])
	})

	it('returns just the name for a language with no code, and [] for blank', () => {
		expect(kitTranslationKeys('Klingon')).toEqual(['klingon'])
		expect(kitTranslationKeys('   ')).toEqual([])
	})

	it('produces a candidate list for every supported language', () => {
		for (const { name } of SPOKEN_LANGUAGES) {
			expect(kitTranslationKeys(name)).toHaveLength(3)
		}
	})
})
