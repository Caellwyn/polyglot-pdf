/**
 * The stale-session guard (bd polyglot-pdf-g2fpr, PR 3c / bead f2a8k).
 *
 * A session persisted under one shape of a kit can be resumed under another:
 * the select migration turns option values from export codes ('AL') into
 * slugs ('alabama') while a browser still holds 'AL' in sessionStorage. Left
 * alone that value matches no option -- the <select> renders EMPTY, the field
 * stays confirmed so it is never re-asked, and the filler writes 'AL'
 * verbatim, right only by coincidence. reconcileSelectValues maps a stored
 * value through the fresh schema's pdf_on_value (lossless) or clears it.
 *
 * ASCII only.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { FormSchema } from '../types/schema'

function schema(options: any[], extra: any[] = []): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', version: '1.0.0', language: 'en',
      form_number: 'I-90', edition_date: '01/01/25', page_count: 1,
    },
    fields: [
      { id: 'state', name: 'state', spoken_name: 'state', type: 'select',
        section_id: 'sec', options },
      { id: 'name', name: 'name', spoken_name: 'name', type: 'text', section_id: 'sec' },
      ...extra,
    ],
    sections: [{ id: 'sec', label: 'Sec', order: 1,
      fields: ['state', 'name', ...extra.map((f: any) => f.id)] }],
  } as unknown as FormSchema
}

/** The pre-migration shape: the code IS the value. */
const LEGACY = [{ value: 'AL', label: 'AL' }, { value: 'AK', label: 'AK' }]
/** The migrated shape: slug value, code in pdf_on_value. */
const MIGRATED = [
  { value: 'alabama', label: 'Alabama (AL)', pdf_on_value: 'AL' },
  { value: 'alaska', label: 'Alaska (AK)', pdf_on_value: 'AK' },
]

const stamp = (value: string, confirmed = true) => ({
  value, confirmed, confirmedAt: '2026-09-03T00:00:00.000Z',
  confirmationMethod: 'ai_voice' as const, lastModified: 1,
})

describe('reconcileSelectValues (bd polyglot-pdf-g2fpr PR 3c)', () => {
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

  const stateWith = (sch: FormSchema, fieldValues: Record<string, any>) =>
    ({ ...SchemaFormStateManager.init(sch), fieldValues }) as any

  it('EXIT CRITERION 1: a value stored under the OLD shape maps to the slug and stays confirmed', () => {
    const old = stateWith(schema(LEGACY), { state: stamp('AL'), name: stamp('Garcia') })
    const fresh = schema(MIGRATED)
    const out = SchemaFormStateManager.reconcileSelectValues(old, fresh)
    expect(out.fieldValues.state.value).toBe('alabama')
    expect(out.fieldValues.state.confirmed).toBe(true)
    expect(out.fieldValues.state.confirmationMethod).toBe('ai_voice')  // stamp preserved
    expect(out.fieldValues.name).toEqual(stamp('Garcia'))               // non-select untouched
    expect(out.schema).toBe(fresh)                                       // fresh schema adopted
  })

  it('EXIT CRITERION 2: a value matching neither a value nor a code is CLEARED, never kept', () => {
    const old = stateWith(schema(LEGACY), { state: stamp('ZZ') })
    const out = SchemaFormStateManager.reconcileSelectValues(old, schema(MIGRATED))
    expect(out.fieldValues.state).toBeUndefined()
  })

  it('a code two options claim is cleared, not guessed (the /resume-form policy)', () => {
    const colliding = [
      { value: 'alabama', label: 'Alabama', pdf_on_value: 'AL' },
      { value: 'alabama_north', label: 'Alabama North', pdf_on_value: 'AL' },
    ]
    const old = stateWith(schema(LEGACY), { state: stamp('AL') })
    const out = SchemaFormStateManager.reconcileSelectValues(old, schema(colliding))
    expect(out.fieldValues.state).toBeUndefined()
  })

  it('a value that is ALREADY current is untouched, and the result is the same object when nothing changes', () => {
    // init() deduplicates sections into a NEW schema object, so "the fresh
    // schema" here is the state's own -- identity can only hold for that.
    const cur = stateWith(schema(MIGRATED), { state: stamp('alabama') })
    const out = SchemaFormStateManager.reconcileSelectValues(cur, cur.schema)
    expect(out).toBe(cur)
    expect(out.fieldValues.state.value).toBe('alabama')
  })

  it('a legacy kit resumed under the SAME legacy shape is untouched', () => {
    const fresh = schema(LEGACY)
    const cur = stateWith(fresh, { state: stamp('AL') })
    expect(SchemaFormStateManager.reconcileSelectValues(cur, fresh).fieldValues.state.value).toBe('AL')
  })

  it('an empty or missing select value is left alone', () => {
    const old = stateWith(schema(LEGACY), { state: stamp('') })
    const out = SchemaFormStateManager.reconcileSelectValues(old, schema(MIGRATED))
    expect(out.fieldValues.state).toEqual(stamp(''))
  })

  it('tolerates malformed options without throwing', () => {
    const old = stateWith(schema(LEGACY), { state: stamp('AL') })
    const bad = schema([null, 'AL', { value: 'alabama', pdf_on_value: 'AL' }] as any)
    expect(() => SchemaFormStateManager.reconcileSelectValues(old, bad)).not.toThrow()
    expect(SchemaFormStateManager.reconcileSelectValues(old, bad).fieldValues.state.value).toBe('alabama')
  })

  it('init() applies it: a session persisted under the OLD shape resumes mapped and persisted', () => {
    // The real path: init() reuses a recent stored session (same form
    // number + version) and until PR 3c handed back its STORED schema and
    // values untouched.
    const old = SchemaFormStateManager.init(schema(LEGACY))
    SchemaFormStateManager.save({ ...old, fieldValues: { state: stamp('AL') } } as any)
    const resumed = SchemaFormStateManager.init(schema(MIGRATED))
    expect(resumed.fieldValues.state.value).toBe('alabama')
    expect(resumed.fieldValues.state.confirmed).toBe(true)
    expect((resumed.schema.fields[0] as any).options[0].value).toBe('alabama')  // fresh schema adopted
    // ...and persisted, so a raw load() sees the mapped value too.
    expect(SchemaFormStateManager.load()!.fieldValues.state.value).toBe('alabama')
  })

  it('init() clears an unmappable stored value rather than resuming with it', () => {
    const old = SchemaFormStateManager.init(schema(LEGACY))
    SchemaFormStateManager.save({ ...old, fieldValues: { state: stamp('ZZ') } } as any)
    const resumed = SchemaFormStateManager.init(schema(MIGRATED))
    expect(resumed.fieldValues.state).toBeUndefined()
  })
})
