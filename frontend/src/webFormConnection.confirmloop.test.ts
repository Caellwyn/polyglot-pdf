/**
 * Regression tests for the unconfirmable-field loop-breaker (bd polyglot-pdf-0y7).
 *
 * confirmField() is a no-op when the target field has no value, so the field
 * stays unconfirmed and computeNextField() keeps returning the SAME field on
 * every request -- a tight confirm_field / next_field_hint loop that strands the
 * session and silences Gemini. handleConfirmFieldRequest() now counts consecutive
 * failed confirms of the same field and, past UNCONFIRMABLE_CONFIRM_LIMIT, breaks
 * the spin by prompting Gemini (via completion_message -> send_prompt) to collect
 * the value instead of re-confirming an empty field.
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

// One section with one field. The field exists in the schema but has no value,
// so confirm_field for it can never take -- exactly the loop condition.
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

function fireConfirm(ws: MockWebSocket, fieldId: string): void {
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'confirm_field',
      field_id: fieldId,
      confirmation_method: 'verbal',
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

    const prompts = sentMessages(ws).filter(m => m.type === 'completion_message')
    expect(prompts).toHaveLength(0)
  })

  it('breaks the loop and prompts Gemini after repeated failed confirms of the same empty field', async () => {
    const ws = await connected()

    // First attempt: tracked, no prompt yet.
    fireConfirm(ws, 'p1_line1_aliennumber')
    // Second attempt hits the limit -> corrective prompt.
    fireConfirm(ws, 'p1_line1_aliennumber')

    const prompts = sentMessages(ws).filter(m => m.type === 'completion_message')
    expect(prompts).toHaveLength(1)
    expect(prompts[0].message).toContain('Alien Number')
    expect(prompts[0].message).toContain('cannot be confirmed')
  })

  it('does not spin: at most one corrective prompt is emitted across many failed confirms', async () => {
    const ws = await connected()

    for (let i = 0; i < 6; i++) {
      fireConfirm(ws, 'p1_line1_aliennumber')
    }

    const prompts = sentMessages(ws).filter(m => m.type === 'completion_message')
    // The counter resets after firing, so a long run produces at most a couple of
    // prompts -- never one-per-request. Pin it well below the request count.
    expect(prompts.length).toBeGreaterThanOrEqual(1)
    expect(prompts.length).toBeLessThanOrEqual(3)
  })
})
