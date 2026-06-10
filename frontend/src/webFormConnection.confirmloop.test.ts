/**
 * Regression tests for the unconfirmable-field loop-breaker (bd polyglot-pdf-0y7).
 *
 * A confirm_field can only make progress when the field has a usable value.
 * Without one, computeNextField() keeps returning the SAME field on every request
 * -- a tight confirm_field / next_field_hint loop that strands the session and
 * silences Gemini. handleConfirmFieldRequest() now gates on the field VALUE (not on
 * confirmField()'s confirmed flag, which would falsely "succeed" on an empty-valued
 * entry), counts consecutive failed confirms of the same field, and every
 * CONFIRM_LIMIT attempts re-prompts Gemini (via completion_message -> send_prompt)
 * to collect the value -- up to a hard REPROMPT_CAP, after which it stops entirely
 * so a genuinely unfillable field does not spin even at the reduced re-prompt rate.
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

// One section with one field. The field exists in the schema; whether it has a
// value is controlled per-test via field_update, exactly as in production.
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    {
      id: 'p1_line1_aliennumber',
      name: 'aliennumber',
      spoken_name: 'Alien Number',
      type: 'text',
    },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['p1_line1_aliennumber'] }],
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

function prompts(ws: MockWebSocket): any[] {
  return sentMessages(ws).filter(m => m.type === 'completion_message')
}

function fireConfirm(ws: MockWebSocket, fieldId: string, requestId?: string): void {
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'confirm_field',
      field_id: fieldId,
      confirmation_method: 'verbal',
      ...(requestId ? { request_id: requestId } : {}),
    }),
  })
}

function confirmAcks(ws: MockWebSocket): any[] {
  return sentMessages(ws).filter(m => m.type === 'confirm_field_response')
}

// Drive a real value into the field through the production field_update path
// (keyed by field name or id), so confirm_field can take.
function fireFieldUpdate(ws: MockWebSocket, value: string): void {
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'field_update',
      updates: { aliennumber: value },
    }),
  })
}

describe('WebFormConnection unconfirmable-field loop-breaker (bd polyglot-pdf-0y7)', () => {
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

  async function connected(): Promise<MockWebSocket> {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send so we only see confirm-driven sends
    return ws
  }

  it('does NOT re-prompt on the first failed confirm of an empty field', async () => {
    const ws = await connected()

    fireConfirm(ws, 'p1_line1_aliennumber')

    expect(prompts(ws)).toHaveLength(0)
  })

  it('breaks the loop and prompts Gemini after repeated failed confirms of the same empty field', async () => {
    const ws = await connected()

    // First attempt: tracked, no prompt yet.
    fireConfirm(ws, 'p1_line1_aliennumber')
    // Second attempt hits the limit -> corrective prompt.
    fireConfirm(ws, 'p1_line1_aliennumber')

    const p = prompts(ws)
    expect(p).toHaveLength(1)
    expect(p[0].message).toContain('Alien Number')
    expect(p[0].message).toContain('cannot be confirmed')
  })

  it('detects a field whose value entry exists but is EMPTY (the case confirmField would wrongly confirm)', async () => {
    const ws = await connected()

    // An entry exists but the value is empty -- confirmField() would set confirmed:true
    // on it, hiding the loop. The value-based guard must still treat it as unconfirmable.
    fireFieldUpdate(ws, '')
    fireConfirm(ws, 'p1_line1_aliennumber')
    fireConfirm(ws, 'p1_line1_aliennumber')

    expect(prompts(ws)).toHaveLength(1)
  })

  it('stops re-prompting after the hard cap -- does not spin forever even at the reduced rate', async () => {
    const ws = await connected()

    // CONFIRM_LIMIT=2, REPROMPT_CAP=3 -> a re-prompt every 2 failed confirms, capped
    // at 3 total. 100 failed confirms must still yield exactly 3 prompts, then silence.
    for (let i = 0; i < 100; i++) {
      fireConfirm(ws, 'p1_line1_aliennumber')
    }

    expect(prompts(ws)).toHaveLength(3)
  })

  it('a successful confirm (field has a value) does NOT re-prompt and clears tracking', async () => {
    const ws = await connected()

    // One failed confirm arms the counter...
    fireConfirm(ws, 'p1_line1_aliennumber')
    // ...then the value lands and the confirm takes.
    fireFieldUpdate(ws, 'A123456789')
    fireConfirm(ws, 'p1_line1_aliennumber')
    // A later confirm of the now-filled field still must not re-prompt.
    fireConfirm(ws, 'p1_line1_aliennumber')

    expect(prompts(ws)).toHaveLength(0)
  })
})

describe('WebFormConnection synchronous confirm ack (bd polyglot-pdf-wpw.2)', () => {
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

  async function connected(): Promise<MockWebSocket> {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    return ws
  }

  it('acks recorded:false + reason no_value when confirming an empty field', async () => {
    const ws = await connected()

    fireConfirm(ws, 'p1_line1_aliennumber', 'req-empty-1')

    const acks = confirmAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].request_id).toBe('req-empty-1')
    expect(acks[0].recorded).toBe(false)
    expect(acks[0].reason).toBe('no_value')
  })

  it('acks recorded:true (no reason) when the field has a usable value', async () => {
    const ws = await connected()

    fireFieldUpdate(ws, 'A123456789')
    fireConfirm(ws, 'p1_line1_aliennumber', 'req-ok-1')

    const acks = confirmAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].request_id).toBe('req-ok-1')
    expect(acks[0].recorded).toBe(true)
    expect(acks[0].reason).toBeUndefined()
  })

  it('sends no ack for a legacy fire-and-forget confirm_field (no request_id)', async () => {
    const ws = await connected()

    fireFieldUpdate(ws, 'A123456789')
    fireConfirm(ws, 'p1_line1_aliennumber') // no request_id -> nothing to ack

    expect(confirmAcks(ws)).toHaveLength(0)
  })
})
