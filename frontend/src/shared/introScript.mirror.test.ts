/**
 * The frontend script copy MUST stay byte-identical to the backend's
 * (bd polyglot-pdf-s1iex.5).
 *
 * Sprint 20's hard invariant is that the modal renders exactly what the
 * backend synthesizes. The Vite bundle cannot cleanly import out of
 * `backend/`, so `frontend/src/shared/introScript.json` is a MIRROR of
 * `backend/services/intro_script.json` -- and a mirror without a pin is drift
 * waiting to happen, in 18 languages nobody proofreads. This test is that pin:
 * it compares the two files BYTE FOR BYTE, so a translation fixed on one side
 * only fails CI instead of shipping a modal that disagrees with its own audio.
 *
 * Same idiom as MAX_SPELLBACK_CHARS <-> SPELLBACK_MAX_CHARS and the
 * agree-label table's parse-both-sides test.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'
import {
  introParagraphs,
  introScriptLanguages,
  renderIntroParagraphs,
  resolveIntroLanguage,
  FORM_PLACEHOLDER,
  AGREE_PLACEHOLDER,
} from './introScript'

// Resolve from THIS TEST FILE, never process.cwd(): a worktree vitest run is
// invoked from the MAIN checkout here (the node_modules junction workaround),
// so a cwd-relative read would audit the wrong copy entirely (measured on bd
// s1iex.4 -- it read 3 sites where the branch had 4).
function repoPath(...parts: string[]): string {
  const here = expect.getState().testPath as string
  // <repo>/frontend/src/shared/<file> -> up 4 to <repo>
  return resolve(here, '../../../..', ...parts)
}

describe('intro script frontend mirror (bd s1iex.5)', () => {
  it('is byte-identical to the backend store', () => {
    const backend = readFileSync(
      repoPath('backend', 'services', 'intro_script.json'), 'utf-8')
    const frontend = readFileSync(
      repoPath('frontend', 'src', 'shared', 'introScript.json'), 'utf-8')
    expect(frontend).toBe(backend)
  })

  it('carries every language the backend does', () => {
    const backend = JSON.parse(readFileSync(
      repoPath('backend', 'services', 'intro_script.json'), 'utf-8'))
    expect(new Set(introScriptLanguages()))
      .toEqual(new Set(Object.keys(backend.languages)))
  })
})

describe('intro script rendering (bd s1iex.5)', () => {
  it('resolves a wire language case-insensitively, English as fallback', () => {
    expect(resolveIntroLanguage('spanish')).toBe('Spanish')
    expect(resolveIntroLanguage('Spanish')).toBe('Spanish')
    // An unknown/absent language must still render SOMETHING readable -- the
    // same fallback the backend applies, so text and audio agree even then.
    expect(resolveIntroLanguage('Klingon')).toBe('English')
    expect(resolveIntroLanguage(undefined)).toBe('English')
  })

  it('interpolates both placeholders, leaving none behind', () => {
    const rendered = renderIntroParagraphs('English', 'I-90', 'I Agree')
    const joined = rendered.join(' ')
    expect(joined).not.toContain(FORM_PLACEHOLDER)
    expect(joined).not.toContain(AGREE_PLACEHOLDER)
    expect(joined).toContain('Form I-90')
    expect(joined).toContain('I Agree')
  })

  it('does not double the "Form " prefix when given a full name', () => {
    const joined = renderIntroParagraphs('English', 'Form I-90', 'I Agree').join(' ')
    expect(joined).toContain('Form I-90')
    expect(joined).not.toContain('Form Form')
  })

  it('renders the agree label in the language the user actually sees', () => {
    // bd s863's requirement, now satisfied by construction: the label the clip
    // speaks and the button the user reads come from one table.
    const joined = renderIntroParagraphs('Spanish', 'I-90', 'Estoy de Acuerdo').join(' ')
    expect(joined).toContain('Estoy de Acuerdo')
  })

  it('keeps every language structurally renderable', () => {
    // Derived from the store, not a hand-list: a language added without
    // paragraphs fails here rather than rendering an empty modal.
    for (const language of introScriptLanguages()) {
      const paragraphs = introParagraphs(language)
      expect(paragraphs.length).toBeGreaterThan(0)
      expect(paragraphs.every(p => typeof p === 'string' && p.trim().length > 0))
        .toBe(true)
    }
  })
})
