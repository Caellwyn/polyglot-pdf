/**
 * W2 (bd polyglot-pdf-kxkw): the client emits `validate_windows` as the fill
 * advances past overlapping stride windows -- driven through the production
 * confirm/field-update path (not a hand-built payload), so a pass proves the real
 * seam. Page-AGNOSTIC: a source:"web" (pageless) schema emits identically to a
 * paginated one; no pdf_position.page anywhere in the trigger.
 *
 * Window knobs are 20/10 in production (private constants). To exercise the emit
 * without a 20+-field fixture, these tests fill enough fields to cross the real
 * boundary on a right-sized schema.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import type { FormSchema } from './schema-forms/types/schema'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3
  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((e: any) => void) | null = null
  onerror: ((e: any) => void) | null = null
  onclose: ((e: any) => void) | null = null
  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    queueMicrotask(() => { this.readyState = MockWebSocket.OPEN; this.onopen?.() })
  }
  send = vi.fn()
  close = vi.fn(() => { this.readyState = MockWebSocket.CLOSED })
}

// N text fields in one section, in schema order.
function nFieldSchema(n: number, source: 'pdf' | 'web' = 'web'): FormSchema {
  const fields = Array.from({ length: n }, (_, i) => ({
    id: `f${i}`, name: `field${i}`, spoken_name: `Field ${i}`, type: 'text',
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

function lastWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}
function sentMessages(ws: MockWebSocket): any[] {
  return ws.send.mock.calls
    .map((c: any[]) => c[0])
    .filter((arg: any) => typeof arg === 'string')
    .map((s: string) => JSON.parse(s))
}
function ofType(ws: MockWebSocket, type: string): any[] {
  return sentMessages(ws).filter(m => m.type === type)
}
function fireFieldUpdate(ws: MockWebSocket, name: string, value: string): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { [name]: value } }) })
}
function fireConfirm(ws: MockWebSocket, fieldId: string): void {
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'confirm_field', field_id: fieldId,
      request_id: 'req-' + fieldId, confirmation_method: 'verbal',
    }),
  })
}
// Fill + confirm fields f0..f(count-1) in order.
function fillFirst(ws: MockWebSocket, count: number): void {
  for (let i = 0; i < count; i++) {
    fireFieldUpdate(ws, `field${i}`, `v${i}`)
    fireConfirm(ws, `f${i}`)
  }
}

describe('WebFormConnection validate_windows stride emit (bd polyglot-pdf-kxkw)', () => {
  let conn: WebFormConnection | null = null

  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error override global WebSocket with the mock
    global.WebSocket = MockWebSocket
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null, length: 0,
    } as unknown as Storage
  })
  afterEach(() => { conn?.disconnect(); conn = null })

  async function connected(schema: FormSchema): Promise<MockWebSocket> {
    conn = new WebFormConnection(schema)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send
    return ws
  }

  it('does NOT emit validate_windows before the fill passes the first window boundary', async () => {
    const ws = await connected(nFieldSchema(50))
    fillFirst(ws, 5) // window 0 = [0,20); 5 confirmed is not past it
    expect(ofType(ws, 'validate_windows')).toHaveLength(0)
  })

  it('emits validate_windows carrying the window fields once the fill passes window 0 (20 confirmed)', async () => {
    const ws = await connected(nFieldSchema(50))
    fillFirst(ws, 20) // hwm index 19 = window 0 end-1 -> window 0 eligible
    const events = ofType(ws, 'validate_windows')
    expect(events).toHaveLength(1)
    expect(Array.isArray(events[0].windows)).toBe(true)
    expect(events[0].windows).toHaveLength(1) // only window 0 ready
    // window 0 = fields f0..f19 (20 fields), contract-2 shape.
    const w0 = events[0].windows[0]
    expect(w0).toHaveLength(20)
    expect(w0[0]).toEqual({ field_id: 'f0', name: 'Field 0', value: 'v0', steered: false })
    expect(w0[19].field_id).toBe('f19')
  })

  it('got6: after an []-alias value migration, an EXACT-KEY-FIRST reader (buildValidatorFields.valueFor) gets the MIGRATED value', async () => {
    // bd polyglot-pdf-got6, closing the fresh-eyes coverage gap through the actual
    // validator-projection READ SEMANTICS. buildValidatorFields.valueFor
    // (webFormConnection.ts) reads the EXACT schema-id key first, then falls back to
    // the []-variant. The got6 bug was that a migration left a STALE entry under the
    // exact key, so valueFor read it. Fill f5 under its id, then migrate to f5[]
    // with a NEW value; the got6 fix removes the stale f5 key, so valueFor's
    // exact-key-first read now correctly falls back to f5[] and gets the migration.
    const conn2 = new WebFormConnection(nFieldSchema(50))
    conn2.updateField('f5', 'stale', { confirmed: true })
    conn2.updateField('f5[]', 'migrated', { confirmed: true })
    const state = (conn2 as any).state
    // Replicate buildValidatorFields.valueFor's exact-key-first + []-fallback read.
    const valueFor = (fieldId: string): any => {
      let fv = state.fieldValues[fieldId]
      if (!fv && !fieldId.endsWith('[]')) fv = state.fieldValues[fieldId + '[]']
      if (!fv && fieldId.endsWith('[]')) fv = state.fieldValues[fieldId.slice(0, -2)]
      return fv
    }
    // valueFor for schema field 'f5' returns the migrated value, not the stale one.
    expect(valueFor('f5')?.value).toBe('migrated')
    // And there is no stale exact-key entry to be read in preference.
    expect(state.fieldValues['f5']).toBeUndefined()
    conn2.disconnect()
  })

  it('does not re-send an already-sent window on later confirms (persisted high-water mark)', async () => {
    const ws = await connected(nFieldSchema(50))
    fillFirst(ws, 20)             // sends window 0
    ws.send.mockClear()
    fillFirst2(ws, 20, 25)        // confirm f20..f24 -- still inside window 1's range, not past it
    // window 0 must NOT be re-sent; nothing new is past yet (window 1 [10,30) needs hwm>=29).
    const events = ofType(ws, 'validate_windows')
    for (const e of events) {
      // if anything emitted, it must not contain window 0's field set again
      for (const w of e.windows) {
        expect(w[0].field_id).not.toBe('f0')
      }
    }
  })

  it('emits overlapping windows as the fill advances further', async () => {
    const ws = await connected(nFieldSchema(50))
    fillFirst(ws, 30) // hwm index 29: window 0 [0,20) AND window 1 [10,30) both eligible
    const events = ofType(ws, 'validate_windows')
    // All eligible-and-unsent windows ride ONE message (per confirm that newly makes
    // them ready). Collect every window sent across the fill.
    const allWindows = events.flatMap(e => e.windows)
    const firstIds = allWindows.map(w => w[0].field_id)
    expect(firstIds).toContain('f0')  // window 0
    expect(firstIds).toContain('f10') // window 1
  })

  it('is PAGE-AGNOSTIC: a pageless web schema emits validate_windows just like a pdf schema', async () => {
    const wsWeb = await connected(nFieldSchema(25, 'web'))
    fillFirst(wsWeb, 25)
    const web = ofType(wsWeb, 'validate_windows')
    conn?.disconnect(); conn = null
    MockWebSocket.instances = []

    const wsPdf = await connected(nFieldSchema(25, 'pdf'))
    fillFirst(wsPdf, 25)
    const pdf = ofType(wsPdf, 'validate_windows')

    // Same number of validate_windows emissions + same window field-id shape.
    const webIds = web.flatMap(e => e.windows.map((w: any[]) => w.map(f => f.field_id)))
    const pdfIds = pdf.flatMap(e => e.windows.map((w: any[]) => w.map(f => f.field_id)))
    expect(webIds).toEqual(pdfIds)
    expect(webIds.length).toBeGreaterThan(0)
  })

  // Confirm f{from}..f{to-1}.
  function fillFirst2(ws: MockWebSocket, from: number, to: number): void {
    for (let i = from; i < to; i++) {
      fireFieldUpdate(ws, `field${i}`, `v${i}`)
      fireConfirm(ws, `f${i}`)
    }
  }

  it('does not re-send an already-sent window after a disconnect + reconnect (persisted high-water)', async () => {
    // Opus outer-review finding 2: prove the persistence guarantee END-TO-END (send
    // -> save -> reconnect from the persisted state -> no re-emit), not just via the
    // two unit mechanisms. The sessionStorage `store` survives across connections in
    // one beforeEach, and a fresh WebFormConnection for the SAME schema within 1h
    // reuses that persisted state (validatedWindowIndices included).
    const schema = nFieldSchema(25)
    const ws1 = await connected(schema)
    fillFirst(ws1, 20)                 // window 0 [0,20) settled -> sent
    expect(ofType(ws1, 'validate_windows')).toHaveLength(1)
    conn!.disconnect()
    conn = null

    // Reconnect (new connection, same schema -> reuses persisted state).
    const ws2 = await connected(schema)
    // A confirm on the reconnected session must NOT re-send window 0 (its index is
    // persisted in validatedWindowIndices). Confirm the rest to complete the form.
    fillFirst2(ws2, 20, 25)
    const reWindows = ofType(ws2, 'validate_windows').flatMap(e => e.windows)
    for (const w of reWindows) {
      expect(w[0].field_id).not.toBe('f0') // window 0 never rides again
    }
  })
})
