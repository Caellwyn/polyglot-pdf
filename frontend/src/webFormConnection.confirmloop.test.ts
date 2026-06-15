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

  it('keeps a REQUIRED field with an empty value unconfirmable', async () => {
    // For a REQUIRED field an empty update is rejected at the apply gate
    // (wpw.3), so an entry-exists-but-empty state cannot land -- which is why
    // the optional carve-out in hasUsableValue (bd polyglot-pdf-w3ic) is safe.
    // The confirm of the still-valueless field must keep tripping the
    // loop-breaker.
    const requiredSchema = {
      ...SCHEMA,
      fields: [{ ...SCHEMA.fields[0], validation: { required: true } }],
    } as unknown as FormSchema
    const conn = new WebFormConnection(requiredSchema)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    fireFieldUpdate(ws, '')
    ws.send.mockClear() // drop the apply-gate rejection prompt; we assert the loop-breaker's

    fireConfirm(ws, 'p1_line1_aliennumber')
    fireConfirm(ws, 'p1_line1_aliennumber')

    expect(prompts(ws)).toHaveLength(1)
  })

  it('confirms an empty OPTIONAL field instead of looping (bd polyglot-pdf-w3ic)', async () => {
    const ws = await connected()

    // The schema field carries no required flag; an intentionally blank value
    // ("I have no middle name") is a confirmable end state -- the unconfirmable
    // re-prompt must NOT fire.
    fireFieldUpdate(ws, '')
    fireConfirm(ws, 'p1_line1_aliennumber')
    fireConfirm(ws, 'p1_line1_aliennumber')

    expect(prompts(ws)).toHaveLength(0)
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

// Two empty fields so the model can ALTERNATE confirm_field across them. Before
// bd polyglot-pdf-r2hy the per-field counter reset on every switch, so the cap
// never engaged and the loop re-prompted forever; the session-wide cap bounds it.
const TWO_FIELD_SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'f_a', name: 'fieldA', spoken_name: 'Field A', type: 'text' },
    { id: 'f_b', name: 'fieldB', spoken_name: 'Field B', type: 'text' },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f_a', 'f_b'] }],
} as unknown as FormSchema

