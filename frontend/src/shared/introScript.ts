/**
 * The canonical intro+disclaimer script, frontend side (bd polyglot-pdf-s1iex.5).
 *
 * THE HARD INVARIANT of sprint 20: the modal renders EXACTLY the text the
 * backend synthesizes. Before this, the modal painted `p1/p2/p3` while a
 * separate `fullText` was spoken, with nothing keeping them in sync -- in 18
 * languages nobody would have caught the drift. Now both sides read one
 * `paragraphs[]` per language: the modal renders the array, and the TTS input
 * is those same paragraphs joined by the backend.
 *
 * WHY A MIRRORED COPY rather than one shared file: the Vite bundle cannot
 * cleanly import out of `backend/`, so `introScript.json` here is a
 * byte-identical copy of `backend/services/intro_script.json`, pinned by
 * `introScript.mirror.test.ts` (the same mirror idiom as MAX_SPELLBACK_CHARS
 * and the agree-label table). A drift between them fails CI rather than
 * shipping a modal that disagrees with its own audio.
 *
 * Placeholders (`[FORM NUMBER]`, `[AGREE LABEL]`) are interpolated HERE for
 * display from the same tables the backend uses for speech -- see
 * `renderIntroParagraphs`.
 */

import scriptData from './introScript.json'

export const FORM_PLACEHOLDER = '[FORM NUMBER]'
export const AGREE_PLACEHOLDER = '[AGREE LABEL]'
const FALLBACK_LANGUAGE = 'English'

interface IntroScriptFile {
  languages: Record<string, { paragraphs: string[] }>
}

const LANGUAGES = (scriptData as unknown as IntroScriptFile).languages

/** Every language the script store carries. */
export function introScriptLanguages(): string[] {
  return Object.keys(LANGUAGES)
}

/**
 * The store's display-cased key for a wire language name, case-insensitively.
 * Unknown/empty falls back to English -- mirroring the backend's
 * `resolve_intro_language`, so a client one deploy behind still gets a
 * working clip and matching text rather than an error.
 */
export function resolveIntroLanguage(language: string | undefined): string {
  if (language) {
    const wanted = language.trim().toLowerCase()
    for (const name of Object.keys(LANGUAGES)) {
      if (name.toLowerCase() === wanted) return name
    }
  }
  return FALLBACK_LANGUAGE
}

/** The raw (un-interpolated) paragraphs for a language. */
export function introParagraphs(language: string | undefined): string[] {
  return LANGUAGES[resolveIntroLanguage(language)].paragraphs
}

/**
 * The paragraphs as the user should SEE them: placeholders replaced with the
 * same values the backend speaks. `formNumber` is the bounded key ("I-90");
 * the spoken/displayed name is "Form I-90" in every language by design (the
 * maintainer's keyed-route decision), so it is not translated here.
 *
 * The modal `<h2>` title is a HEADING, not script -- it is deliberately NOT
 * part of this array and is never spoken.
 */
export function renderIntroParagraphs(
  language: string | undefined,
  formNumber: string,
  agreeLabel: string,
): string[] {
  // A kit MAY legitimately have no form number: schema_lint makes it a
  // WARNING, not a publish gate, so firm-proprietary intake sheets can ship.
  // Before bd polyglot-pdf-nsb4y the degraded "Form  " (double space) was
  // unreachable -- the text was flag-gated and the clip early-returns on an
  // empty form number. The modal now renders this UNCONDITIONALLY, so an
  // empty value would be both shown and READ ALOUD. Fall back to a generic
  // noun phrase rather than a dangling "Form".
  //
  // NO ENGLISH FALLBACK. The placeholder sits mid-sentence inside each
  // language's own grammar ("...fill out your [FORM NUMBER] today", "...llenar
  // su [FORM NUMBER]"), so substituting an English noun phrase would read
  // wrong in 17 languages -- the same trap avoided in bd s1iex.5, which kept
  // English state strings out of this 18-language modal. Instead emit the
  // untranslated form WORD only when we have a number, and collapse to
  // nothing when we do not: every language's sentence stays grammatical
  // around an empty slot, just less specific.
  const trimmed = formNumber.trim()
  const formName = !trimmed
    ? ''
    : trimmed.startsWith('Form ') ? trimmed : `Form ${trimmed}`
  return introParagraphs(language).map((p) => {
    const withForm = formName
      ? p.split(FORM_PLACEHOLDER).join(formName)
      // No form number: swallow one adjacent space with the placeholder so
      // neither a double space nor a space-before-punctuation is created.
      : p.split(' ' + FORM_PLACEHOLDER).join('').split(FORM_PLACEHOLDER).join('')
    return withForm.split(AGREE_PLACEHOLDER).join(agreeLabel)
  })
}
