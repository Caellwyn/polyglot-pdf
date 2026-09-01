/**
 * The AI ingress must reach the copy_to fan-out (bd polyglot-pdf-gpaed).
 *
 * The fix lives at the state chokepoint (SchemaFormStateManager.updateField) and
 * schemaFormState.copyto.test.ts pins it there. This file pins the OTHER half:
 * that the voice path actually REACHES that chokepoint.
 *
 * Why both are needed -- fresh-eyes' finding. Real gating sits between Gemini's
 * message and the chokepoint, and it sits at TWO levels:
 *   - handleFieldUpdate (the message handler) does the read-only / hidden
 *     availability check and refuses a locked field outright;
 *   - applyAiValueWithValidation (below it) validates and canonicalizes.
 * A chokepoint-only test cannot catch a regression where the AI path stops
 * reaching updateField at all -- for instance a future change that
 * special-cases a copy_to source upstream.
 *
 * So the LAST describe here drives handleFieldUpdate with a message-shaped
 * payload, covering the whole span; the others drive
 * applyAiValueWithValidation, which covers everything BELOW the availability
 * gate. An earlier version of this docstring claimed the latter covered the
 * lock check too -- it does not, that check lives one level above it
 * (fresh-eyes, round 2).
 *
 * ASCII only.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import { SchemaFormStateManager } from './schema-forms/state/schemaFormState'
import { computeNextField } from './navigation'
import type { FormSchema } from './schema-forms/types/schema'

/** The i-90 shape: a Part 1 answer repeating on page 8, target read-only. */
function schema(required = false): FormSchema {
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
        ...(required ? { validation: { required: true } } : {}),
      },
    ],
    sections: [{
      id: 'sec', label: 'Sec', order: 1,
      fields: ['family_name', 'p8_family_name'],
    }],
  } as unknown as FormSchema
}

function stubStorage() {
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
}

/** Drive the REAL AI ingress, the way a Gemini field-fill message does. */
function aiFill(conn: WebFormConnection, s: FormSchema, fieldId: string, value: string) {
  const field = s.fields.find(f => f.id === fieldId)!
  // applyAiValueWithValidation is private; the point of this test is to go
  // through it rather than around it.
  return (conn as any).applyAiValueWithValidation(field, value, { emit: false })
}

describe('the AI ingress reaches the copy_to fan-out (bd polyglot-pdf-gpaed)', () => {
  beforeEach(() => { stubStorage() })

  it('an AI fill of the source populates the target', () => {
    const s = schema()
    const conn = new WebFormConnection(s)
    const applied = aiFill(conn, s, 'family_name', 'GARCIA')

    expect(applied).toBe(true)
    const state = (conn as any).state
    expect(state.fieldValues['family_name']?.value).toBe('GARCIA')
    expect(state.fieldValues['p8_family_name']?.value).toBe('GARCIA')
  })

  it('the fanned-out target clears a REQUIRED section gate', () => {
    // The dead-end from the bead's title: the target is required AND read_only,
    // so the AI cannot fill it directly and the section could never complete.
    const s = schema(true)
    const conn = new WebFormConnection(s)

    expect(SchemaFormStateManager.isSectionValid((conn as any).state, 'sec'))
      .toBe(false)                                    // non-vacuity floor

    aiFill(conn, s, 'family_name', 'GARCIA')

    expect(SchemaFormStateManager.isSectionValid((conn as any).state, 'sec'))
      .toBe(true)
  })

  it('the fan-out persists, so a reload keeps the target filled', () => {
    const s = schema()
    const conn = new WebFormConnection(s)
    aiFill(conn, s, 'family_name', 'GARCIA')

    const reloaded = SchemaFormStateManager.load()
    expect(reloaded?.fieldValues['p8_family_name']?.value).toBe('GARCIA')
  })
})

describe('the MESSAGE handler reaches the fan-out too (bd polyglot-pdf-gpaed)', () => {
  beforeEach(() => { stubStorage() })

  it('a field_update message fans the value out to the target', () => {
    // One level ABOVE applyAiValueWithValidation: handleFieldUpdate does the
    // read-only/hidden availability check and refuses a locked field. Driving
    // it with a message-shaped payload covers that gate too, which the tests
    // above deliberately do not.
    const s = schema()
    const conn = new WebFormConnection(s)
    ;(conn as any).handleFieldUpdate({ updates: { family_name: 'GARCIA' } })

    const state = (conn as any).state
    expect(state.fieldValues['family_name']?.value).toBe('GARCIA')
    expect(state.fieldValues['p8_family_name']?.value).toBe('GARCIA')
  })

  it('the SOURCE being writable is what matters, not the locked target', () => {
    // The target is read_only, so the availability gate would refuse a direct
    // AI write to it. The whole point of the fan-out is that the source is
    // writable and carries the value across.
    const s = schema()
    const conn = new WebFormConnection(s)
    ;(conn as any).handleFieldUpdate({ updates: { p8_family_name: 'DIRECT' } })
    expect((conn as any).state.fieldValues['p8_family_name']?.value)
      .not.toBe('DIRECT')
  })
})

describe('the fan-out must not TRAP the session (bd polyglot-pdf-gpaed)', () => {
  beforeEach(() => { stubStorage() })

  /** Source, a normal next question, and the read_only copy target. */
  function nav(): FormSchema {
    return {
      source: 'pdf',
      form_metadata: {
        title: 'T', version: '1.0.0', language: 'en',
        form_number: 'I-90', edition_date: '01/01/25', page_count: 1,
      },
      fields: [
        { id: 'a_number', name: 'a_number', spoken_name: 'A number',
          type: 'text', section_id: 'sec', copy_to: ['p8_a_number'] },
        { id: 'uscis_account', name: 'uscis_account',
          spoken_name: 'USCIS account', type: 'text', section_id: 'sec' },
        { id: 'p8_a_number', name: 'p8_a_number', spoken_name: 'A number (p8)',
          type: 'text', section_id: 'sec', read_only: true },
      ],
      sections: [{ id: 'sec', label: 'Sec', order: 1,
        fields: ['a_number', 'uscis_account', 'p8_a_number'] }],
    } as unknown as FormSchema
  }

  it('never navigates to the copy target after an AI fill', () => {
    // The cross-surface finding, at the level that matters. An AI fill lands
    // confirmed:false; if the fan-out inherited that, computeNextField's
    // filled-but-unconfirmed pass would send the session to p8_a_number -- a
    // read_only field the model cannot fill (refused) and can no longer skip
    // (it now holds a value). A dead end worse than the bug being fixed.
    const s = nav()
    const conn = new WebFormConnection(s)
    ;(conn as any).handleFieldUpdate({ updates: { a_number: 'A123' } })

    const next = computeNextField((conn as any).state)
    expect(next?.id).not.toBe('p8_a_number')
  })

  it('the copy target is not left as an unconfirmed loose end', () => {
    const s = nav()
    const conn = new WebFormConnection(s)
    ;(conn as any).handleFieldUpdate({ updates: { a_number: 'A123' } })

    const unconfirmed = SchemaFormStateManager
      .getUnconfirmedFields((conn as any).state)
      .map((f: any) => (typeof f === 'string' ? f : f.id))
    expect(unconfirmed).not.toContain('p8_a_number')
  })
})
