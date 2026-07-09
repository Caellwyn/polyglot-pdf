/**
 * Tests for the voice skip_field handler (bd polyglot-pdf-7yra).
 *
 * skip_field lets the assistant force-skip a REQUIRED field the user cannot
 * answer. Unlike confirm_field there is NO usable-value gate: an empty REQUIRED
 * field -- which confirm_field REFUSES (the 0y7 loop-breaker) -- is recorded as
 * intentionally skipped (markFieldSkipped: empty value + skipped flag) and the
 * frontend acks recorded:true so the backend advances.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
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
    queueMicrotask(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.()
    })
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })
}

// One REQUIRED field in one section -- the case confirm_field cannot skip.
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    {
      id: 'p1_uscis_number',
      name: 'USCIS Number',
      spoken_name: 'USCIS Number',
      type: 'text',
      validation: { required: true },
    },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['p1_uscis_number'] }],
} as unknown as FormSchema

function lastWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

function sentMessages(ws: MockWebSocket): any[] {
  return ws.send.mock.calls
    .map((c: any[]) => c[0])
    .filter((arg: any) => typeof arg === 'string')
    .map((s: string) => JSON.parse(s))
}

function fireSkip(ws: MockWebSocket, fieldId: string, requestId = 'req-1'): void {
  ws.onmessage?.({
    data: JSON.stringify({ type: 'skip_field', field_id: fieldId, request_id: requestId }),
  })
}

function skipAcks(ws: MockWebSocket): any[] {
  return sentMessages(ws).filter(m => m.type === 'skip_field_response')
}

describe('WebFormConnection skip_field handler (bd polyglot-pdf-7yra)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    } as unknown as Storage
  })

  async function connected(): Promise<{ conn: WebFormConnection; ws: MockWebSocket }> {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send
    return { conn, ws }
  }

  it('records a skip on an empty REQUIRED field and acks recorded:true', async () => {
    const { conn, ws } = await connected()

    fireSkip(ws, 'p1_uscis_number')
    await Promise.resolve() // let the async handler run

    const acks = skipAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(true)
    expect(acks[0].request_id).toBe('req-1')

    // The field is marked skipped in state (empty value + skipped flag).
    const fv = (conn as any).state.fieldValues['p1_uscis_number']
    expect(fv?.skipped).toBe(true)
    expect(fv?.value ?? null).toBeNull()
  })

  it('REFUSES to skip an already-filled field (no data loss) and acks already_filled', async () => {
    const { conn, ws } = await connected()

    // Fill the field first (production field_update path keyed by name).
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { 'USCIS Number': 'A123456789' } }),
    })
    await Promise.resolve()
    ws.send.mockClear()

    fireSkip(ws, 'p1_uscis_number')
    await Promise.resolve()

    const acks = skipAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(false)
    expect(acks[0].reason).toBe('already_filled')

    // The real value is INTACT -- not blanked, not marked skipped.
    const fv = (conn as any).state.fieldValues['p1_uscis_number']
    expect(fv?.value).toBe('A123456789')
    expect(fv?.skipped).toBeFalsy()
  })

  it('acks recorded:false for an unknown field id', async () => {
    const { ws } = await connected()

    fireSkip(ws, 'no_such_field')
    await Promise.resolve()

    const acks = skipAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(false)
    expect(acks[0].reason).toBe('unknown_field')
  })

  it('does not ack OR mutate state when request_id is missing', async () => {
    const { conn, ws } = await connected()

    // No request_id -> the handler cannot ack the synchronous round-trip, so it
    // must NOT record the skip or advance (that would silently diverge from what
    // the backend believes). The real backend always sends request_id.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'skip_field', field_id: 'p1_uscis_number' }),
    })
    await Promise.resolve()

    expect(skipAcks(ws)).toHaveLength(0)
    // State untouched: the field is not marked skipped.
    const fv = (conn as any).state.fieldValues['p1_uscis_number']
    expect(fv?.skipped).toBeFalsy()
  })
})
