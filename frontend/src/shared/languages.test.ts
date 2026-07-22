// Enforcement test (bd polyglot-pdf-ow1e): supported spoken languages must be
// code-backed. Quechua -- the one SPOKEN_LANGUAGES entry with no BCP-47 code --
// was removed (maintainer decision, 2026-07-16); this list now mirrors the
// backend's SPOKEN_LANGUAGE_BCP47 map (backend/utils/language_codes.py) exactly,
// enforced there by test_map_covers_all_spoken_languages. Adding a language
// here without updating the backend map (and vice versa) must fail a test.
import { describe, it, expect } from 'vitest'
import { SPOKEN_LANGUAGES } from './languages'

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
