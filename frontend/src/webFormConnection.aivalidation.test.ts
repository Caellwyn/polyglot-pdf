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

// Checkbox-GROUP enum validation must run even though NO shipped form-kit sets
// group_kind (bd polyglot-pdf-5jvn). Before the fix, isStringEnumField's checkbox
// branch required group_kind === "checkbox", which the real i-90 p3_race field
// never sets (it is type:"checkbox" with a plain options array) -- so an
// AI-invented race option skipped validateOptionMembership entirely, landed as
// confirmed-pending, and was only silently dropped at PDF-fill time. The fix
// aligns isStringEnumField's checkbox-group detection to the SAME rule already
// used by canonicalizeAiCheckboxGroupValue and the CheckboxField renderer:
// options.length > 0, not a group_kind requirement.
describe('WebFormConnection checkbox-group enum validation (bd polyglot-pdf-5jvn)', () => {
  // Mirrors the real form-kits/i-90 p3_race field: type "checkbox", an options
  // array, and deliberately NO group_kind.
  const RACE_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'p3_race',
        name: 'Race (Select all applicable)',
        spoken_name: 'race',
        type: 'checkbox',
        options: [
          { value: 'P3_checkbox7_White[0]', label: 'White' },
          { value: 'P3_checkbox7_Asian[0]', label: 'Asian' },
          { value: 'P3_checkbox7_Black[0]', label: 'Black or African American' },
        ],
      },
    ],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: ['p3_race'] }],
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

  it('rejects an AI-invented option on a real shipped checkbox-group field (no group_kind)', async () => {
    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(RACE_SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    // Keyed by field id ('p3_race') -- handleFieldUpdate matches on field.name
    // OR field.id, and this schema's `name` is the display label, not 'race'.
    fireFieldUpdate(ws, { p3_race: 'P3_checkbox7_MadeUp[0]' })

    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).not.toContain('p3_race')

    const completions = sentMessages(ws).filter(m => m.type === 'completion_message')
    expect(completions).toHaveLength(1)
  })

  it('accepts a VALID p3_race option', async () => {
    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(RACE_SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    fireFieldUpdate(ws, { p3_race: 'P3_checkbox7_White[0]' })

    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).toContain('p3_race')
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

// An OPTIONAL checkbox group filled with [] (the user selected none) must be a
// CONFIRMABLE end state, not a deadlock (fresh-eyes PR #145 round 5). A round-4
// change briefly made confirm_field reject [] as "no usable value"; combined with
// computeNextField counting [] as a value, that stranded the form -- the field was
// re-offered forever while confirm refused it. validateField treats [] as empty
// (so a REQUIRED group's [] is caught at the apply gate), but an OPTIONAL group's
// [] is valid and must confirm.
describe('WebFormConnection optional checkbox group [] is confirmable, not stranded (bd polyglot-pdf-wpw.3)', () => {
  const GROUP_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'concerns[]',
        name: 'concerns',
        spoken_name: 'Concerns',
        type: 'checkbox_group',
        // optional: no validation.required
        options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
      },
    ],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: ['concerns[]'] }],
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

  function confirmAcks(ws: MockWebSocket): any[] {
    return ws.send.mock.calls
      .map((c: any[]) => c[0])
      .filter((a: any) => typeof a === 'string')
      .map((s: string) => JSON.parse(s))
      .filter((m: any) => m.type === 'confirm_field_response')
  }

  it('confirms an optional checkbox group whose value is [] (no deadlock)', async () => {
    const conn = new WebFormConnection(GROUP_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // Store [] for the optional group (the AI fill path -- valid, lands).
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { 'concerns[]': [] } }) })

    // Confirm it -- must be RECORDED (true), not refused as "no usable value".
    ws.onmessage?.({
      data: JSON.stringify({
        type: 'confirm_field',
        field_id: 'concerns[]',
        confirmation_method: 'verbal',
        request_id: 'req-empty-group',
      }),
    })

    const acks = confirmAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(true)
  })
})

// --- bd polyglot-pdf-z6xs: locked-field rejects must reach the model -------
// When AI tries to fill a hidden/locked field, the FE was sending a
// 'dependency_error' WS message which has NO backend handler -- the reason
// silently disappeared. The fix routes the message through 'completion_message'
// (the same in-band channel used for validation rejects), so Gemini actually
// receives the explanation and can stop re-attempting the locked field.

