/**
 * Spec tests for the auto-reconnect path (bd polyglot-pdf-uov.5, T1.2).
 *
 * The reconnect path is the highest-impact failure mode in production (idle
 * timeout, GoAway, and network drops all route through handleClose ->
 * attemptReconnect), but until this suite it was unspecced: connection.test.ts
 * pins only the manager's status DELEGATION, and webFormConnection.token.test.ts
 * covers the fresh-token plumbing on (re)connect -- neither covers the
 * exponential BACKOFF or the reconnect-attempt CAP. These tests pin those two
 * behaviors directly on WebFormConnection (where attemptReconnect lives):
 *   - backoff: delay = min(reconnectDelay * 2^(attempts-1), 30000)
 *   - cap:     stop reconnecting after maxReconnectAttempts (5) -> 'disconnected'
 *   - a successful open resets the attempt counter (so the cap is per-outage)
 *
 * Together with token.test.ts's "re-fetches a fresh token on each reconnect",
 * this is the criterion-2(a) reconnect spec for the epic.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import { SchemaFormStateManager } from './schema-forms/state/schemaFormState'
import type { SchemaFormState } from './schema-forms/state/schemaFormState'
import type { FormSchema } from './schema-forms/types/schema'

// Mock WebSocket that records instances and exposes the lifecycle callbacks so a
// test can fire onclose by hand. onopen does NOT auto-fire here (unlike
// token.test.ts) because the reconnect timer creates new sockets asynchronously
// and the tests need to control exactly when each one "opens".
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3
  url: string
  readyState = 0
  bufferedAmount = 0
  onopen: (() => void) | null = null
  onmessage: ((e: any) => void) | null = null
  onerror: ((e: any) => void) | null = null
  onclose: ((e: any) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  // Helper: simulate the server accepting the connection.
  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  // Helper: simulate an unexpected close (code 1006-style drop).
  drop() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code: 1006, reason: '', wasClean: false })
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })
}

const SCHEMA: FormSchema = {
  source: 'web',
  fields: [],
  sections: [{ id: 's1', label: 'S1', order: 1 }],
} as unknown as FormSchema

/** Connect and complete the open handshake, returning the live socket. */
async function connectAndOpen(conn: WebFormConnection, url = 'wss://example/ws/fill') {
  const p = conn.connect(url)
  // The socket is constructed synchronously inside connect(); open it so the
  // connect() promise resolves and enableAutoReconnect flips on.
  const sock = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  sock.open()
  await p
  return sock
}