describe('WebFormConnection cross-field confirm-spin session cap (bd polyglot-pdf-r2hy)', () => {
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

  async function connectedTwoField(): Promise<MockWebSocket> {
    const conn = new WebFormConnection(TWO_FIELD_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    return ws
  }

  it('bounds the total re-prompts when the model spins confirm_field across DIFFERENT empty fields', async () => {
    const ws = await connectedTwoField()

    // The per-field gate fires a re-prompt every CONFIRM_LIMIT(=2) CONSECUTIVE
    // confirms of the SAME field, capped per-field at REPROMPT_CAP(=3). A model
    // that confirms a field twice (-> prompt), switches to the other field twice
    // (-> prompt), and keeps alternating in PAIRS re-arms the per-field counter on
    // every switch, so WITHOUT the session cap each new field would prompt up to
    // 3 more times and the total would grow without bound. The session-wide cap
    // (UNCONFIRMABLE_SESSION_CAP=6) bounds the TOTAL re-prompts regardless of how
    // many fields the spin touches.
    const ids = ['f_a', 'f_b']
    for (let cycle = 0; cycle < 50; cycle++) {
      const id = ids[cycle % 2]
      // two consecutive confirms of the same field -> trips the per-field gate
      fireConfirm(ws, id)
      fireConfirm(ws, id)
    }

    const p = prompts(ws)
    // Bounded by the session cap, NOT ~50. A regression to per-field-only would
    // produce one prompt-burst per field-switch (dozens here).
    expect(p.length).toBeGreaterThan(0)
    expect(p.length).toBeLessThanOrEqual(6)
  })

  it('a successful confirm of the stuck field restores the session re-prompt budget', async () => {
    const ws = await connectedTwoField()

    // FULLY EXHAUST the session cap (=6) with a paired cross-field spin, so the
    // session counter is at the ceiling and NO field can earn another re-prompt.
    // (Using a single field would only spend 3 of 6 via its per-field cap, leaving
    // budget that would let B prompt even WITHOUT a reset -- a vacuous test. The
    // paired spin is what actually drives the session counter to 6.)
    const ids = ['f_a', 'f_b']
    for (let cycle = 0; cycle < 50; cycle++) {
      const id = ids[cycle % 2]
      fireConfirm(ws, id)
      fireConfirm(ws, id)
    }
    const exhausted = prompts(ws).length
    expect(exhausted).toBe(6) // session cap reached -- no more prompts possible

    // Confirm that the cap is truly spent: more spinning yields ZERO new prompts.
    for (let i = 0; i < 10; i++) fireConfirm(ws, 'f_a')
    expect(prompts(ws).length).toBe(exhausted)

    // Now field A finally gets a value and confirms -- genuine progress on the
    // stuck field calls resetUnconfirmableTracking(), which ZEROES the session
    // counter (not merely leaves room). The field_update is keyed by field NAME.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { fieldA: 'A123456789' } }),
    })
    fireConfirm(ws, 'f_a') // takes -> resetUnconfirmableTracking()

    // With the counter reset to zero, a fresh empty field B can earn re-prompts
    // again. This is ONLY possible if the stuck-field confirm reset the SESSION
    // counter -- if it had merely left room, the cap was already at 6 and B would
    // stay silent.
    for (let i = 0; i < 4; i++) fireConfirm(ws, 'f_b')
    expect(prompts(ws).length).toBeGreaterThan(exhausted)
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

  it('does NOT set section_complete when confirming the only field of the only section (form complete, not a section boundary)', async () => {
    const ws = await connected()

    fireFieldUpdate(ws, 'A123456789')
    fireConfirm(ws, 'p1_line1_aliennumber', 'req-formdone')

    const acks = confirmAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(true)
    // No NEXT section -> the form is complete, not a section boundary. The
    // section_complete flag is for "advancing to another section", so it must be
    // absent here (bd polyglot-pdf-njvh).
    expect(acks[0].section_complete).toBeUndefined()
  })
})

// Two sections, each one field, so confirming the LAST field of section 1 has a
// section 2 to advance to -- the exact section boundary the njvh race fires on.
const TWO_SECTION_SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'f_s1', name: 'fieldS1', spoken_name: 'Field S1', type: 'text' },
    { id: 'f_s2', name: 'fieldS2', spoken_name: 'Field S2', type: 'text' },
  ],
  sections: [
    { id: 's1', label: 'S1', order: 1, fields: ['f_s1'] },
    { id: 's2', label: 'S2', order: 2, fields: ['f_s2'] },
  ],
} as unknown as FormSchema

describe('WebFormConnection confirm at a section boundary (bd polyglot-pdf-njvh)', () => {
  // Holds the live connection so afterEach can tear it down. Confirming the last
  // field of section 1 triggers an auto-switchToSection whose section_switched ack
  // never arrives in this mock, so it arms a real ~15s watchdog setTimeout;
  // disconnect() runs clearSectionSwitchWatchdog so it can't fire into a later test
  // (fresh-eyes test-isolation note).
  let conn: WebFormConnection | null = null

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

  afterEach(() => {
    conn?.disconnect()
    conn = null
  })

  async function connectedTwoSection(): Promise<MockWebSocket> {
    conn = new WebFormConnection(TWO_SECTION_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    return ws
  }

  function fillS1(ws: MockWebSocket, value: string): void {
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { fieldS1: value } }) })
  }

  it('acks section_complete:true when confirming the last field of section 1 (a NEXT section exists)', async () => {
    const ws = await connectedTwoSection()

    fillS1(ws, 'value-one')
    fireConfirm(ws, 'f_s1', 'req-boundary')

    // Exactly one ack for the boundary confirm -- a double-fire would be a bug.
    const acks = confirmAcks(ws)
    expect(acks).toHaveLength(1)
    const boundaryAck = acks[0]
    expect(boundaryAck.request_id).toBe('req-boundary')
    expect(boundaryAck.recorded).toBe(true)
    // Section 1 is now fully confirmed AND section 2 exists -> a real section
    // boundary. The backend reads this to skip the racing next-field-hint request.
    expect(boundaryAck.section_complete).toBe(true)
  })
})