describe('WebFormConnection locked-field rejection (bd polyglot-pdf-z6xs)', () => {
  const CONDITIONAL_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'spouse_name',
        name: 'spouseName',
        spoken_name: 'Spouse Name',
        type: 'text',
        hidden: true,  // locked: not visible until a condition is met
      },
      {
        id: 'first_name',
        name: 'firstName',
        spoken_name: 'First Name',
        type: 'text',
      },
    ],
    sections: [
      { id: 's1', label: 'S1', order: 1, fields: ['spouse_name', 'first_name'] },
    ],
  } as unknown as FormSchema

  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error
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

  it('sends a completion_message (not dependency_error) when AI targets a locked field', async () => {
    const conn = new WebFormConnection(CONDITIONAL_SCHEMA, {})
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // AI tries to fill the hidden spouse_name field
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { spouseName: 'Jordan' } }) })

    const sent = ws.send.mock.calls
      .map((c: any[]) => c[0])
      .filter((a: any) => typeof a === 'string')
      .map((s: string) => JSON.parse(s))

    // Must send completion_message so the backend forwards it to Gemini
    const completions = sent.filter((m: any) => m.type === 'completion_message')
    expect(completions).toHaveLength(1)
    expect(completions[0].message).toContain('Spouse Name')

    // Must NOT send the dead dependency_error type
    const depErrors = sent.filter((m: any) => m.type === 'dependency_error')
    expect(depErrors).toHaveLength(0)
  })

  it('does not send completion_message when the locked field is not targeted', async () => {
    const conn = new WebFormConnection(CONDITIONAL_SCHEMA, {})
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // AI fills the visible field -- no locked-field message should fire
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { firstName: 'Alex' } }) })

    const sent = ws.send.mock.calls
      .map((c: any[]) => c[0])
      .filter((a: any) => typeof a === 'string')
      .map((s: string) => JSON.parse(s))

    const completions = sent.filter((m: any) => m.type === 'completion_message')
    expect(completions).toHaveLength(0)
  })
})

// --- bd polyglot-pdf-34wc: read_only locked-field message names field once ---
// A read_only field is locked (the AI must not write it). Two bugs were latent:
// (1) the locked-field gate checked only hidden + show_if visibility, so a
//     VISIBLE read_only field slipped through to the apply path instead of being
//     reported back to the model; and
// (2) the read_only lockedReason restated the field name, which -- composed with
//     the "Cannot update '<name>': " prefix -- printed the name TWICE.