describe('WebFormConnection auto-reconnect (bd polyglot-pdf-uov.5)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    // attemptReconnect schedules via window.setTimeout; alias window to the
    // global so the timer registers under fake timers.
    global.window = globalThis as any
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
    vi.useRealTimers()
  })

  it('does NOT auto-reconnect the INITIAL connection drop (lets connection.ts try the cloud fallback)', () => {
    const conn = new WebFormConnection(SCHEMA)
    // Start connecting but DROP the socket before it ever opens, so
    // enableAutoReconnect is still false (it only flips true in handleOpen). We
    // do not await connect() here: an initial socket that closes without opening
    // never settles connect()'s promise under fake timers, and the point of this
    // test is purely that the CLOSE path schedules no reconnect.
    void conn.connect('wss://example/ws/fill').catch(() => { /* unsettled; ignored */ })
    const initial = MockWebSocket.instances[0]
    initial.drop()

    // No reconnect timer fired; still exactly one socket was ever created, and
    // the initial failure is left for connection.ts's cloud-fallback to handle.
    vi.advanceTimersByTime(60000)
    expect(MockWebSocket.instances.length).toBe(1)
    expect(conn.getStatus()).toBe('disconnected')
  })

  it('auto-reconnects after a drop on an ESTABLISHED connection, with exponential backoff', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)
    expect(MockWebSocket.instances.length).toBe(1)

    // First drop -> reconnect scheduled at 1000ms (2^0 * 1000). Nothing before.
    MockWebSocket.instances[0].drop()
    expect(conn.getStatus()).toBe('reconnecting')
    vi.advanceTimersByTime(999)
    expect(MockWebSocket.instances.length).toBe(1)
    vi.advanceTimersByTime(1)
    expect(MockWebSocket.instances.length).toBe(2) // attempt 1 fired at 1000ms

    // Drop the 2nd socket before it opens -> attempt 2 at 2000ms (2^1 * 1000).
    MockWebSocket.instances[1].drop()
    vi.advanceTimersByTime(1999)
    expect(MockWebSocket.instances.length).toBe(2)
    vi.advanceTimersByTime(1)
    expect(MockWebSocket.instances.length).toBe(3) // attempt 2 fired at 2000ms

    // Drop the 3rd -> attempt 3 at 4000ms (2^2 * 1000).
    MockWebSocket.instances[2].drop()
    vi.advanceTimersByTime(3999)
    expect(MockWebSocket.instances.length).toBe(3)
    vi.advanceTimersByTime(1)
    expect(MockWebSocket.instances.length).toBe(4) // attempt 3 fired at 4000ms
  })

  it('stops reconnecting after maxReconnectAttempts (5) and lands on reconnect_failed', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)

    // Drive 5 reconnect attempts: each new socket is dropped before it opens, so
    // the attempt counter never resets. Backoff caps at 30000ms.
    // attempt n fires at min(1000 * 2^(n-1), 30000): 1000, 2000, 4000, 8000, 16000.
    const delays = [1000, 2000, 4000, 8000, 16000]
    // Drop the original (opened) socket to start the cascade.
    MockWebSocket.instances[MockWebSocket.instances.length - 1].drop()
    for (let i = 0; i < delays.length; i++) {
      vi.advanceTimersByTime(delays[i])
      // A new socket should now exist for attempt i+1; drop it unopened.
      const sock = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      sock.drop()
    }

    // The 5th drop hit the cap: reconnectAttempts == maxReconnectAttempts, so
    // handleClose schedules no 6th attempt and surfaces the distinct terminal
    // 'reconnect_failed' status (an unexpected-drop give-up the user must act on,
    // which drives the connection-timeout modal -- bd polyglot-pdf-jf6w.3), not
    // the generic 'disconnected'.
    const countAtCap = MockWebSocket.instances.length
    vi.advanceTimersByTime(60000) // far past any backoff
    expect(MockWebSocket.instances.length).toBe(countAtCap) // no further sockets
    expect(conn.getStatus()).toBe('reconnect_failed')
  })

  it('resets the attempt counter on a SUCCESSFUL open (the cap is per-outage, not lifetime)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)

    // Outage 1: drop, let the reconnect fire, then OPEN it (success resets the
    // counter via handleOpen).
    MockWebSocket.instances[0].drop()
    vi.advanceTimersByTime(1000) // attempt 1
    const recovered = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    recovered.open()

    // Outage 2: a fresh drop must schedule the NEXT reconnect at the FIRST
    // backoff step (1000ms) again -- proving the counter reset. If it had NOT
    // reset, the delay would be 2000ms and nothing would fire at 1000ms.
    const before = MockWebSocket.instances.length
    recovered.drop()
    expect(conn.getStatus()).toBe('reconnecting')
    vi.advanceTimersByTime(1000)
    expect(MockWebSocket.instances.length).toBe(before + 1)
  })
})

/**
 * Handshake freshness on (re)connect / soft page-refresh (bd polyglot-pdf-fn1m).
 *
 * The handshake is built from this.state, which is the constructor's init()
 * snapshot. On a soft page refresh a brand-new WebFormConnection is built and
 * this.state can predate the latest sessionStorage save, so the stateless backend
 * would rebuild context from a STALE currentSectionId / fieldValues -- the "model
 * asserts a value from a previous section" symptom. handleOpen now calls
 * reloadState() (re-read sessionStorage into this.state) BEFORE building the
 * handshake, so it reflects the client's actual current field state.
 */
