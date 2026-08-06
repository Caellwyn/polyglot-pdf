/**
 * markFieldSkipped must honour the `[]`-alias like updateField does
 * (bd polyglot-pdf-8c97, the got6 one-entry invariant).
 *
 * A checkbox group's value can sit under either key variant -- Gemini drops or
 * adds the bracket (bd polyglot-pdf-5k52). updateField resolves the alias and
 * DELETES the stale variant so exactly one entry represents the field.
 * markFieldSkipped did neither: it wrote its exact key and left the other one in
 * place, making it the last remaining producer of the both-variants state.
 *
 * That state is not cosmetic. It breaks the one-entry invariant, and it hands
 * reconcileFieldValues a pair it then has to arbitrate -- the arbitration that
 * bd 8c97 was filed about.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { FormSchema } from '../types/schema'

function schema(): FormSchema {
  return {
    source: 'web',
    form_metadata: {
      title: 'T', version: '1.0.0', language: 'en',
      form_number: 'SK', edition_date: '01/01/25', page_count: 1,
    },
    fields: [
      {
        id: 'p1_grp', name: 'p1_grp', spoken_name: 'Group', type: 'checkbox_group',
        section_id: 'sec',
        options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
      },
    ],
    sections: [{ id: 'sec', label: 'Sec', order: 1, fields: ['p1_grp'] }],
  } as unknown as FormSchema
}

function groupKeys(state: any): string[] {
  return Object.keys(state.fieldValues).filter(k => k.startsWith('p1_grp')).sort()
}

describe('confirmField []-alias handling (bd polyglot-pdf-8c97)', () => {
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

  it('confirms through the alias and does NOT create a second entry', () => {
    // The reconcile consolidates an alias pair onto the schema's variant, so a
    // model that drops the bracket sends `p1_grp` for a value now under
    // `p1_grp[]`. An exact-key confirm would no-op (confirming nothing) or, if
    // it wrote to the requested key, create a second entry.
    let state: any = SchemaFormStateManager.init(schema())
    state = { ...state, fieldValues: { 'p1_grp[]': { value: ['a'], lastModified: 100 } } }

    const after = SchemaFormStateManager.confirmField(state, 'p1_grp', 'ai_voice')

    expect(groupKeys(after)).toEqual(['p1_grp[]'])
    expect(after.fieldValues['p1_grp[]'].confirmed).toBe(true)
    expect(after.fieldValues['p1_grp[]'].value).toEqual(['a'])
  })

  it('still no-ops when NEITHER variant has an entry', () => {
    const state: any = SchemaFormStateManager.init(schema())
    const after = SchemaFormStateManager.confirmField(state, 'p1_grp', 'ai_voice')
    expect(groupKeys(after)).toEqual([])
  })
})

describe('markFieldSkipped []-alias handling (bd polyglot-pdf-8c97)', () => {
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

  it('skipping the BARE id when the value sits under the bracket leaves ONE entry', () => {
    let state: any = SchemaFormStateManager.init(schema())
    state = { ...state, fieldValues: { 'p1_grp[]': { value: ['a'], lastModified: 100 } } }

    const after = SchemaFormStateManager.markFieldSkipped(state, 'p1_grp', 'ai_voice')

    expect(groupKeys(after)).toEqual(['p1_grp'])
    expect(after.fieldValues['p1_grp'].skipped).toBe(true)
    expect(after.fieldValues['p1_grp'].value).toBeNull()
  })

  it('skipping the BRACKETED id when the value sits under the bare key leaves ONE entry', () => {
    let state: any = SchemaFormStateManager.init(schema())
    state = { ...state, fieldValues: { 'p1_grp': { value: ['a'], lastModified: 100 } } }

    const after = SchemaFormStateManager.markFieldSkipped(state, 'p1_grp[]', 'ai_voice')

    expect(groupKeys(after)).toEqual(['p1_grp[]'])
    expect(after.fieldValues['p1_grp[]'].skipped).toBe(true)
  })

  it('carries the prior entry forward (the skip is not a fresh blank object)', () => {
    let state: any = SchemaFormStateManager.init(schema())
    state = {
      ...state,
      fieldValues: { 'p1_grp[]': { value: ['a'], steered: true, lastModified: 100 } },
    }

    const after = SchemaFormStateManager.markFieldSkipped(state, 'p1_grp', 'ai_voice')

    // The aliased prior entry was resolved and spread, not ignored.
    expect(after.fieldValues['p1_grp'].steered).toBe(true)
  })

  it('clears the validation error under the PRIOR key too', () => {
    // The alias resolution deletes the stale variant; an error recorded against
    // that key would otherwise outlive the entry it describes.
    let state: any = SchemaFormStateManager.init(schema())
    state = {
      ...state,
      fieldValues: { 'p1_grp[]': { value: ['a'], lastModified: 100 } },
      validationErrors: { 'p1_grp[]': 'Required' },
    }

    const after = SchemaFormStateManager.markFieldSkipped(state, 'p1_grp', 'ai_voice')

    expect(Object.keys(after.validationErrors)).not.toContain('p1_grp[]')
    expect(Object.keys(after.validationErrors)).not.toContain('p1_grp')
  })

  it('a skip with NO prior entry under either variant still records one entry', () => {
    const state: any = SchemaFormStateManager.init(schema())

    const after = SchemaFormStateManager.markFieldSkipped(state, 'p1_grp', 'ai_voice')

    expect(groupKeys(after)).toEqual(['p1_grp'])
    expect(after.fieldValues['p1_grp'].skipped).toBe(true)
  })
})