describe('WebFormConnection read_only-field rejection (bd polyglot-pdf-34wc)', () => {
  const READONLY_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'case_number',
        name: 'caseNumber',
        spoken_name: 'Case Number',
        type: 'text',
        read_only: true,  // visible but not user-editable
      },
      {
        id: 'first_name',
        name: 'firstName',
        spoken_name: 'First Name',
        type: 'text',
      },
    ],
    sections: [
      { id: 's1', label: 'S1', order: 1, fields: ['case_number', 'first_name'] },
    ],
  } as unknown as FormSchema

  function onMsgSent(ws: MockWebSocket): any[] {
    return ws.send.mock.calls
      .map((c: any[]) => c[0])
      .filter((a: any) => typeof a === 'string')
      .map((s: string) => JSON.parse(s))
  }

  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error
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

  it('routes a read_only field-fill to completion_message and does NOT apply the value', async () => {
    // The gate regression (fresh-eyes finding): a VISIBLE read_only field used to
    // slip past the locked check and reach the apply path. onFieldUpdate fires
    // ONLY for values that actually land, so asserting it was never called proves
    // the value was rejected, not merely that a message was also sent.
    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(READONLY_SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { caseNumber: 'A123' } }) })

    const completions = onMsgSent(ws).filter((m: any) => m.type === 'completion_message')
    expect(completions).toHaveLength(1)
    // No dead dependency_error
    expect(onMsgSent(ws).filter((m: any) => m.type === 'dependency_error')).toHaveLength(0)
    // The read_only value must NOT have landed.
    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).not.toContain('case_number')
  })

  it('names the read_only field EXACTLY ONCE and gives read-only-appropriate guidance (bd 34wc)', async () => {
    const conn = new WebFormConnection(READONLY_SCHEMA, {})
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { caseNumber: 'A123' } }) })

    const completions = onMsgSent(ws).filter((m: any) => m.type === 'completion_message')
    expect(completions).toHaveLength(1)
    const msg: string = completions[0].message
    // The exit criterion: the spoken name appears once, not "Cannot update
    // 'Case Number': The field 'Case Number' is read-only..."
    const occurrences = msg.split('Case Number').length - 1
    expect(occurrences).toBe(1)
    expect(msg).toContain('read-only')
    // A read_only field has NO prerequisite to wait on, so the guidance must not
    // tell the model to complete upstream fields (fresh-eyes finding 1).
    expect(msg).not.toContain('prerequisite')
    expect(msg).toContain('system-managed')
  })

  it('never echoes the rejected read_only value back to the backend (PII-safe)', async () => {
    const conn = new WebFormConnection(READONLY_SCHEMA, {})
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    const secret = 'super-secret-case-id-9999'
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { caseNumber: secret } }) })

    for (const m of onMsgSent(ws)) {
      expect(JSON.stringify(m)).not.toContain(secret)
    }
  })

  // MIXED BATCH (fresh-eyes round 2): one field_update containing BOTH a read_only
  // field and a dependency-gated field. Guidance is per-field, so the read_only
  // field must NOT be told to wait for a prerequisite while the dependency-gated
  // field still is. A single blanket trailing instruction can't satisfy both.
  const MIXED_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'case_number',
        name: 'caseNumber',
        spoken_name: 'Case Number',
        type: 'text',
        read_only: true,
      },
      {
        id: 'marriage_date',
        name: 'marriageDate',
        spoken_name: 'Marriage Date',
        type: 'text',
        // dependency-gated: only shown when maritalStatus === 'married'
        show_if: { field: 'marital_status', operator: 'equals', value: 'married' },
      },
      {
        id: 'marital_status',
        name: 'maritalStatus',
        spoken_name: 'Marital Status',
        type: 'text',
      },
    ],
    sections: [
      { id: 's1', label: 'S1', order: 1, fields: ['case_number', 'marriage_date', 'marital_status'] },
    ],
  } as unknown as FormSchema

  it('gives each field its own lock-kind guidance in a mixed batch (read_only + dependency)', async () => {
    const conn = new WebFormConnection(MIXED_SCHEMA, {})
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()

    // maritalStatus is unset, so marriage_date is dependency-locked; case_number
    // is read_only. Fire both in one update.
    ws.onmessage?.({
      data: JSON.stringify({
        type: 'field_update',
        updates: { caseNumber: 'A123', marriageDate: '2020-01-01' },
      }),
    })

    const completions = onMsgSent(ws).filter((m: any) => m.type === 'completion_message')
    expect(completions).toHaveLength(1)
    const msg: string = completions[0].message

    // Both fields named.
    expect(msg).toContain('Case Number')
    expect(msg).toContain('Marriage Date')

    // Split into per-field sentences on "Cannot update" so each field's guidance
    // can be checked in isolation.
    const caseSentence = msg
      .split('Cannot update')
      .find(s => s.includes('Case Number')) || ''
    const marriageSentence = msg
      .split('Cannot update')
      .find(s => s.includes('Marriage Date')) || ''

    // The read_only field is permanent/system-managed -- and must NOT be told to
    // wait for a prerequisite (it has none).
    expect(caseSentence).toContain('system-managed')
    expect(caseSentence).not.toContain('Marital Status')
    expect(caseSentence).not.toContain('not updated; do not retry')

    // The dependency-gated field gets the specific prerequisite instruction
    // (names the trigger field) and the don't-retry-yet directive -- and must NOT
    // be mislabeled system-managed.
    expect(marriageSentence).toContain('Marital Status')
    expect(marriageSentence).not.toContain('system-managed')
  })
})

