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
import type { SchemaFormState } from './schemaFormState'
import type { FormSchema } from '../types/schema'

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

  it('returns nothing until a whole window is settled', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    // size 20 / stride 10: window 0 = [0,20) is eligible only when ALL of f0..f19
    // are settled. With only 5 confirmed, no window is fully settled.
    state = confirmFirst(state, 5)
    expect(SchemaFormStateManager.computeReadyWindows(state, 20, 10)).toEqual([])
  })

  it('releases window 0 once ALL of its fields are settled (f0..f19 confirmed)', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    state = confirmFirst(state, 20) // f0..f19 confirmed -> window 0 fully settled
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    // window 0 [0,20) all settled -> ready; window 1 [10,30) has f20..f29 unsettled.
    expect(ready.map(w => w.index)).toEqual([0])
    expect(ready[0]).toEqual({ index: 0, start: 0, end: 20 })
  })

  it('releases overlapping windows as more fields settle (stride < size)', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    state = confirmFirst(state, 30) // f0..f29 all settled
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    // window 0 [0,20) settled; window 1 [10,30) settled; window 2 [20,40) has
    // f30..f39 unsettled -> not ready.
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

  it('releases the tail (partial) window when its fields settle -- no isFormComplete needed', () => {
    // 25 fields, size 20 / stride 10. Windows: 0 [0,20), 1 [10,25), 2 [20,25).
    // Confirm all 25 -> every window fully settled, including the short tail.
    let state = SchemaFormStateManager.init(nFieldSchema(25))
    state = confirmFirst(state, 25)
    const ready = SchemaFormStateManager.computeReadyWindows(state, 20, 10)
    expect(ready.map(w => w.index)).toEqual([0, 1, 2])
    expect(ready[ready.length - 1]).toEqual({ index: 2, start: 20, end: 25 })
  })

  it('does NOT starve a mid-window unconfirmed field: window 0 stays pending until f5 settles', () => {
    // Fresh-eyes regression (the high-water design fired + retired window 0 while f5
    // was still open). Confirm f0..f19 EXCEPT f5.
    let state = SchemaFormStateManager.init(nFieldSchema(50))
    for (let i = 0; i < 20; i++) {
      if (i === 5) continue
      state = SchemaFormStateManager.updateField(state, `f${i}`, `v${i}`)
      state = SchemaFormStateManager.confirmField(state, `f${i}`, 'ai_voice')
    }
    // window 0 [0,20) has f5 unsettled -> NOT ready.
    expect(SchemaFormStateManager.computeReadyWindows(state, 20, 10).map(w => w.index)).toEqual([])
    // Now settle f5 -> window 0 becomes ready (f5 is re-included, not starved).
    state = SchemaFormStateManager.updateField(state, 'f5', 'v5')
    state = SchemaFormStateManager.confirmField(state, 'f5', 'ai_voice')
    expect(SchemaFormStateManager.computeReadyWindows(state, 20, 10).map(w => w.index)).toEqual([0])
  })

  it('treats a SKIPPED field as settled (a user-skipped optional does not block its window)', () => {
    let state = SchemaFormStateManager.init(nFieldSchema(20))
    for (let i = 0; i < 20; i++) {
      if (i === 7) {
        state = SchemaFormStateManager.markFieldSkipped(state, `f${i}`)
      } else {
        state = SchemaFormStateManager.updateField(state, `f${i}`, `v${i}`)
        state = SchemaFormStateManager.confirmField(state, `f${i}`, 'ai_voice')
      }
    }
    // f7 skipped counts as settled -> the whole 20-field form is settled, so both
    // window 0 [0,20) and window 1 [10,20) are ready (a skip never blocks a window).
    expect(SchemaFormStateManager.computeReadyWindows(state, 20, 10).map(w => w.index)).toEqual([0, 1])
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

  it('guards against coverage gaps when stride > size (clamps step to size)', () => {
    // stride 30 > size 10 would leave fields 10..29 in no window; the builder clamps
    // the enumeration step to `size` so coverage stays contiguous. All 40 settled.
    let state = SchemaFormStateManager.init(nFieldSchema(40))
    state = confirmFirst(state, 40)
    const ready = SchemaFormStateManager.computeReadyWindows(state, 10, 30)
    // Every field index must be covered by at least one returned window.
    const covered = new Set<number>()
    for (const w of ready) for (let i = w.start; i < w.end; i++) covered.add(i)
    for (let i = 0; i < 40; i++) expect(covered.has(i)).toBe(true)
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
