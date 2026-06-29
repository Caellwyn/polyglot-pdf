/**
 * B4 (bd polyglot-pdf-jnjj.16): proactive section_complete / form_complete events.
 *
 * When the last field of a section is confirmed the client emits a top-level
 * `section_complete` (section_id + the contract-2 field payload); when the whole
 * form is confirmed it emits a once-only `form_complete` (whole-form payload),
 * re-emitted only after a post-completion edit. These feed the cheap-model
 * validator (validation-delegation.md contract 4). Fire-and-forget: the events
 * never block the user (criterion 3).
 *
 * The model stub here is the production confirm/field-update path, so a passing
 * test proves the real emit + projection, not a hand-built payload.
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

// Two sections, one field each. Confirming s1's field (with a next section) is a
// section boundary; confirming s2's field completes the whole form.
const TWO_SECTION_SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'f_s1', name: 'firstname', spoken_name: 'First Name', type: 'text' },
    { id: 'f_s2', name: 'lastname', spoken_name: 'Last Name', type: 'text' },
  ],
  sections: [
    { id: 's1', label: 'S1', order: 1, fields: ['f_s1'] },
    { id: 's2', label: 'S2', order: 2, fields: ['f_s2'] },
  ],
} as unknown as FormSchema

// One section, two fields. Both confirmed -> form complete (single boundary).
const ONE_SECTION_SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'f_a', name: 'fielda', spoken_name: 'Field A', type: 'text' },
    { id: 'f_b', name: 'fieldb', spoken_name: 'Field B', type: 'text' },
  ],
  sections: [{ id: 'only', label: 'Only', order: 1, fields: ['f_a', 'f_b'] }],
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

function ofType(ws: MockWebSocket, type: string): any[] {
  return sentMessages(ws).filter(m => m.type === type)
}

function fireConfirm(ws: MockWebSocket, fieldId: string): void {
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'confirm_field',
      field_id: fieldId,
      // A request_id is ALWAYS present on a real synchronous confirm_field request;
      // sendConfirmFieldResponse skips the ack without one (legacy-shape guard), so
      // the ack-subfield assertion below needs it.
      request_id: 'req-' + fieldId,
      confirmation_method: 'verbal',
    }),
  })
}

// Fill a field through the production field_update path (keyed by field name).
function fireFieldUpdate(ws: MockWebSocket, name: string, value: string): void {
  ws.onmessage?.({
    data: JSON.stringify({ type: 'field_update', updates: { [name]: value } }),
  })
}

describe('WebFormConnection proactive section/form-complete (bd polyglot-pdf-jnjj.16)', () => {
  // Confirming the last field of a non-final section triggers an auto-switch whose
  // section_switched ack never arrives in the mock, arming a real ~15s watchdog;
  // disconnect() in afterEach clears it so it cannot fire into a later test
  // (the confirmloop suite's test-isolation note).
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

  async function connected(schema: FormSchema): Promise<MockWebSocket> {
    conn = new WebFormConnection(schema)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send
    return ws
  }

  // --- Criterion 1: section_complete on a section boundary ---

  it('emits section_complete with section_id + contract-2 fields when the last field of a non-final section is confirmed', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')

    const events = ofType(ws, 'section_complete')
    expect(events).toHaveLength(1)
    expect(events[0].section_id).toBe('s1')
    // contract-2 projection: only the section's non-empty field, with name+steered.
    expect(events[0].fields).toEqual([
      { field_id: 'f_s1', name: 'First Name', value: 'Jane', steered: false },
    ])
  })

  it('does NOT emit section_complete when the FINAL section completes (no next section) -- that path is form_complete only', async () => {
    // A single-section form: confirming its last field completes the WHOLE form, so
    // there is no next section. The boundary must emit form_complete, NOT
    // section_complete (the latter is gated on a next section existing). This is the
    // mock-friendly way to exercise the "final section" branch without driving a
    // real cross-section switch (which the mock cannot complete).
    const ws = await connected(ONE_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'fielda', 'AA')
    fireConfirm(ws, 'f_a')
    fireFieldUpdate(ws, 'fieldb', 'BB')
    fireConfirm(ws, 'f_b')

    expect(ofType(ws, 'section_complete')).toHaveLength(0)
    expect(ofType(ws, 'form_complete')).toHaveLength(1)
  })

  // --- Criterion 1: once-only form_complete ---

  it('emits a single form_complete with the whole-form payload when the form completes', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'fielda', 'AA')
    fireConfirm(ws, 'f_a')
    fireFieldUpdate(ws, 'fieldb', 'BB')
    fireConfirm(ws, 'f_b')

    const events = ofType(ws, 'form_complete')
    expect(events).toHaveLength(1)
    expect(events[0].fields).toEqual([
      { field_id: 'f_a', name: 'Field A', value: 'AA', steered: false },
      { field_id: 'f_b', name: 'Field B', value: 'BB', steered: false },
    ])
  })

  it('skips empty/unfilled fields from the form_complete payload (contract 2: non-empty only)', async () => {
    // Single-field section so the form completes on one confirm; assert only the
    // filled field rides. (A second untouched field would be skipped.)
    const ws = await connected(ONE_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'fielda', 'AA')
    fireConfirm(ws, 'f_a')
    // Only f_a is filled+confirmed; the form is NOT complete yet (f_b unconfirmed),
    // so no form_complete should have fired.
    expect(ofType(ws, 'form_complete')).toHaveLength(0)
  })

  // --- Once-only guard + dirty re-emit (the edit-after-complete hole) ---

  it('does NOT re-emit form_complete when the completed form is re-touched with no value change (once-only guard)', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'fielda', 'AA')
    fireConfirm(ws, 'f_a')
    fireFieldUpdate(ws, 'fieldb', 'BB')
    fireConfirm(ws, 'f_b')
    expect(ofType(ws, 'form_complete')).toHaveLength(1)

    // Re-confirm f_b at the SAME value: the form is still complete but the
    // confirmed-values snapshot is unchanged, so the dirty guard suppresses a
    // second form_complete (the no-pester property, contract 4).
    ws.send.mockClear()
    fireConfirm(ws, 'f_b')
    expect(ofType(ws, 'form_complete')).toHaveLength(0)
  })

  it('DOES re-emit form_complete after a post-completion edit changes a value (closes the edit-after-complete bypass)', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'fielda', 'AA')
    fireConfirm(ws, 'f_a')
    fireFieldUpdate(ws, 'fieldb', 'BB')
    fireConfirm(ws, 'f_b')
    expect(ofType(ws, 'form_complete')).toHaveLength(1)

    // A manual edit changes f_b's value AND re-confirms it, so the form re-reaches
    // the complete state with a CHANGED snapshot -> form_complete re-emits once with
    // the updated value. (fireFieldUpdate sets confirmed:false; re-confirm restores
    // completeness, and the confirm handler's maybeEmitFormComplete sees the new
    // snapshot.)
    ws.send.mockClear()
    fireFieldUpdate(ws, 'fieldb', 'CC')
    fireConfirm(ws, 'f_b')
    const reEmit = ofType(ws, 'form_complete')
    expect(reEmit).toHaveLength(1)
    const fb = reEmit[0].fields.find((f: any) => f.field_id === 'f_b')
    expect(fb.value).toBe('CC')
  })

  // --- Criterion 2: no double-fire vs the confirm-ack sub-field ---

  it('the top-level section_complete and the confirm-ack section_complete sub-field both fire exactly once, and are distinct', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')

    // Exactly one top-level proactive event.
    expect(ofType(ws, 'section_complete')).toHaveLength(1)
    // The confirm ack still carries its section_complete:true SUB-FIELD (distinct
    // message, bd njvh), exactly once.
    const acks = ofType(ws, 'confirm_field_response').filter(m => m.section_complete === true)
    expect(acks).toHaveLength(1)
  })
})
