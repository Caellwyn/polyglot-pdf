/**
 * copy_to fans out at the WRITE CHOKEPOINT, so every path gets it
 * (bd polyglot-pdf-gpaed).
 *
 * The fan-out used to live in exactly ONE caller -- SchemaForm's React
 * manual-edit handler -- so the VOICE path never fanned out: a value Gemini
 * filled left its copy targets blank. Combined with the read_only coupling the
 * editor applies to a copy target (bd polyglot-pdf-g33y2), a REQUIRED target
 * was unreachable: the AI cannot write a read_only field, and isSectionValid
 * does not excuse it, so the section gate could never be satisfied.
 *
 * updateField has EIGHT call sites across SchemaForm, shared/connection.ts and
 * webFormConnection.ts. Putting the fan-out inside it fixes all of them and
 * deletes a single-path special case rather than adding a second one.
 *
 * ASCII only.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { FormSchema } from '../types/schema'

/** The i-90 shape: a Part 1 answer that repeats on page 8. */
function schema(extra: any[] = []): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', version: '1.0.0', language: 'en',
      form_number: 'I-90', edition_date: '01/01/25', page_count: 1,
    },
    fields: [
      {
        id: 'family_name', name: 'family_name', spoken_name: 'family name',
        type: 'text', section_id: 'sec', copy_to: ['p8_family_name'],
      },
      {
        id: 'p8_family_name', name: 'p8_family_name',
        spoken_name: 'family name (page 8)', type: 'text', section_id: 'sec',
        read_only: true,
      },
      { id: 'other', name: 'other', spoken_name: 'other', type: 'text',
        section_id: 'sec' },
      ...extra,
    ],
    sections: [{
      id: 'sec', label: 'Sec', order: 1,
      fields: ['family_name', 'p8_family_name', 'other',
               ...extra.map((f: any) => f.id)],
    }],
  } as unknown as FormSchema
}

function fresh(s: FormSchema) {
  return SchemaFormStateManager.init(s)
}

const valueOf = (state: any, id: string) => state.fieldValues[id]?.value