describe('WebFormConnection handshake reflects fresh sessionStorage on open (bd polyglot-pdf-fn1m)', () => {
  const TWO_SECTION_SCHEMA: FormSchema = {
    source: 'web',
    fields: [],
    sections: [
      { id: 's1', label: 'S1', order: 1, fields: [] },
      { id: 's2', label: 'S2', order: 2, fields: [] },
    ],
  } as unknown as FormSchema

  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    global.window = globalThis as any
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
    vi.restoreAllMocks()
  })

  it('builds the handshake from the CURRENT sessionStorage state, not the constructor snapshot', async () => {
    // Constructor snapshots section s1 (init() seeds a fresh session at the first
    // section for an empty store).
    const conn = new WebFormConnection(TWO_SECTION_SCHEMA)

    // Simulate the client having advanced to s2 and filled a field AFTER the
    // constructor ran (the state a soft refresh must resume from). reloadState()
    // reads this via SchemaFormStateManager.load(); return it fresh here.
    const freshState: SchemaFormState = {
      schema: TWO_SECTION_SCHEMA,
      fieldValues: { name_changed: { value: 'No', confirmed: true } },
      currentSectionId: 's2',
      completedSections: new Set<string>(['s1']),
      validationErrors: {},
      lastUpdated: 1,
      formSessionId: 'fss_test',
      loadedFieldIds: new Set<string>(),
      jitModeEnabled: false,
      disclaimerAccepted: true,
      selectedLanguage: 'English',
    } as unknown as SchemaFormState
    const loadSpy = vi
      .spyOn(SchemaFormStateManager, 'load')
      .mockReturnValue(freshState)

    // Open the socket -> handleOpen fires -> reloadState() + handshake send.
    const p = conn.connect('wss://example/ws/fill')
    const sock = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    sock.open()
    await p

    // reloadState() (which calls load()) must have run on open.
    expect(loadSpy).toHaveBeenCalled()

    // The handshake actually sent must reflect the FRESH state (s2 + the filled
    // value), not the constructor's s1 snapshot.
    const handshakeStr = (sock.send.mock.calls
      .map((c: any[]) => c[0])
      .find((s: any) => typeof s === 'string' && s.includes('"type":"handshake"'))) as string
    expect(handshakeStr).toBeDefined()
    const handshake = JSON.parse(handshakeStr)
    expect(handshake.section_label).toBe('S2')
    expect(handshake.section_number).toBe(2)
    expect(handshake.current_values).toHaveProperty('name_changed')
    // resume:true even on the first connect of this instance -- the fresh state
    // this soft refresh resumes from is in-progress (disclaimer accepted + a
    // filled field), so the backend must use the resume template and not
    // re-greet mid-form (bd polyglot-pdf-hc4b; this assertion previously
    // encoded the pre-fix behavior).
    expect(handshake.resume).toBe(true)
  })

  it('also refreshes the JIT handshake (loaded_field_ids + current_values) from fresh state', async () => {
    const conn = new WebFormConnection(TWO_SECTION_SCHEMA)

    // A JIT/DTI session's fresh state: reloadState() must feed getJITHandshakePayload
    // so the manifest-first handshake carries the current section, filled values,
    // and loaded_field_ids -- not the constructor snapshot.
    const freshJitState: SchemaFormState = {
      schema: TWO_SECTION_SCHEMA,
      fieldValues: { name_changed: { value: 'No', confirmed: true } },
      currentSectionId: 's2',
      completedSections: new Set<string>(['s1']),
      validationErrors: {},
      lastUpdated: 1,
      formSessionId: 'fss_test',
      loadedFieldIds: new Set<string>(['name_changed']),
      jitModeEnabled: true,
      continuousSessionEnabled: false,
      disclaimerAccepted: true,
      selectedLanguage: 'English',
    } as unknown as SchemaFormState
    vi.spyOn(SchemaFormStateManager, 'load').mockReturnValue(freshJitState)

    const p = conn.connect('wss://example/ws/fill')
    const sock = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    sock.open()
    await p

    const handshakeStr = (sock.send.mock.calls
      .map((c: any[]) => c[0])
      .find((s: any) => typeof s === 'string' && s.includes('"type":"handshake_jit"'))) as string
    expect(handshakeStr).toBeDefined()
    const handshake = JSON.parse(handshakeStr)
    expect(handshake.type).toBe('handshake_jit')
    expect(handshake.section_label).toBe('S2')
    // loadedFieldIds is a Set on state; getJITHandshakePayload serializes it to an
    // array -- reloadState() must have reconstructed it so the array is non-empty.
    expect(handshake.loaded_field_ids).toContain('name_changed')
    expect(handshake.current_values).toHaveProperty('name_changed')
  })
})
