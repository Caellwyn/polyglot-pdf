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

  it('no production source declares or calls a language-switching API', () => {
    // `connectionManager.changeSpokenLanguage` was the one API that could swap
    // the language on a live session, and `handleLanguageChange` was the UI that
    // drove it. Both had NO caller and still survived unnoticed -- which is why a
    // behavior test is not enough here: dead code passes every behavior test. So
    // assert on the SOURCE, and a re-add fails even if nothing calls it.
    const BANNED = /\bchangeSpokenLanguage\b|\bhandleLanguageChange\b/
    // vitest runs with cwd at the frontend package root.
    const root = join(process.cwd(), 'src')
    const offenders: string[] = []

    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name)
        if (entry.isDirectory()) {
          if (entry.name !== 'node_modules') walk(full)
          continue
        }
        if (!/\.tsx?$/.test(entry.name)) continue
        // Test files may narrate the history; production source may not.
        if (/\.test\.tsx?$/.test(entry.name)) continue
        const lines = readFileSync(full, 'utf8').split(/\r?\n/)
        for (const line of lines) {
          const code = line.trim()
          // Skip comments -- the tombstones deliberately NAME the removed API.
          if (code.startsWith('//') || code.startsWith('*') || code.startsWith('/*')) continue
          if (BANNED.test(code)) offenders.push(`${entry.name}: ${code.slice(0, 80)}`)
        }
      }
    }
    walk(root)

    expect(
      offenders,
      'a mid-session language-switching API was re-added -- the spoken language ' +
        'is PINNED per session (bd polyglot-pdf-87a9, docs/standards/voice-and-vad.md)'
    ).toEqual([])
  })
})