describe('copy_to fans out from the write chokepoint (bd polyglot-pdf-gpaed)', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    const stub = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    } as unknown as Storage
    global.sessionStorage = stub
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, 'sessionStorage', {
        value: stub, writable: true, configurable: true,
      })
    }
  })

  it('an AI_VOICE fill reaches the copy target -- the bug this closes', () => {
    // The AI ingress (webFormConnection) writes with confirmationMethod
    // 'ai_voice'. Before this fix the target stayed undefined.
    const s = SchemaFormStateManager.updateField(
      fresh(schema()), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(valueOf(s, 'p8_family_name')).toBe('GARCIA')
  })

  it('a MANUAL edit still reaches it (the path that already worked)', () => {
    const s = SchemaFormStateManager.updateField(
      fresh(schema()), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'manual_edit' })
    expect(valueOf(s, 'p8_family_name')).toBe('GARCIA')
  })

  it('the target is stamped confirmed, so it does not re-ask', () => {
    const s = SchemaFormStateManager.updateField(
      fresh(schema()), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(s.fieldValues['p8_family_name'].confirmed).toBe(true)
  })

  it('fans out to SEVERAL targets', () => {
    const many = schema([
      { id: 'p9_family_name', name: 'p9_family_name', spoken_name: 'p9',
        type: 'text', section_id: 'sec' },
    ])
    ;(many.fields[0] as any).copy_to = ['p8_family_name', 'p9_family_name']
    const s = SchemaFormStateManager.updateField(
      fresh(many), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(valueOf(s, 'p8_family_name')).toBe('GARCIA')
    expect(valueOf(s, 'p9_family_name')).toBe('GARCIA')
  })

  it('leaves unrelated fields alone', () => {
    const s = SchemaFormStateManager.updateField(
      fresh(schema()), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(valueOf(s, 'other')).toBeUndefined()
  })

  it('a later edit of the source OVERWRITES the target', () => {
    let s = SchemaFormStateManager.updateField(
      fresh(schema()), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    s = SchemaFormStateManager.updateField(s, 'family_name', 'LOPEZ',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(valueOf(s, 'p8_family_name')).toBe('LOPEZ')
  })

  it('writing the TARGET directly does not write back to the source', () => {
    const s = SchemaFormStateManager.updateField(
      fresh(schema()), 'p8_family_name', 'TYPED',
      { confirmed: true, confirmationMethod: 'manual_edit' })
    expect(valueOf(s, 'p8_family_name')).toBe('TYPED')
    expect(valueOf(s, 'family_name')).toBeUndefined()
  })

  it('does NOT chain: a target with its own copy_to is not followed', () => {
    // Matches what the old single-caller version did -- this changes WHICH
    // paths fan out, not how far.
    const chained = schema([
      { id: 'c', name: 'c', spoken_name: 'c', type: 'text', section_id: 'sec' },
    ])
    ;(chained.fields[1] as any).copy_to = ['c']   // p8_family_name -> c
    const s = SchemaFormStateManager.updateField(
      fresh(chained), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(valueOf(s, 'p8_family_name')).toBe('GARCIA')
    expect(valueOf(s, 'c')).toBeUndefined()
  })

  it('tolerates a self-referential copy_to without looping', () => {
    const selfish = schema()
    ;(selfish.fields[0] as any).copy_to = ['family_name', 'p8_family_name']
    const s = SchemaFormStateManager.updateField(
      fresh(selfish), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(valueOf(s, 'family_name')).toBe('GARCIA')
    expect(valueOf(s, 'p8_family_name')).toBe('GARCIA')
  })

  it.each([
    ['absent', undefined],
    ['not an array', 'p8_family_name'],
    ['carrying non-strings', [null, 42]],
    ['naming a field that does not exist', ['ghost']],
  ])('degrades on a malformed copy_to: %s', (_label, raw) => {
    const bad = schema()
    ;(bad.fields[0] as any).copy_to = raw
    expect(() => SchemaFormStateManager.updateField(
      fresh(bad), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })).not.toThrow()
  })

  it('is idempotent, so the legacy SchemaForm fan-out cannot double-write', () => {
    // SchemaForm still fans out in its own handler. That call now lands on a
    // target this method already wrote -- the same value, so the second write
    // is a no-op in effect. Pinned because leaving that duplicate in place is
    // a deliberate choice (its file is claimed by another in-flight bead).
    let s = SchemaFormStateManager.updateField(
      fresh(schema()), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'manual_edit' })
    const after = SchemaFormStateManager.updateField(s, 'p8_family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'manual_edit' })
    expect(valueOf(after, 'p8_family_name')).toBe('GARCIA')
    expect(valueOf(after, 'family_name')).toBe('GARCIA')
  })
})

describe('the section gate: a REQUIRED copy target is reachable again', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    const stub = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    } as unknown as Storage
    global.sessionStorage = stub
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, 'sessionStorage', {
        value: stub, writable: true, configurable: true,
      })
    }
  })

  /** Source -> REQUIRED, read_only target: the dead-end shape from the title. */
  function gated(): FormSchema {
    const s = schema()
    ;(s.fields[1] as any).validation = { required: true }
    return s
  }

  it('the section is INCOMPLETE before the source is answered', () => {
    // Floor: without this the next assertion could pass vacuously on a section
    // that was already valid.
    expect(SchemaFormStateManager.isSectionValid(fresh(gated()), 'sec')).toBe(false)
  })

  it('an AI fill of the SOURCE completes the section', () => {
    // This is the bug in the bead's title. The target is required AND
    // read_only: the AI cannot write it directly, so before the fan-out reached
    // the voice path the gate could never clear and the session dead-ended.
    const s = SchemaFormStateManager.updateField(
      fresh(gated()), 'family_name', 'GARCIA',
      { confirmed: true, confirmationMethod: 'ai_voice' })
    expect(valueOf(s, 'p8_family_name')).toBe('GARCIA')
    expect(SchemaFormStateManager.isSectionValid(s, 'sec')).toBe(true)
  })
})
