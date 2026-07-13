/**
 * B5 (bd polyglot-pdf-jnjj.17): the frontend side of validator steering --
 * the validation_result handler, the section-switch validator gate, and the
 * client-owned `steered` marker (validation-delegation.md contracts 1/2/4).
 *
 * Criteria exercised here:
 *  - clean validation_result -> the PAUSED section switch resumes;
 *  - conflict validation_result -> the switch is HELD (stay in-section) AND the
 *    named fields are marked steered:true in sessionStorage, so the NEXT contract-2
 *    payload carries steered:true (the client half of the max-resteer bound);
 *  - no validation_result within the fail-OPEN window -> the switch proceeds unchecked.
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
    queueMicrotask(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.()
    })
  }
  send = vi.fn()
  close = vi.fn(() => { this.readyState = MockWebSocket.CLOSED })
}

// Two sections, one field each: confirming f_s1 is a section boundary (s2 exists).
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
function fireFieldUpdate(ws: MockWebSocket, name: string, value: string): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { [name]: value } }) })
}
function fireConfirm(ws: MockWebSocket, fieldId: string): void {
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'confirm_field', field_id: fieldId,
      request_id: 'req-' + fieldId, confirmation_method: 'verbal',
    }),
  })
}
function deliverValidationResult(ws: MockWebSocket, conflicts: any[]): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'validation_result', conflicts }) })
}
// W3 (bd polyglot-pdf-pr3i): the backend's drain result -- the conflicts whose steer
// DELIVERED. The client marks these steered + consumes them from the queue.
function deliverDrainResult(ws: MockWebSocket, conflicts: any[]): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'drain_findings_result', conflicts }) })
}

// `flush` lets queued microtasks (the gated proceedSectionSwitch promise chain) run.
const flush = () => new Promise<void>(r => setTimeout(r, 0))

describe('WebFormConnection validator steering + switch-gate (bd polyglot-pdf-jnjj.17)', () => {
  let conn: WebFormConnection | null = null

  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock
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
    vi.useRealTimers()
  })

  async function connected(schema: FormSchema, callbacks: any = {}): Promise<MockWebSocket> {
    conn = new WebFormConnection(schema, callbacks)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    return ws
  }

  // switchToSection() moves the connection to status 'switching_section', so
  // conn.getStatus() === 'switching_section' is the observable "the switch proceeded"
  // signal in the mock (it uses a backend-side reconnect, not a fresh socket).
  it('PAUSES the section switch until a validation_result arrives', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await flush()

    // The section_complete event fired, but the switch is gated -- not switching yet.
    expect(ofType(ws, 'section_complete')).toHaveLength(1)
    expect(conn!.getStatus()).not.toBe('switching_section')
  })

  it('a CLEAN validation_result resumes the paused switch', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await flush()
    expect(conn!.getStatus()).not.toBe('switching_section') // still paused

    deliverValidationResult(ws, [])
    await flush()

    // The switch ran.
    expect(conn!.getStatus()).toBe('switching_section')
  })

  it('a CONFLICT validation_result HOLDS the switch, enqueues + drains, and marks steered on the drain result (W3)', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await flush()

    deliverValidationResult(ws, [
      { field_ids: ['f_s1'], reason: 'looks off', field_names: { f_s1: 'First Name' } },
    ])
    await flush()

    // The switch did NOT proceed (stay in-section for the steer).
    expect(conn!.getStatus()).not.toBe('switching_section')
    // W3: the conflict is REPORT-ONLY -- it was ENQUEUED and a drain_findings emitted;
    // the field is NOT steered yet (that waits for the drain result).
    const drains = ofType(ws, 'drain_findings')
    expect(drains).toHaveLength(1)
    expect(drains[0].conflicts[0].field_ids).toEqual(['f_s1'])
    let state = SchemaFormStateManager.load()!
    expect(state.validatorFindingsQueue).toHaveLength(1)
    expect(state.fieldValues['f_s1'].steered).toBeFalsy()

    // The backend confirms delivery -> NOW mark steered + consume the queue.
    deliverDrainResult(ws, [{ field_ids: ['f_s1'] }])
    await flush()
    state = SchemaFormStateManager.load()!
    expect(state.fieldValues['f_s1'].steered).toBe(true)
    expect(state.validatorFindingsQueue).toHaveLength(0)
  })

  it('keeps the mic LIVE on a conflict-hold, and stops it only when the switch proceeds', async () => {
    // Opus PR #275 deadlock: the audio teardown must NOT run before the gate resolves.
    // On a conflict-hold the user must be able to SPEAK to resolve it, so onStopCapture
    // must not fire; it fires only when the switch actually proceeds (clean/fail-OPEN).
    const onStopCapture = vi.fn()
    const ws = await connected(TWO_SECTION_SCHEMA, { onStopCapture })
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await flush()

    // Conflict -> hold in-section -> mic must still be live.
    deliverValidationResult(ws, [{ field_ids: ['f_s1'], reason: 'verify this' }])
    await flush()
    expect(conn!.getStatus()).not.toBe('switching_section')
    expect(onStopCapture).not.toHaveBeenCalled()

    // Now the user re-confirms and the verdict is clean -> the switch proceeds and the
    // mic stops as part of the switch.
    fireConfirm(ws, 'f_s1')
    await flush()
    deliverValidationResult(ws, [])
    await flush()
    expect(conn!.getStatus()).toBe('switching_section')
    expect(onStopCapture).toHaveBeenCalled()
  })

  it('a steered field rides the NEXT validator payload as steered:true', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await flush()
    deliverValidationResult(ws, [{ field_ids: ['f_s1'], reason: 'x', field_names: { f_s1: 'First Name' } }])
    await flush()
    // W3: the steer marker lands on the DRAIN RESULT, not the report-only result.
    deliverDrainResult(ws, [{ field_ids: ['f_s1'] }])
    await flush()

    // Re-confirm f_s1 -> section_complete re-emits; its payload now carries steered:true.
    ws.send.mockClear()
    fireConfirm(ws, 'f_s1')
    await flush()
    const events = ofType(ws, 'section_complete')
    expect(events.length).toBeGreaterThanOrEqual(1)
    const f = events[events.length - 1].fields.find((x: any) => x.field_id === 'f_s1')
    expect(f.steered).toBe(true)
  })

  it('FAILS OPEN: the switch proceeds if no validation_result arrives within the window', async () => {
    vi.useFakeTimers()
    conn = new WebFormConnection(TWO_SECTION_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    await vi.advanceTimersByTimeAsync(1) // let the queued onopen/handshake run
    const ws = lastWs()
    ws.send.mockClear()

    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await vi.advanceTimersByTimeAsync(1)
    expect(conn!.getStatus()).not.toBe('switching_section') // gated, awaiting validator

    // Advance past the fail-OPEN gate window without delivering a validation_result.
    await vi.advanceTimersByTimeAsync(6500)

    // Fail-OPEN: the switch proceeded unchecked.
    expect(conn!.getStatus()).toBe('switching_section')
  })

  it('a DUPLICATE confirm while the gate is parked does NOT reset the fail-OPEN timer', async () => {
    // Codex PR #275: a duplicate confirm must not re-park the gate (which would reset
    // the 6s timer and let repeated duplicates delay the advance forever). The
    // original gate owns the boundary; the duplicate is a no-op. So the fail-OPEN
    // still fires ~6s after the FIRST confirm, regardless of a duplicate at +4s.
    vi.useFakeTimers()
    conn = new WebFormConnection(TWO_SECTION_SCHEMA)
    await conn.connect('wss://example/ws/fill')
    await vi.advanceTimersByTimeAsync(1)
    const ws = lastWs()
    ws.send.mockClear()

    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await vi.advanceTimersByTimeAsync(1)

    // A duplicate confirm arrives partway through the window.
    await vi.advanceTimersByTimeAsync(4000)
    fireConfirm(ws, 'f_s1')
    await vi.advanceTimersByTimeAsync(1)
    expect(conn!.getStatus()).not.toBe('switching_section') // still gated

    // Advance to just past the ORIGINAL 6s window (total ~6.5s from the first
    // confirm). If the duplicate had reset the timer, this would still be gated.
    await vi.advanceTimersByTimeAsync(2000)
    expect(conn!.getStatus()).toBe('switching_section')
  })
})
