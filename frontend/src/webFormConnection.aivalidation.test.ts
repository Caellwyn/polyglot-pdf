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

// The session-wide cap must stop a model that ALTERNATES invalid values between
// fields (Codex PR #145): each field switch resets the per-field counter, so the
// per-field cap alone would let it prompt forever. The session-wide cap is not
// reset on a field change, so the cross-field spin is bounded.
describe('WebFormConnection AI-value reject session cap (cross-field spin) (bd polyglot-pdf-wpw.3)', () => {
  const TWO_ENUM_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'field_a',
        name: 'fieldA',
        spoken_name: 'Field A',
        type: 'select',
        options: [{ value: 'a1', label: 'A1' }, { value: 'a2', label: 'A2' }],
      },
      {
        id: 'field_b',
        name: 'fieldB',
        spoken_name: 'Field B',
        type: 'select',
        options: [{ value: 'b1', label: 'B1' }, { value: 'b2', label: 'B2' }],
      },
    ],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: ['field_a', 'field_b'] }],
  } as unknown as FormSchema

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

  it('caps total prompts even when the model alternates bad values between two fields', async () => {
    const conn = new WebFormConnection(TWO_ENUM_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // Alternate bad values A, B, A, B, ... 40 times. Without the session cap the
    // per-field counter would reset on every switch and every reject would prompt
    // (~40 prompts). The session cap (6) must bound it.
    for (let i = 0; i < 40; i++) {
      const bad = i % 2 === 0 ? { fieldA: 'bad-a' } : { fieldB: 'bad-b' }
      fireFieldUpdate(ws, bad)
    }

    expect(prompts(ws).length).toBe(6) // VALIDATION_REJECT_SESSION_CAP
  })

  it('restores the prompt budget when the STUCK field itself finally succeeds', async () => {
    const conn = new WebFormConnection(TWO_ENUM_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // Repeatedly reject field A until its budget is spent (per-field cap reached).
    for (let i = 0; i < 10; i++) {
      fireFieldUpdate(ws, { fieldA: 'bad-a' })
    }
    const spent = prompts(ws).length
    expect(spent).toBeGreaterThan(0)

    // Genuine PROGRESS on the STUCK field: A lands a valid value. lastValidationReject
    // is A, so this clears the streak + session cap -- the model fixed the failing thing.
    ws.send.mockClear()
    fireFieldUpdate(ws, { fieldA: 'a1' }) // valid -> lands, budget restored

    // A later bad value gets a fresh corrective prompt again (budget was restored).
    fireFieldUpdate(ws, { fieldA: 'bad-a-again' })
    expect(prompts(ws).length).toBe(1)
  })

  it('does NOT restore the budget on a good value for a DIFFERENT field while another is still failing', async () => {
    // The [bad-A, good-B] alternation must NOT reset the session cap each batch --
    // good-B is not progress on the FAILING field A, and resetting would let the
    // model spin corrective prompts for A forever (fresh-eyes round 4). The cap must
    // hold at the session limit regardless of the interleaved good-B fills.
    const conn = new WebFormConnection(TWO_ENUM_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // 30 batches of "field A bad + field B GOOD". If a different-field success reset
    // A's tracking each batch, A's streak would restart every time and it would
    // prompt on (almost) every batch (~30). Because good-B does NOT reset the streak
    // of the still-failing A, A stays bounded by its OWN per-field cap (3) -- the
    // good-B fills are ignored for A's budget entirely.
    for (let i = 0; i < 30; i++) {
      fireFieldUpdate(ws, { fieldA: 'bad-a' })  // reject A
      fireFieldUpdate(ws, { fieldB: 'b1' })     // valid B (a DIFFERENT field)
    }

    // Bounded at A's per-field reprompt cap (VALIDATION_REJECT_REPROMPT_CAP = 3),
    // NOT ~30 -- proving good-B did not keep resetting A's streak/budget
    // (fresh-eyes round 4).
    expect(prompts(ws).length).toBe(3)
  })
})

// The reject streak must NOT carry across a section switch (fresh-eyes finding on
// PR #145): switchToSection / startSection keep the same socket, so handleOpen's
// reset does not fire -- they reset the validation-reject counters themselves.
//
// In production this is DEFENSE-IN-DEPTH, exactly like the 0y7 unconfirmable reset
// at the same sites: the per-field streak is keyed on field_id, and field ids are
// globally unique per schema (scar tissue #5), so a DIFFERENT field in the next
// section already resets the streak via the field-id change in handleAiValueRejected.
// The cross-section carry-over only bites if the SAME field_id were to recur, which
// the uniqueness invariant forbids. This test deliberately reuses ONE field_id
// across the switch boundary to exercise the reset path directly and remove the
// reliance on that invariant -- mirroring why 0y7 resets here too.
describe('WebFormConnection AI-value reject streak resets on section switch (bd polyglot-pdf-wpw.3)', () => {
  // The SAME option-backed field id appears in both sections (intentionally
  // violating id-uniqueness) so a streak built in s1 would, absent the reset,
  // carry into s2 for that id.
  const SHARED_ID_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'status',
        name: 'status',
        spoken_name: 'Status',
        type: 'select',
        options: [
          { value: 'single', label: 'Single' },
          { value: 'married', label: 'Married' },
        ],
      },
    ],
    sections: [
      { id: 's1', label: 'S1', order: 1, fields: ['status'] },
      { id: 's2', label: 'S2', order: 2, fields: ['status'] },
    ],
  } as unknown as FormSchema

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

  it('clears the per-field cap so the same field id gets a fresh prompt after a switch', async () => {
    const conn = new WebFormConnection(SHARED_ID_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // Exhaust the cap (3 prompts) in section 1 on the shared field's bad value.
    for (let i = 0; i < 10; i++) {
      fireFieldUpdate(ws, { status: 'widowed' })
    }
    expect(prompts(ws)).toHaveLength(3) // cap reached for field id 'status'

    // Switch sections (same socket, so handleOpen does not fire) -- this must reset
    // the per-field reject tracking.
    await conn.switchToSection('s2', 'ws://x')
    ws.send.mockClear()

    // The SAME field id, bad again in the new section, must get a fresh first-reject
    // prompt. Without resetValidationRejectTracking() in switchToSection the cap
    // would still be exhausted for 'status' and this would be 0.
    fireFieldUpdate(ws, { status: 'widowed' })
    expect(prompts(ws)).toHaveLength(1)
  })
})
