/**
 * W3 (bd polyglot-pdf-pr3i): the validatorFindingsQueue state ops --
 * enqueueValidatorFindings (dedupe by field-id set) + consumeValidatorFindings
 * (remove drained), plus persistence + the pre-W3 migration default.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { SchemaFormState } from './schemaFormState'
import type { FormSchema, ValidatorFinding } from '../types/schema'

function schema(): FormSchema {
  return {
    source: 'web',
    form_metadata: { title: 'T', version: '1.0.0', language: 'en', form_number: 'W3Q', edition_date: '01/01/25', page_count: 1 },
    fields: [
      { id: 'a', name: 'a', spoken_name: 'A', type: 'text', section_id: 'sec' },
      { id: 'b', name: 'b', spoken_name: 'B', type: 'text', section_id: 'sec' },
      { id: 'c', name: 'c', spoken_name: 'C', type: 'text', section_id: 'sec' },
    ],
    sections: [{ id: 'sec', label: 'Sec', order: 1, fields: ['a', 'b', 'c'] }],
  } as unknown as FormSchema
}

const F_AB: ValidatorFinding = { field_ids: ['a', 'b'], reason: 'ab', field_names: { a: 'A', b: 'B' } }
const F_C: ValidatorFinding = { field_ids: ['c'], reason: 'c', field_names: { c: 'C' } }

describe('W3 validatorFindingsQueue ops (bd polyglot-pdf-pr3i)', () => {
  let base: SchemaFormState
  beforeEach(() => {
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null, length: 0,
    } as unknown as Storage
    base = SchemaFormStateManager.init(schema())
  })

  it('enqueues findings and appends only new field-id sets', () => {
    let s = SchemaFormStateManager.enqueueValidatorFindings(base, [F_AB])
    expect(s.validatorFindingsQueue).toHaveLength(1)
    // Re-enqueue the same set (order flipped) -> deduped, no growth, same reference.
    const s2 = SchemaFormStateManager.enqueueValidatorFindings(s, [{ ...F_AB, field_ids: ['b', 'a'] }])
    expect(s2).toBe(s)
    expect(s2.validatorFindingsQueue).toHaveLength(1)
    // A distinct set appends.
    const s3 = SchemaFormStateManager.enqueueValidatorFindings(s2, [F_C])
    expect(s3.validatorFindingsQueue.map(f => f.field_ids)).toEqual([['a', 'b'], ['c']])
  })

  it('drops malformed findings (no field_ids)', () => {
    const s = SchemaFormStateManager.enqueueValidatorFindings(base, [
      { field_ids: [], reason: 'empty' } as unknown as ValidatorFinding,
      { reason: 'no ids' } as unknown as ValidatorFinding,
      F_C,
    ])
    expect(s.validatorFindingsQueue.map(f => f.field_ids)).toEqual([['c']])
  })

  it('returns the same state reference when nothing new is enqueued', () => {
    expect(SchemaFormStateManager.enqueueValidatorFindings(base, [])).toBe(base)
  })

  it('consumes findings whose field-id set matches a delivered conflict', () => {
    let s = SchemaFormStateManager.enqueueValidatorFindings(base, [F_AB, F_C])
    expect(s.validatorFindingsQueue).toHaveLength(2)
    // Deliver only the (a,b) finding (order flipped) -> it is removed; (c) stays.
    s = SchemaFormStateManager.consumeValidatorFindings(s, [{ field_ids: ['b', 'a'] }])
    expect(s.validatorFindingsQueue.map(f => f.field_ids)).toEqual([['c']])
  })

  it('consume is a no-op (same reference) when nothing matches', () => {
    const s = SchemaFormStateManager.enqueueValidatorFindings(base, [F_AB])
    expect(SchemaFormStateManager.consumeValidatorFindings(s, [{ field_ids: ['x'] }])).toBe(s)
    expect(SchemaFormStateManager.consumeValidatorFindings(s, [])).toBe(s)
  })

  it('persists the queue across save/load and defaults [] for a pre-W3 session', () => {
    const s = SchemaFormStateManager.enqueueValidatorFindings(base, [F_AB])
    SchemaFormStateManager.save(s)
    const loaded = SchemaFormStateManager.load()!
    expect(loaded.validatorFindingsQueue.map(f => f.field_ids)).toEqual([['a', 'b']])

    // A pre-W3 blob (no key) loads as [].
    const legacy = {
      schema: schema(), fieldValues: {}, currentSectionId: 'sec', completedSections: [],
      validationErrors: {}, lastUpdated: Date.now(), formSessionId: 'fss', loadedFieldIds: [],
      jitModeEnabled: false, continuousSessionEnabled: false, disclaimerAccepted: false,
    }
    global.sessionStorage.setItem('schema_form_state', JSON.stringify(legacy))
    expect(SchemaFormStateManager.load()!.validatorFindingsQueue).toEqual([])
  })
})
