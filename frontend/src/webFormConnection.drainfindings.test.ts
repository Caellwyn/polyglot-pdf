/**
 * W3 (bd polyglot-pdf-pr3i): the FINDING-DRIVEN validator queue + drain.
 *
 * A `validation_result` is REPORT-ONLY since W3: a surviving conflict is ENQUEUED
 * into the persisted validatorFindingsQueue and DRAINED immediately (drain_findings),
 * and the fields are marked steered + consumed only when the backend confirms
 * delivery (drain_findings_result). A CLEAN result enqueues nothing + drains nothing.
 *
 * Driven through the production message path (a real validation_result inbound), so a
 * pass proves the real enqueue/drain wiring, not a hand-built call.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import { SchemaFormStateManager } from './schema-forms/state/schemaFormState'
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

const SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { title: 'T', version: '1.0.0', language: 'en', form_number: 'W3', edition_date: '01/01/25', page_count: 1 },
  fields: [
    { id: 'f_a', name: 'fielda', spoken_name: 'Field A', type: 'text' },
    { id: 'f_b', name: 'fieldb', spoken_name: 'Field B', type: 'text' },
  ],
  sections: [{ id: 'only', label: 'Only', order: 1, fields: ['f_a', 'f_b'] }],
} as unknown as FormSchema

function lastWs(): MockWebSocket { return MockWebSocket.instances[MockWebSocket.instances.length - 1] }
function sentMessages(ws: MockWebSocket): any[] {
  return ws.send.mock.calls.map((c: any[]) => c[0]).filter((a: any) => typeof a === 'string').map((s: string) => JSON.parse(s))
}
function ofType(ws: MockWebSocket, type: string): any[] { return sentMessages(ws).filter(m => m.type === type) }
function deliverValidationResult(ws: MockWebSocket, conflicts: any[]): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'validation_result', conflicts }) })
}
function deliverDrainResult(ws: MockWebSocket, conflicts: any[]): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'drain_findings_result', conflicts }) })
}
// Fire session_ready (the seam handleSessionReady -- reconnect re-drain -- hangs off).
function deliverSessionReady(ws: MockWebSocket): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'session_ready', session_id: 'sess-1' }) })
}
const flush = () => new Promise<void>(r => setTimeout(r, 0))

const CONFLICT = { field_ids: ['f_a', 'f_b'], reason: 'mismatch', field_names: { f_a: 'Field A', f_b: 'Field B' } }

describe('WebFormConnection W3 finding queue + drain (bd polyglot-pdf-pr3i)', () => {
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
    ws.send.mockClear()
    return ws
  }

  it('a CLEAN validation_result enqueues nothing and drains nothing (no voice turn)', async () => {
    const ws = await connected(SCHEMA)
    deliverValidationResult(ws, [])
    await flush()
    expect(ofType(ws, 'drain_findings')).toHaveLength(0)
    expect(SchemaFormStateManager.load()!.validatorFindingsQueue).toHaveLength(0)
  })

  it('a CONFLICT validation_result enqueues it and drains immediately', async () => {
    const ws = await connected(SCHEMA)
    deliverValidationResult(ws, [CONFLICT])
    await flush()
    const drains = ofType(ws, 'drain_findings')
    expect(drains).toHaveLength(1)
    expect(drains[0].conflicts).toHaveLength(1)
    expect(drains[0].conflicts[0].field_ids).toEqual(['f_a', 'f_b'])
    // The names ride the drain payload (the composer needs them).
    expect(drains[0].conflicts[0].field_names).toEqual({ f_a: 'Field A', f_b: 'Field B' })
    // Queued, not yet steered (delivery unconfirmed).
    const state = SchemaFormStateManager.load()!
    expect(state.validatorFindingsQueue).toHaveLength(1)
    expect(state.fieldValues['f_a']?.steered).toBeFalsy()
  })

  it('a DUPLICATE conflict (same field set) does not re-enqueue or re-drain', async () => {
    const ws = await connected(SCHEMA)
    deliverValidationResult(ws, [CONFLICT])
    await flush()
    ws.send.mockClear()
    // Same conflict, field_ids in a different order -> same set -> deduped.
    deliverValidationResult(ws, [{ ...CONFLICT, field_ids: ['f_b', 'f_a'] }])
    await flush()
    expect(ofType(ws, 'drain_findings')).toHaveLength(0) // no new drain
    expect(SchemaFormStateManager.load()!.validatorFindingsQueue).toHaveLength(1)
  })

  it('the drain result marks the fields steered and CONSUMES them from the queue', async () => {
    const ws = await connected(SCHEMA)
    deliverValidationResult(ws, [CONFLICT])
    await flush()
    deliverDrainResult(ws, [{ field_ids: ['f_a', 'f_b'] }])
    await flush()
    const state = SchemaFormStateManager.load()!
    expect(state.validatorFindingsQueue).toHaveLength(0)          // consumed
    // Note: markFieldsSteered needs an existing fieldValue entry; f_a/f_b have none
    // here (no value set), so the marker is a no-op on a missing entry -- the CONSUME
    // is the observable guarantee. (The steered-marker-lands case is covered in
    // validatorsteer.test.ts, where the field has a confirmed value.)
  })

  it('an UNDELIVERED drain (empty result) keeps the finding queued to retry', async () => {
    const ws = await connected(SCHEMA)
    deliverValidationResult(ws, [CONFLICT])
    await flush()
    deliverDrainResult(ws, []) // backend delivered nothing (dead session)
    await flush()
    expect(SchemaFormStateManager.load()!.validatorFindingsQueue).toHaveLength(1) // still queued
  })

  it('the queue persists across a reconnect and re-drains', async () => {
    const ws1 = await connected(SCHEMA)
    deliverValidationResult(ws1, [CONFLICT])
    await flush()
    expect(SchemaFormStateManager.load()!.validatorFindingsQueue).toHaveLength(1)
    conn!.disconnect(); conn = null

    // Reconnect (same schema -> reuses persisted state incl. the queue).
    const ws2 = await connected(SCHEMA)
    deliverSessionReady(ws2) // the seam handleSessionReady's re-drain hangs off
    await flush()
    const drains = ofType(ws2, 'drain_findings')
    expect(drains.length).toBeGreaterThanOrEqual(1)
    expect(drains[drains.length - 1].conflicts[0].field_ids).toEqual(['f_a', 'f_b'])
  })
})
