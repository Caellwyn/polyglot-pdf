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

  async function connected(schema: FormSchema): Promise<MockWebSocket> {
    conn = new WebFormConnection(schema)
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

  it('a CONFLICT validation_result HOLDS the switch and marks the named fields steered', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await flush()

    deliverValidationResult(ws, [
      { field_ids: ['f_s1'], reason: 'looks off' },
    ])
    await flush()

    // The switch did NOT proceed (stay in-section for the steer).
    expect(conn!.getStatus()).not.toBe('switching_section')
    // f_s1 is now marked steered in sessionStorage.
    const state = SchemaFormStateManager.load()!
    expect(state.fieldValues['f_s1'].steered).toBe(true)
  })

  it('a steered field rides the NEXT validator payload as steered:true', async () => {
    const ws = await connected(TWO_SECTION_SCHEMA)
    fireFieldUpdate(ws, 'firstname', 'Jane')
    fireConfirm(ws, 'f_s1')
    await flush()
    deliverValidationResult(ws, [{ field_ids: ['f_s1'], reason: 'x' }])
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
