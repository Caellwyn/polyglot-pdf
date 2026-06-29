/**
 * Tests for the secretary's two client-owned inputs (bd polyglot-pdf-p68s /
 * jnjj.45d): the full-form schema at handshake, and per-field `shown`
 * (applicability) on the form_state_response round-trip.
 *
 * The backend is stateless and cannot derive either: the client owns the whole
 * form schema and computes conditional visibility (shouldShowField). These tests
 * assert the wire payloads the backend's secretary handler consumes.
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

// A conditional field: `spouse_name` is shown ONLY when marital_status === 'married'.
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    {
      id: 'marital_status',
      name: 'maritalStatus',
      spoken_name: 'Marital Status',
      type: 'select',
      options: [
        { value: 'single', label: 'Single' },
        { value: 'married', label: 'Married' },
      ],
    },
    {
      id: 'spouse_name',
      name: 'spouseName',
      spoken_name: 'Spouse Name',
      type: 'text',
      show_if: { field: 'marital_status', operator: 'equals', value: 'married' },
    },
    {
      id: 'first_name',
      name: 'firstName',
      spoken_name: 'First Name',
      type: 'text',
    },
  ],
  sections: [
    {
      id: 's1',
      label: 'S1',
      order: 1,
      fields: ['marital_status', 'spouse_name', 'first_name'],
    },
  ],
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

function installSessionStorage(): void {
  const store: Record<string, string> = {}
  global.sessionStorage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { for (const k of Object.keys(store)) delete store[k] },
    key: () => null,
    length: 0,
  } as unknown as Storage
}

describe('WebFormConnection secretary catalog handshake (bd polyglot-pdf-p68s)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    installSessionStorage()
  })

  it('handshake carries full_schema = the WHOLE form (all sections/fields)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()

    const handshake = sentMessages(ws).find(m =>
      m.type === 'handshake' || m.type === 'handshake_jit')
    expect(handshake).toBeDefined()
    // full_schema is the complete form: all three fields, not a section subset.
    expect(handshake.full_schema).toBeDefined()
    const ids = (handshake.full_schema.fields || []).map((f: any) => f.id).sort()
    expect(ids).toEqual(['first_name', 'marital_status', 'spouse_name'])
    expect((handshake.full_schema.sections || []).length).toBe(1)
  })
})

describe('WebFormConnection form_state_response carries shown (bd polyglot-pdf-p68s)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    installSessionStorage()
  })

  function formStateResponse(ws: MockWebSocket): any {
    return sentMessages(ws).find(m => m.type === 'form_state_response')
  }

  it('a value-bearing field that became conditionally hidden reports shown=false', async () => {
    // The value-vs-applicability case the renderer exists for: a field that HAS a
    // value but is now hidden by a changed condition. The all-fields branch returns
    // every touched field, so spouse_name (filled, then hidden) appears with
    // shown=false -- letting the secretary distinguish "answered but no longer
    // applicable" from "answered and applicable".
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // 1) marital_status = married -> spouse_name applicable; fill it.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { maritalStatus: 'married', spouseName: 'Sam' } }),
    })
    // 2) marital_status flips to single -> spouse_name's show_if is now unmet, but
    //    its stored value remains.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { maritalStatus: 'single' } }),
    })

    // Backend asks for the full form state (the secretary tail round-trip).
    ws.onmessage?.({
      data: JSON.stringify({ type: 'get_form_state', request_id: 'req-1', field_ids: [] }),
    })

    const resp = formStateResponse(ws)
    expect(resp).toBeDefined()
    // marital_status itself is always shown (no show_if).
    expect(resp.field_values.marital_status.shown).toBe(true)
    // spouse_name still HAS its value but is hidden by the unmet condition.
    expect(resp.field_values.spouse_name.value).toBe('Sam')
    expect(resp.field_values.spouse_name.shown).toBe(false)
  })

  it('the conditional field reports shown=true while its trigger is met', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // marital_status = 'married' -> spouse_name becomes applicable; fill it so it
    // appears in the all-fields response.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { maritalStatus: 'married', spouseName: 'Sam' } }),
    })
    ws.onmessage?.({
      data: JSON.stringify({ type: 'get_form_state', request_id: 'req-2', field_ids: [] }),
    })

    const resp = formStateResponse(ws)
    expect(resp.field_values.spouse_name.shown).toBe(true)
  })

  it('shown rides a requested-field response too (not just the all-fields branch)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { maritalStatus: 'single' } }),
    })
    // Ask for spouse_name explicitly -- it is unfilled AND hidden; the entry must
    // still carry shown=false (computed against the full value map).
    ws.onmessage?.({
      data: JSON.stringify({
        type: 'get_form_state', request_id: 'req-3', field_ids: ['spouse_name'],
      }),
    })

    const resp = formStateResponse(ws)
    expect(resp.field_values.spouse_name).toBeDefined()
    expect(resp.field_values.spouse_name.value).toBeNull()
    expect(resp.field_values.spouse_name.shown).toBe(false)
  })
})
