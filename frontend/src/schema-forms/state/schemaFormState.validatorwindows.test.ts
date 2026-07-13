/**
 * W2 (bd polyglot-pdf-kxkw): the async-validator STRIDE window builder.
 *
 * Two concerns pinned here:
 *   1. computeReadyWindows -- the PURE eligibility math: which overlapping windows
 *      (size/stride over schema field order) have been "passed" by the fill and are
 *      not yet sent. Page-AGNOSTIC by construction (keys on schema order + the
 *      confirmed flag, never pdf_position.page), so a source:"web" / pageless
 *      schema behaves identically to a paginated one (report-cadence revision
 *      2026-07-13).
 *   2. validatedWindowIndices persistence -- the Set survives a save/load round
 *      trip and defaults empty for a pre-W2 (old) session.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { FormSchema, SchemaFormState } from './schemaFormState'

// N text fields f0..f(N-1) in one section, in schema order. `source` is a knob so
// the same builder can prove PDF and pageless (web) forms behave identically.
function nFieldSchema(n: number, source: 'pdf' | 'web' = 'web'): FormSchema {
  const fields = Array.from({ length: n }, (_, i) => ({
    id: `f${i}`, name: `field${i}`, spoken_name: `Field ${i}`, type: 'text',
    section_id: 'sec',
  }))
  return {
    source,
    form_metadata: {
      title: 'W2 Test', version: '1.0.0', language: 'en',
      form_number: `W2-${source}-${n}`, edition_date: '01/01/25', page_count: 1,
    },
    fields,
    sections: [{ id: 'sec', label: 'Sec', order: 1, fields: fields.map(f => f.id) }],
  } as unknown as FormSchema
}

// Confirm the first `count` fields (schema order f0..f(count-1)) via the real API.
function confirmFirst(state: SchemaFormState, count: number): SchemaFormState {
  let s = state
  for (let i = 0; i < count; i++) {
    s = SchemaFormStateManager.updateField(s, `f${i}`, `v${i}`)
    s = SchemaFormStateManager.confirmField(s, `f${i}`, 'ai_voice')
  }
  return s
}

describe('W2 computeReadyWindows (bd polyglot-pdf-kxkw)', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null, length: 0,
    } as unknown as Storage
  })

  it('returns nothing until the fill has passed a window boundary', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    // size 20 / stride 10: window 0 = [0,20). It is "passed" once a confirmed field
    // exists at index 19 (i.e. 20 fields confirmed). With only 5 confirmed, nothing.
    state = confirmFirst(state, 5)
    expect(SchemaFormStateManager.computeReadyWindows(state, 20, 10)).toEqual([])
  })

  it('releases window 0 once the fill reaches its end (20 confirmed)', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    state = confirmFirst(state, 20) // hwm = index 19 = window 0 end-1
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    // Windows whose end-1 <= 19: window 0 [0,20) (end 20, end-1 19) and window 1
    // [10,30)? end 30, end-1 29 > 19 -> NOT ready. So only window 0.
    expect(ready.map(w => w.index)).toEqual([0])
    expect(ready[0]).toEqual({ index: 0, start: 0, end: 20 })
  })

  it('releases overlapping windows as the fill advances (stride < size)', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    state = confirmFirst(state, 30) // hwm = index 29
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    // window 0 [0,20) end-1 19 <= 29 ready; window 1 [10,30) end-1 29 <= 29 ready;
    // window 2 [20,40) end-1 39 > 29 not ready.
    expect(ready.map(w => w.index)).toEqual([0, 1])
    expect(ready.map(w => [w.start, w.end])).toEqual([[0, 20], [10, 30]])
  })

  it('excludes windows already recorded in validatedWindowIndices', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    state = confirmFirst(state, 30)
    state.validatedWindowIndices.add(0) // pretend window 0 was already sent
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    expect(ready.map(w => w.index)).toEqual([1]) // only the not-yet-sent one
  })

  it('releases the tail (partial) window only when the form is complete', () => {
    // 25 fields, size 20 / stride 10. Windows: 0 [0,20), 1 [10,30->25), 2 [20,25).
    // Confirm all 25 -> form complete. The tail windows (end clamped to 25, rawEnd
    // >= 25) release via the form-complete branch even though nothing is confirmed
    // "beyond" them.
    let state = SchemaFormStateManager.init(nFieldSchema(25))
    state = confirmFirst(state, 25)
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    expect(ready.map(w => w.index)).toEqual([0, 1, 2])
    expect(ready[ready.length - 1]).toEqual({ index: 2, start: 20, end: 25 })
  })

  it('is PAGE-AGNOSTIC: a pageless web schema and a paginated pdf schema yield identical windows', () => {
    let web = SchemaFormStateManager.init(nFieldSchema(30, 'web'))
    let pdf = SchemaFormStateManager.init(nFieldSchema(30, 'pdf'))
    web = confirmFirst(web, 30)
    pdf = confirmFirst(pdf, 30)
    const rw = SchemaFormStateManager.computeReadyWindows(web, 20, 10)
    const rp = SchemaFormStateManager.computeReadyWindows(pdf, 20, 10)
    expect(rw).toEqual(rp)
    expect(rw.length).toBeGreaterThan(0)
  })

  it('does not blow up on an empty schema or degenerate knobs', () => {
    const empty = SchemaFormStateManager.init(nFieldSchema(0))
    expect(SchemaFormStateManager.computeReadyWindows(empty, 20, 10)).toEqual([])
    let state = SchemaFormStateManager.init(nFieldSchema(30))
    state = confirmFirst(state, 30)
    expect(SchemaFormStateManager.computeReadyWindows(state, 0, 10)).toEqual([])
    expect(SchemaFormStateManager.computeReadyWindows(state, 20, 0)).toEqual([])
  })

  it('respects confirmed-field ORDER, not just count (out-of-order fill)', () => {
    // Confirm only a HIGH-index field (f24) and nothing else. hwm = 24, which passes
    // windows 0 and 1 even though only ONE field is confirmed -- the high-water fill
    // position, not the raw count, is what "passed a boundary" means.
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    state = SchemaFormStateManager.updateField(state, 'f24', 'x')
    state = SchemaFormStateManager.confirmField(state, 'f24', 'ai_voice')
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    // window 0 [0,20) end-1 19 <= 24 ready; window 1 [10,30) end-1 29 > 24 NOT ready.
    expect(ready.map(w => w.index)).toEqual([0])
  })
})

describe('W2 validatedWindowIndices persistence (bd polyglot-pdf-kxkw)', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null, length: 0,
    } as unknown as Storage
  })

  it('round-trips the Set through save/load as an array', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(30))
    state.validatedWindowIndices.add(0)
    state.validatedWindowIndices.add(2)
    SchemaFormStateManager.save(state)
    const loaded = SchemaFormStateManager.load()!
    expect(loaded.validatedWindowIndices instanceof Set).toBe(true)
    expect([...loaded.validatedWindowIndices].sort()).toEqual([0, 2])
  })

  it('defaults to an empty Set for a pre-W2 session (no key stored)', () => {
    // Simulate an old sessionStorage blob with NO validatedWindowIndices key.
    const legacy = {
      schema: nFieldSchema(10),
      fieldValues: {},
      currentSectionId: 'sec',
      completedSections: [],
      validationErrors: {},
      lastUpdated: Date.now(),
      formSessionId: 'fss_legacy',
      loadedFieldIds: [],
      jitModeEnabled: false,
      continuousSessionEnabled: false,
      disclaimerAccepted: false,
    }
    global.sessionStorage.setItem('schema_form_state', JSON.stringify(legacy))
    const loaded = SchemaFormStateManager.load()!
    expect(loaded.validatedWindowIndices instanceof Set).toBe(true)
    expect(loaded.validatedWindowIndices.size).toBe(0)
  })

  it('a fresh init starts with an empty validatedWindowIndices Set', () => {
    const state = SchemaFormStateManager.init(nFieldSchema(10))
    expect(state.validatedWindowIndices instanceof Set).toBe(true)
    expect(state.validatedWindowIndices.size).toBe(0)
  })
})
