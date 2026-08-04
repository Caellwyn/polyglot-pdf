/**
 * Spoken languages confirmed to work with Gemini Live API
 *
 * Source: planning_documents/hello_gemini_translations.csv
 * These are the languages verified to work for voice conversation with Gemini
 */
export const SPOKEN_LANGUAGES = [
	{ name: "English", nativeName: "English" },
	{ name: "Spanish", nativeName: "Español" },
	{ name: "Chinese", nativeName: "中文 (Zhōngwén)" },
	{ name: "Tagalog", nativeName: "Tagalog" },
	{ name: "Arabic", nativeName: "العربية (al-ʿArabīyah)" },
	{ name: "French", nativeName: "Français" },
	{ name: "Korean", nativeName: "한국어 (Hangugeo)" },
	{ name: "German", nativeName: "Deutsch" },
	{ name: "Portuguese", nativeName: "Português" },
	{ name: "Hindi", nativeName: "हिन्दी (Hindī)" },
	{ name: "Italian", nativeName: "Italiano" },
	{ name: "Urdu", nativeName: "اردو (Urdū)" },
	{ name: "Persian", nativeName: "فارسی (Fārsī)" },
	{ name: "Dutch", nativeName: "Nederlands" },
	{ name: "Ukrainian", nativeName: "Українська (Ukrayins'ka)" },
	{ name: "Russian", nativeName: "Русский (Russkiy)" },
	{ name: "Swedish", nativeName: "Svenska" },
	{ name: "Afrikaans", nativeName: "Afrikaans" },
] as const;

/**
 * Supported languages for form field filling
 *
 * These are the languages that Gemini can use to fill form field values.
 * The user can converse with Gemini in any language, but form values will
 * be filled in the selected language.
 */

export const SUPPORTED_FILL_LANGUAGES = [
	"Afrikaans",
	"Albanian",
	"Amharic",
	"Arabic",
	"Armenian",
	"Assamese",
	"Azerbaijani",
	"Basque",
	"Belarusian",
	"Bengali",
	"Bosnian",
	"Bulgarian",
	"Catalan",
	"Cebuano",
	"Chinese (Simplified and Traditional)",
	"Corsican",
	"Croatian",
	"Czech",
	"Danish",
	"Dhivehi",
	"Dutch",
	"English",
	"Esperanto",
	"Estonian",
	"Filipino (Tagalog)",
	"Finnish",
	"French",
	"Frisian",
	"Galician",
	"Georgian",
	"German",
	"Greek",
	"Gujarati",
	"Haitian Creole",
	"Hausa",
	"Hawaiian",
	"Hebrew",
	"Hindi",
	"Hmong",
	"Hungarian",
	"Icelandic",
	"Igbo",
	"Indonesian",
	"Irish",
	"Italian",
	"Japanese",
	"Javanese",
	"Kannada",
	"Kazakh",
	"Khmer",
	"Korean",
	"Krio",
	"Kurdish",
	"Kyrgyz",
	"Lao",
	"Latin",
	"Latvian",
	"Lithuanian",
	"Luxembourgish",
	"Macedonian",
	"Malagasy",
	"Malay",
	"Malayalam",
	"Maltese",
	"Maori",
	"Marathi",
	"Meiteilon (Manipuri)",
	"Mongolian",
	"Myanmar (Burmese)",
	"Nepali",
	"Norwegian",
	"Nyanja (Chichewa)",
	"Odia (Oriya)",
	"Pashto",
	"Persian",
	"Polish",
	"Portuguese",
	"Punjabi",
	"Romanian",
	"Russian",
	"Samoan",
	"Scots Gaelic",
	"Serbian",
	"Sesotho",
	"Shona",
	"Sindhi",
	"Sinhala (Sinhalese)",
	"Slovak",
	"Slovenian",
	"Somali",
	"Spanish",
	"Sundanese",
	"Swahili",
	"Swedish",
	"Tajik",
	"Tamil",
	"Telugu",
	"Thai",
	"Turkish",
	"Ukrainian",
	"Urdu",
	"Uyghur",
	"Uzbek",
	"Vietnamese",
	"Welsh",
	"Xhosa",
	"Yiddish",
	"Yoruba",
	"Zulu"
] as const;

export type FillLanguage = typeof SUPPORTED_FILL_LANGUAGES[number];

/**
 * Spoken-language NAME (lowercase) -> BCP-47 code.
 *
 * MIRRORS backend/utils/language_codes.py SPOKEN_LANGUAGE_BCP47 -- keep the two
 * in sync; every entry in SPOKEN_LANGUAGES above must appear here.
 *
 * The sync is pinned from BOTH ends, and it has to be: each suite compares its
 * own map against a literal in its own file, so one side alone cannot see a
 * drift introduced on the other. languages.test.ts guards edits made HERE;
 * backend test_transcription_language_bias.py::test_map_values_match_the_frontend_mirror
 * guards edits made THERE (the likelier direction -- that file is the ASR
 * biasing map and gets edited for ASR reasons). Change a code and you must
 * update both literals.
 *
 * Regional variants match the backend's choices for this app's user base (US
 * immigration intake): es-US over es-ES, pt-BR over pt-PT.
 *
 * Used to read hand-authored kits whose option `label_translations` are keyed
 * by CODE rather than by the canonical lowercase name (bd polyglot-pdf-thun).
 * The backend's kit resolver accepts all three forms, so this one must too, or
 * the guidance block and the next-field hint disagree on the same turn.
 */
export const SPOKEN_LANGUAGE_BCP47: Record<string, string> = {
	english: "en-US",
	spanish: "es-US",
	chinese: "cmn-CN",
	tagalog: "fil-PH",
	arabic: "ar-XA",
	french: "fr-FR",
	korean: "ko-KR",
	german: "de-DE",
	portuguese: "pt-BR",
	hindi: "hi-IN",
	italian: "it-IT",
	urdu: "ur-PK",
	persian: "fa-IR",
	dutch: "nl-NL",
	ukrainian: "uk-UA",
	russian: "ru-RU",
	swedish: "sv-SE",
	afrikaans: "af-ZA",
};

/**
 * The `label_translations` keys accepted for a session language, lowercase.
 *
 * Mirrors backend/services/option_translation.py `_kit_translation_keys`: the
 * CANONICAL key is the lowercase spoken-language NAME ("spanish") -- what the
 * authoring bake writes -- while a hand-authored kit may use the full BCP-47
 * code ("es-US") or its stem ("es"). Bare ISO-639-1 codes that differ from the
 * BCP-47 stem ("zh", "tl") do NOT resolve on either side; the accepted short
 * forms are the stems ("cmn", "fil").
 *
 * @param languageName - session language name, already lowercased/trimmed
 */
export function kitTranslationKeys(languageName: string): string[] {
	const name = languageName.trim().toLowerCase();
	if (!name) return [];
	const keys = [name];
	const full = SPOKEN_LANGUAGE_BCP47[name]?.toLowerCase();
	if (full) {
		keys.push(full);
		const stem = full.split("-")[0];
		if (stem !== full) keys.push(stem);
	}
	return keys;
}
