/**
 * Regression tests for client-side validation of AI-applied values
 * (bd polyglot-pdf-wpw.3 / WS-E3).
 *
 * The client owns all field state (the stateless-backend invariant), so an
 * AI-supplied value that violates its schema (a non-existent enum option, a
 * malformed format, etc.) must NEVER land. handleFieldUpdate() now runs
 * validateField on every applied value: a reject skips the apply and routes a
 * corrective, PII-free completion_message back to the model so it re-asks the
 * user in-band. Those prompts are rate-limited per field and capped in total
 * (mirroring the 0y7 unconfirmable loop-breaker) so a model that keeps sending
 * the same bad value cannot spin the session.
 *
 * Applied-vs-rejected is asserted via the onFieldUpdate callback (which fires
 * only for values that actually land) rather than sessionStorage, since the AI
 * fill path holds values in in-memory state.
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

// One section, two fields:
//  - a select with a fixed option set (enum validation)
//  - a plain text field (the control: any value is valid)
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
      id: 'first_name',
      name: 'firstName',
      spoken_name: 'First Name',
      type: 'text',
    },
  ],
  sections: [
    { id: 's1', label: 'S1', order: 1, fields: ['marital_status', 'first_name'] },
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

function prompts(ws: MockWebSocket): any[] {
  return sentMessages(ws).filter(m => m.type === 'completion_message')
}

// Drive an AI field fill through the production field_update path (keyed by
// field name or id), exactly as the backend sends after update_form_fields.
function fireFieldUpdate(ws: MockWebSocket, updates: Record<string, any>): void {
  ws.onmessage?.({
    data: JSON.stringify({ type: 'field_update', updates }),
  })
}

describe('WebFormConnection client-side AI-value validation (bd polyglot-pdf-wpw.3)', () => {
  let onFieldUpdate: ReturnType<typeof vi.fn>

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
    onFieldUpdate = vi.fn()
  })

  async function connect(): Promise<MockWebSocket> {
    const conn = new WebFormConnection(SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send so we only see update-driven sends
    onFieldUpdate.mockClear()
    return ws
  }

  // Field ids that actually landed (onFieldUpdate fires only for applied values).
  function appliedFieldIds(): string[] {
    return onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
  }

  it('applies a valid enum value', async () => {
    const ws = await connect()

    fireFieldUpdate(ws, { maritalStatus: 'married' })

    expect(appliedFieldIds()).toContain('marital_status')
    expect(prompts(ws)).toHaveLength(0)
  })

  it('does NOT apply a value outside the option set, and prompts the model', async () => {
    const ws = await connect()

    fireFieldUpdate(ws, { maritalStatus: 'widowed' })

    // Rejected -> never reported as applied.
    expect(appliedFieldIds()).not.toContain('marital_status')
    // First reject prompts the model in-band.
    const p = prompts(ws)
    expect(p).toHaveLength(1)
    expect(p[0].message).toContain('Marital Status')
  })

  it('never echoes the rejected value in any message sent to the backend (PII-safe)', async () => {
    const ws = await connect()

    const secret = 'totally-made-up-secret-option'
    fireFieldUpdate(ws, { maritalStatus: secret })

    for (const msg of sentMessages(ws)) {
      expect(JSON.stringify(msg)).not.toContain(secret)
    }
  })

  it('passes through any value for a field with no option/validation constraints', async () => {
    const ws = await connect()

    fireFieldUpdate(ws, { firstName: 'Jordan' })

    expect(appliedFieldIds()).toContain('first_name')
    expect(prompts(ws)).toHaveLength(0)
  })

  it('caps corrective prompts so a repeatedly-bad value cannot spin the session', async () => {
    const ws = await connect()

    // REJECT_REPROMPT_CAP = 3: 50 rejects of the same field must yield at most 3
    // prompts, then silence.
    for (let i = 0; i < 50; i++) {
      fireFieldUpdate(ws, { maritalStatus: 'widowed' })
    }

    expect(prompts(ws).length).toBe(3)
    // The bad value still never landed.
    expect(appliedFieldIds()).not.toContain('marital_status')
  })

  it('a subsequent valid value lands and clears the reject streak', async () => {
    const ws = await connect()

    fireFieldUpdate(ws, { maritalStatus: 'widowed' }) // reject (1 prompt)
    fireFieldUpdate(ws, { maritalStatus: 'single' })  // valid -> lands, streak cleared

    expect(appliedFieldIds()).toContain('marital_status')

    // A later bad value is treated as a FRESH streak (prompts again on its first
    // reject), proving the streak reset rather than staying at/above the cap.
    ws.send.mockClear()
    fireFieldUpdate(ws, { maritalStatus: 'widowed' })
    expect(prompts(ws)).toHaveLength(1)
  })
})
