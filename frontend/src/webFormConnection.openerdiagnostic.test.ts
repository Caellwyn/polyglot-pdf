/**
 * bd polyglot-pdf-xp4q: the field-1 opener gate in handleSessionReady must
 * never skip SILENTLY in the window where the opener is expected.
 *
 * Background: after I Agree, switchToFirstSection re-handshakes and the new
 * session's session_ready is supposed to auto-send `change_spoken_language`
 * (whose backend handler renders field-1's guidance into the initiating
 * message -- bd j748). On the deployed demo this skipped in 3/3 observed
 * real-auth sessions with no trace anywhere; the model then starts blind and
 * invents field ids. These tests pin the new contract:
 *
 *   opener fires        -> change_spoken_language sent, NO diagnostic
 *   expected-but-skipped -> ONE `client_diagnostic` naming the failing gate
 *   first connect        -> silent (the one legitimate skip; noise guard)
 *
 * Driven through the production message path (a real session_ready inbound).
 * Gate-state variants are set directly on the connection's in-memory state:
 * this.state staleness at session_ready time is itself a suspect in the live
 * bug, so these tests do not depend on the refresh-from-storage dance.
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
    queueMicrotask(() => { this.readyState = MockWebSocket.OPEN; this.onopen?.() })
  }
  send = vi.fn()
  close = vi.fn(() => { this.readyState = MockWebSocket.CLOSED })
}

const SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { title: 'T', version: '1.0.0', language: 'en', form_number: 'XQ', edition_date: '01/01/25', page_count: 1 },
  fields: [
    { id: 'f_a', name: 'fielda', spoken_name: 'Field A', type: 'text' },
    { id: 'f_b', name: 'fieldb', spoken_name: 'Field B', type: 'text' },
  ],
  sections: [{ id: 'only', label: 'Only', order: 1, fields: ['f_a', 'f_b'] }],
} as unknown as FormSchema

function lastWs(): MockWebSocket { return MockWebSocket.instances[MockWebSocket.instances.length - 1] }
function sentMessages(ws: MockWebSocket): any[] {
  return ws.send.mock.calls.map((c: any[]) => c[0]).filter((a: any) => typeof a === 'string').map((s: string) => JSON.parse(s))
}
function ofType(ws: MockWebSocket, type: string): any[] { return sentMessages(ws).filter(m => m.type === type) }
function deliverSessionReady(ws: MockWebSocket): void {
  ws.onmessage?.({ data: JSON.stringify({ type: 'session_ready', session_id: 'sess-1' }) })
}
const flush = () => new Promise<void>(r => setTimeout(r, 0))

describe('field-1 opener diagnostic (bd polyglot-pdf-xp4q)', () => {
  let conn: WebFormConnection | null = null
  let warnSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error override global WebSocket with the mock
    global.WebSocket = MockWebSocket
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null, length: 0,
    } as unknown as Storage
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })
  afterEach(() => { conn?.disconnect(); conn = null; warnSpy.mockRestore() })

  async function connected(): Promise<MockWebSocket> {
    conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    return ws
  }

  it('fires the opener (and no diagnostic) when all three gates hold', async () => {
    const ws = await connected()
    const state = (conn as any).state
    state.disclaimerAccepted = true
    state.selectedLanguage = 'English'

    deliverSessionReady(ws)
    await flush()

    const openers = ofType(ws, 'change_spoken_language')
    expect(openers).toHaveLength(1)
    expect(openers[0].spoken_language).toBe('English')
    expect(openers[0].next_field_hint).toBeTruthy()
    expect(ofType(ws, 'client_diagnostic')).toHaveLength(0)
  })

  it('emits ONE diagnostic on a post-switch skip, and a stale in-memory flag DIVERGES from storage (the staleness signature)', async () => {
    await connected()
    // Production path: a section switch is in flight when session_ready lands
    // (this is what the post-I-Agree switchToFirstSection produces). NOTE:
    // startSection DISCONNECTS and re-handshakes, so the session_ready must be
    // delivered on the NEW socket -- exactly like the real reconnect.
    await (conn as any).startSection('only')
    const ws = lastWs()
    // Manufacture the STALENESS hypothesis directly: storage says accepted,
    // the in-memory copy the gate reads does not. (The real I-Agree flow
    // persists accepted=true BEFORE switching, so a real capture with
    // disclaimer_accepted=false + storage_disclaimer_accepted=true is exactly
    // this bug; a real capture with both false means the accept never landed.)
    const persisted = JSON.parse(sessionStorage.getItem('schema_form_state')!)
    persisted.disclaimerAccepted = true
    sessionStorage.setItem('schema_form_state', JSON.stringify(persisted))
    // PROBE: verify the write landed where the diagnostic will read it.
    const { SchemaFormStateManager } = await import('./schema-forms/state/schemaFormState')
    expect(SchemaFormStateManager.load()?.disclaimerAccepted).toBe(true)
    const state = (conn as any).state
    state.disclaimerAccepted = false
    ws.send.mockClear()

    deliverSessionReady(ws)
    await flush()

    expect(ofType(ws, 'change_spoken_language')).toHaveLength(0)
    const diags = ofType(ws, 'client_diagnostic')
    expect(diags).toHaveLength(1)
    expect(diags[0]).toMatchObject({
      event: 'field1_opener_skipped',
      was_section_switch: true,
      disclaimer_accepted: false,
      // The divergence that names the staleness bug in one glance:
      storage_disclaimer_accepted: true,
      // A form with unconfirmed fields: NOT the benign completed shape.
      is_form_complete: false,
    })
    // The console names it too, for a devtools-open session.
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('field-1 opener SKIPPED'),
      expect.objectContaining({ was_section_switch: true })
    )
  })

  it('tolerates the old backend\'s unknown_control reply without failing the session (deploy skew)', async () => {
    const ws = await connected()
    // Drive a switch so the skew lands in the worst window: an in-flight
    // switch, where handleServerError would otherwise failSectionSwitch.
    await (conn as any).startSection('only')
    const ws2 = lastWs()

    // The OLD backend answers our client_diagnostic with this benign ack.
    ws2.onmessage?.({ data: JSON.stringify({ type: 'error', code: 'unknown_control' }) })
    await flush()

    // The session must NOT be driven into the error state by it.
    expect((conn as any).status).not.toBe('error')
  })

  it('emits a diagnostic with has_next_field_hint=false when accepted but nothing is askable', async () => {
    const ws = await connected()
    const state = (conn as any).state
    state.disclaimerAccepted = true
    state.selectedLanguage = 'English'
    // Every field confirmed -> computeNextFieldHintString has nothing to offer.
    state.fieldValues = {
      f_a: { value: 'x', confirmed: true },
      f_b: { value: 'y', confirmed: true },
    }

    deliverSessionReady(ws)
    await flush()

    expect(ofType(ws, 'change_spoken_language')).toHaveLength(0)
    const diags = ofType(ws, 'client_diagnostic')
    expect(diags).toHaveLength(1)
    expect(diags[0]).toMatchObject({
      disclaimer_accepted: true,
      has_selected_language: true,
      has_next_field_hint: false,
      // Every field is confirmed, so this is the BENIGN completed-form shape --
      // the flag that separates it from a genuinely broken opener in the logs
      // (fresh-eyes finding: without it the two are byte-identical).
      is_form_complete: true,
    })
  })

  it('stays SILENT on the first connect (no switch, disclaimer not yet accepted) -- the noise guard', async () => {
    const ws = await connected()

    deliverSessionReady(ws)
    await flush()

    expect(ofType(ws, 'change_spoken_language')).toHaveLength(0)
    expect(ofType(ws, 'client_diagnostic')).toHaveLength(0)
  })
})