// --- bd polyglot-pdf-38p0y: a read_only field that UNLOCKS when shown ---------
// The unit tests in schema-forms/utils/readonlyUnlock.test.ts pin the three gate
// FUNCTIONS. This suite drives the REAL WebFormConnection update path, because a
// bug in the wiring between updateField and isFieldReadOnly would leave every one
// of those unit tests green while the model is still refused -- they call the gate
// directly and never touch the code that decides WHETHER to call it.
//
// Measured limit, so the next reader does not over-trust this: dropping the
// `schema.fields` argument at the call site does NOT redden these, because
// evaluateAtomicCondition currently accepts `fields` without ever dereferencing
// it. That argument is inert today and is passed for correctness under a future
// evaluator that does use it, NOT because anything here would catch its loss.
//
// The shape is the i-90's mail_unit_number: read_only, shown+required the moment
// a mailing unit TYPE is picked, and declaring flip_readonly_bit -- which the PDF
// filler and the UI both honor. SYNTHETIC on purpose: no git-tracked kit ships a
// flip_readonly_bit field (w7 and f1040 both measure zero), so a kit-reading test
// would pass locally and SKIP in CI (CLAUDE.md scar #10).
describe('WebFormConnection honors flip_readonly_bit (bd polyglot-pdf-38p0y)', () => {
  const UNLOCK_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'mail_unit_type',
        name: 'mailUnitType',
        spoken_name: 'Mailing Unit Type',
        type: 'text',
      },
      {
        id: 'mail_unit_number',
        name: 'mailUnitNumber',
        spoken_name: 'Mailing Unit Number',
        type: 'text',
        read_only: true,
        show_if: { field: 'mail_unit_type', operator: 'is_not_empty' },
        conditional_behavior: { unlock_method: 'flip_readonly_bit' },
      },
    ],
    sections: [
      { id: 's1', label: 'S1', order: 1, fields: ['mail_unit_type', 'mail_unit_number'] },
    ],
  } as unknown as FormSchema

  function sent(ws: MockWebSocket): any[] {
    return ws.send.mock.calls
      .map((c: any[]) => c[0])
      .filter((a: any) => typeof a === 'string')
      .map((s: string) => JSON.parse(s))
  }

  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error
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

  it('THE BUG: once the trigger is filled, the AI write to the unlocked field LANDS', async () => {
    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(UNLOCK_SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()

    // The user picks a mailing unit type -- this SHOWS mail_unit_number and,
    // because it declares flip_readonly_bit, unlocks it.
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { mailUnitType: 'Apt' } }) })
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { mailUnitNumber: '4B' } }) })

    // The value must actually LAND -- onFieldUpdate fires only for applied values.
    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).toContain('mail_unit_number')
    // ...and the model must NOT be told to stop trying.
    const msgs = sent(ws).map((m: any) => JSON.stringify(m)).join(' ')
    expect(msgs).not.toContain('system-managed')
  })

  it('...but BEFORE the trigger is filled it is still refused (the unlock has not fired)', async () => {
    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(UNLOCK_SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { mailUnitNumber: '4B' } }) })

    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).not.toContain('mail_unit_number')
  })

  // The SECOND field exit criterion 1 names. Not a duplicate of the above: the
  // trigger is a CHECKBOX read with is_checked (vs a text field read with
  // is_not_empty) and the target is a textarea. Driven through the real
  // connection because a unit test on the gate functions cannot see the call
  // site -- which is the whole reason this block exists (fresh-eyes round 5).
  const ACCOMMODATION_SCHEMA: FormSchema = {
    source: 'web',
    fields: [
      {
        id: 'accommodation_other',
        name: 'accommodationOther',
        spoken_name: 'Other Accommodation',
        type: 'checkbox',
      },
      {
        id: 'accommodation_other_detail',
        name: 'accommodationOtherDetail',
        spoken_name: 'Accommodation Detail',
        type: 'textarea',
        read_only: true,
        show_if: { field: 'accommodation_other', operator: 'is_checked' },
        conditional_behavior: { unlock_method: 'flip_readonly_bit' },
      },
    ],
    sections: [
      {
        id: 's1', label: 'S1', order: 1,
        fields: ['accommodation_other', 'accommodation_other_detail'],
      },
    ],
  } as unknown as FormSchema

  it('accommodation_other_detail: the write LANDS once the box is checked', async () => {
    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(ACCOMMODATION_SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { accommodationOther: true } }) })
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { accommodationOtherDetail: 'wheelchair access' } }) })

    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).toContain('accommodation_other_detail')
    expect(sent(ws).map((m: any) => JSON.stringify(m)).join(' ')).not.toContain('system-managed')
  })

  it('accommodation_other_detail: still refused while the box is unchecked', async () => {
    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(ACCOMMODATION_SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { accommodationOtherDetail: 'wheelchair access' } }) })

    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).not.toContain('accommodation_other_detail')
  })

  it('a read_only field with NO unlock is still refused however it is shown', async () => {
    // Guards the other direction: the fix must not have opened every read_only
    // field. Same schema shape, minus the unlock declaration.
    const NO_UNLOCK = JSON.parse(JSON.stringify(UNLOCK_SCHEMA)) as FormSchema
    delete (NO_UNLOCK.fields[1] as any).conditional_behavior

    const onFieldUpdate = vi.fn()
    const conn = new WebFormConnection(NO_UNLOCK, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { mailUnitType: 'Apt' } }) })
    ws.send.mockClear()
    onFieldUpdate.mockClear()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { mailUnitNumber: '4B' } }) })

    const applied = onFieldUpdate.mock.calls.flatMap(
      (c: any[]) => (c[0] as Array<{ fieldId: string }>).map(u => u.fieldId)
    )
    expect(applied).not.toContain('mail_unit_number')
    expect(sent(ws).map((m: any) => JSON.stringify(m)).join(' ')).toContain('system-managed')
  })
})
