/**
 * The spoken language is PINNED per session (bd polyglot-pdf-87a9).
 *
 * POLICY (maintainer, 2026-08-04): mid-conversation spoken-language switching is
 * NOT supported. The language is chosen once before the form starts, pinned into
 * the per-connect Gemini config + system instruction, and held for every turn of
 * that session. The only way to change it is a NEW session: "clear form", then
 * pick again in the language modal. See docs/standards/voice-and-vad.md.
 *
 * WHY THIS FILE EXISTS. The policy was already true in the product but written
 * down nowhere, and two dead code paths (`handleLanguageChange` in both overlays,
 * `connectionManager.changeSpokenLanguage`) made it look like switching was
 * supported. That misled a whole PR and four independent reviewers -- nobody
 * questioned the premise, because the code plainly showed a language-change path.
 * Documentation alone had already failed once, so the invariant is pinned here:
 * a re-added switcher fails a test rather than passing silently.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { WebFormConnection } from '../webFormConnection'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'

const SCHEMA = {
  form_id: 'test_form',
  title: 'Test Form',
  fields: [
    {
      id: 'p1_sex',
      name: 'Sex',
      spoken_name: 'sex',
      type: 'radio',
      section_id: 'section-1',
      options: [
        { value: 'male', label: 'Male' },
        { value: 'female', label: 'Female' },
      ],
    },
  ],
  sections: [
    { id: 'section-1', label: 'Section 1', order: 1, fields: ['p1_sex'] },
  ],
} as unknown as FormSchema

/** Every production (non-test) .ts/.tsx file under frontend/src. */
function productionSources(): string[] {
  const root = join(process.cwd(), 'src')
  const files: string[] = []
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        if (entry.name !== 'node_modules') walk(full)
        continue
      }
      if (!/\.tsx?$/.test(entry.name)) continue
      if (/\.test\.tsx?$/.test(entry.name)) continue // tests may narrate history
      files.push(full)
    }
  }
  walk(root)
  return files
}

/**
 * Source with comments stripped, so the deliberate tombstone comments are not
 * false hits and a real declaration cannot hide behind a leading '*'.
 */
function codeOnly(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
}

describe('pinned-language policy (bd polyglot-pdf-87a9)', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('the only change_spoken_language sender carries the PINNED language', () => {
    // The message survives for the reconnect opener, which RE-ASSERTS the
    // session's language on a fresh Gemini session after a socket teardown. It
    // must never carry anything other than what is already persisted -- that is
    // what makes it a re-assertion rather than a switch.
    const conn = new WebFormConnection(SCHEMA)
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Ukrainian'
    )
    ;(conn as any).state = started
    SchemaFormStateManager.save(started)

    const sent: any[] = []
    ;(conn as any).send = (m: any) => sent.push(m)
    ;(conn as any).handleSessionReady({ session_id: 's1' })

    const opener = sent.find(m => m?.type === 'change_spoken_language')
    expect(opener, 'reconnect opener did not fire').toBeDefined()
    // Byte-identical to the persisted pinned value -- not merely truthy.
    expect(opener.spoken_language).toBe(
      SchemaFormStateManager.load()!.selectedLanguage
    )
    expect(opener.spoken_language).toBe('Ukrainian')
  })

  it('every change_spoken_language send carries the pinned state value', () => {
    // THE DURABLE INVARIANT, and why this is not a name-based ban: a reviewer
    // showed that a switcher RENAMED to anything else slips past a scan for
    // `changeSpokenLanguage` / `handleLanguageChange`. What matters is not the
    // function's name -- it is that no send of this message may carry a
    // caller-supplied language. So scan the SEND SITES: each one's
    // `spoken_language` must be the pinned session value read from state.
    //
    // A source scan rather than a behavior test on purpose: the removed
    // switchers were dead for months and passed every behavior test that
    // existed. Dead code is exactly what a behavior test cannot see.
    const files = productionSources()
    // Guard against a vacuous pass if the walk ever finds nothing.
    expect(files.length).toBeGreaterThan(20)

    const offenders: string[] = []
    let sendSites = 0

    for (const file of files) {
      const code = codeOnly(readFileSync(file, 'utf8'))
      const marker = /type:\s*['"]change_spoken_language['"]/g
      let m: RegExpExecArray | null
      while ((m = marker.exec(code)) !== null) {
        sendSites += 1
        // The object literal continues for a few lines; the language must come
        // from state, not from a parameter or a literal.
        const slice = code.slice(m.index, m.index + 400)
        const lang = /spoken_language:\s*([^,\r\n]+)/.exec(slice)
        const expr = lang && lang[1] ? lang[1].trim() : '<missing>'
        if (!/state\.selectedLanguage/.test(expr)) {
          const name = file.split(/[\\/]/).pop()
          offenders.push(`${name}: spoken_language: ${expr}`)
        }
      }
    }

    // The reconnect opener is the one sanctioned sender; if it disappears this
    // test must not silently become a no-op.
    expect(sendSites, 'the reconnect opener send site vanished').toBeGreaterThan(0)
    expect(
      offenders,
      'a change_spoken_language send carries a language that is not the pinned ' +
        'session value -- the spoken language is PINNED per session ' +
        '(bd polyglot-pdf-87a9, docs/standards/voice-and-vad.md)'
    ).toEqual([])
  })

  it('no production source declares the removed switching helpers', () => {
    // Belt to the invariant's braces: the two historical names stay banned, so a
    // verbatim restore of the deleted code is caught at its declaration, before
    // it ever grows a send site.
    const BANNED = /\bchangeSpokenLanguage\b|\bhandleLanguageChange\b/
    const offenders: string[] = []

    for (const file of productionSources()) {
      const lines = codeOnly(readFileSync(file, 'utf8')).split(/\r?\n/)
      for (const line of lines) {
        if (BANNED.test(line)) {
          const name = file.split(/[\\/]/).pop()
          offenders.push(`${name}: ${line.trim().slice(0, 80)}`)
        }
      }
    }

    expect(
      offenders,
      'a removed language-switching helper was re-added -- the spoken language ' +
        'is PINNED per session (bd polyglot-pdf-87a9)'
    ).toEqual([])
  })
})
