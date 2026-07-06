/**
 * Coverage for WebFormConnection GoAway handling.
 *
 * DISPATCH (bd polyglot-pdf-c5t): the Gemini Live server sends a GoAway before
 * terminating the connection; the backend forwards it as {type:"go_away",
 * time_left}. handleMessage routes a go_away to the onGoAway callback with the
 * time_left, and -- unlike idle_timeout -- does NOT set the no-reconnect flag (a
 * GoAway is a server lifecycle reset; reconnect IS wanted).
 *
 * POLICY (bd polyglot-pdf-l3a.2): WebFormConnection also ACTS on the GoAway with a
 * silent, pre-emptive reconnect -- it tears down the current socket and immediately
 * reconnects through the standard path (which sends resume:true, bd
 * polyglot-pdf-vmxx, so no re-greeting), keeping status "connected" so the user
 * sees no drop. The reconnect is guarded so a burst of GoAways coalesces into one
 * reconnect and the paths that own the socket lifecycle (idle timeout, section
 * switch) are not raced.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import type { FormSchema } from './schema-forms/types/schema'

const SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { form_number: 'I-90', version: '1' },
  fields: [{ id: 'f1', name: 'f1', spoken_name: 'F1', type: 'text' }],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1'] }],
} as unknown as FormSchema

function msg(payload: unknown): MessageEvent {
  return { data: JSON.stringify(payload) } as MessageEvent
}

// Minimal WebSocket mock (mirrors webFormConnection.reconnect.test.ts) so the
// policy tests can exercise the real connect()/close() lifecycle. onopen does not
// auto-fire; a test opens a socket explicitly.
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

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  // Simulate the server rejecting/failing the connection: onerror then onclose,
  // mirroring how connect() settles a failed socket (handleError + reject).
  error() {
    this.onerror?.({})
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code: 1006, reason: '', wasClean: false })
  }

  send = (() => {}) as (data: any) => void
  close = () => {
    this.readyState = MockWebSocket.CLOSED
  }
}

/** Connect and complete the open handshake, returning the live socket. */
async function connectAndOpen(conn: WebFormConnection, url = 'wss://example/ws/fill') {
  const p = conn.connect(url)
  const sock = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  sock.open()
  await p
  return sock
}

describe('WebFormConnection GoAway dispatch (bd polyglot-pdf-c5t)', () => {
  beforeEach(() => {
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

  it('routes a go_away message to onGoAway with time_left', async () => {
    const seen: (string | null)[] = []
    const conn = new WebFormConnection(SCHEMA, { onGoAway: (t) => seen.push(t) })
    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '3.5s' }))
    expect(seen).toEqual(['3.5s'])
  })

  it('passes null when time_left is absent', async () => {
    const seen: (string | null)[] = []
    const conn = new WebFormConnection(SCHEMA, { onGoAway: (t) => seen.push(t) })
    await (conn as any).handleMessage(msg({ type: 'go_away' }))
    expect(seen).toEqual([null])
  })

  it('does NOT set the idle-timeout no-reconnect flag on go_away', async () => {
    const conn = new WebFormConnection(SCHEMA, { onGoAway: () => {} })
    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '1s' }))
    // A GoAway is a server lifecycle reset, not a user-inactivity close, so the
    // reconnect-suppressing flag idle_timeout sets must stay false.
    expect((conn as any).idleTimedOut).toBe(false)
  })

  it('does not throw when no onGoAway callback is registered', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await expect(
      (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
    ).resolves.toBeUndefined()
  })
})

describe('WebFormConnection GoAway reconnect POLICY (bd polyglot-pdf-l3a.2)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    // connect() has no timers on the happy path, but window must exist for the
    // reconnect timer references elsewhere in the class.
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

  it('pre-emptively reconnects on a go_away, keeps status connected, and closes the old socket', async () => {
    const conn = new WebFormConnection(SCHEMA)
    const first = await connectAndOpen(conn)
    // session_ready flips status to "connected".
    ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })
    expect(conn.getStatus()).toBe('connected')
    expect(MockWebSocket.instances.length).toBe(1)

    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))

    // A second socket was created (the pre-emptive reconnect) and the first was
    // closed. Status stayed "connected" -- no reconnecting/disconnected flicker.
    expect(MockWebSocket.instances.length).toBe(2)
    expect(first.readyState).toBe(MockWebSocket.CLOSED)
    expect(conn.getStatus()).toBe('connected')
  })

  it('reconnects with resume semantics (handshake carries resume:true) after a go_away', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)
    ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

    // Capture the handshake the NEW socket sends when it opens.
    let handshake: any = null
    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
    const reconnected = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    reconnected.send = (data: any) => { handshake = JSON.parse(data) }
    reconnected.open()

    // hasConnectedOnce is true after the first open, so the reconnect handshake
    // must carry resume:true -> backend suppresses greeting/section re-intro
    // (bd polyglot-pdf-vmxx), which is what makes the GoAway reconnect seamless.
    expect(handshake).toBeTruthy()
    expect(handshake.resume).toBe(true)
  })

  it('coalesces a burst of go_away messages into a single reconnect', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)
    ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

    // Two GoAways arrive before the reconnect completes (new socket not yet open).
    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '1s' }))

    // Only ONE extra socket was created -- the guard coalesced the second GoAway.
    expect(MockWebSocket.instances.length).toBe(2)
  })

  it('re-arms after the reconnect completes: a later go_away drives another reconnect', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)
    ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
    expect(MockWebSocket.instances.length).toBe(2)
    // Complete the reconnect (new socket opens -> guard clears in handleOpen).
    MockWebSocket.instances[1].open()

    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
    expect(MockWebSocket.instances.length).toBe(3)
  })

  it('does NOT reconnect on a go_away after an idle timeout (user-gated reconnect wins)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)
    ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

    // Idle timeout closes the connection and suppresses auto-reconnect.
    await (conn as any).handleMessage(msg({ type: 'idle_timeout' }))
    const countAfterIdle = MockWebSocket.instances.length

    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
    // No new socket -- the idle-timeout no-reconnect gate is respected.
    expect(MockWebSocket.instances.length).toBe(countAfterIdle)
  })

  it('does NOT reconnect on a go_away while a section switch is in flight', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await connectAndOpen(conn)
    ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

    // A section switch owns the socket lifecycle; mark it in flight.
    ;(conn as any).switchInFlight = true
    const before = MockWebSocket.instances.length

    await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
    expect(MockWebSocket.instances.length).toBe(before)
  })

  // Failure-path coverage (fresh-eyes PR-review gap): a GoAway pre-emptive
  // reconnect that FAILS must not strand the user on a stale "connected" or a
  // dead-end "error"; it falls back to the normal auto-reconnect loop, exactly the
  // recovery the pre-bead baseline had.
  describe('reconnect FAILURE falls back to auto-reconnect', () => {
    beforeEach(() => { vi.useFakeTimers() })
    afterEach(() => { vi.useRealTimers() })

    it('recovers via attemptReconnect when the pre-emptive reconnect socket errors', async () => {
      const conn = new WebFormConnection(SCHEMA)
      // connectAndOpen uses awaits; drive the open synchronously under fake timers.
      const p = conn.connect('wss://example/ws/fill')
      MockWebSocket.instances[0].open()
      await p
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })
      expect(conn.getStatus()).toBe('connected')

      // GoAway -> pre-emptive reconnect creates socket #2 (index 1).
      await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
      expect(MockWebSocket.instances.length).toBe(2)

      // That socket FAILS before it opens. connect() rejects; handleError must NOT
      // flash "error" (guard suppresses it), and the .catch falls back to
      // attemptReconnect -> "reconnecting" + a backoff timer.
      MockWebSocket.instances[1].error()
      await Promise.resolve() // let the connect() .catch microtask run
      await Promise.resolve()
      expect(conn.getStatus()).toBe('reconnecting')
      // The guard was released so the fallback (and any later GoAway) is not
      // permanently coalesced.
      expect((conn as any).goAwayReconnectInFlight).toBe(false)

      // The backoff fires a fresh reconnect socket (attempt 1 at 1000ms).
      vi.advanceTimersByTime(1000)
      expect(MockWebSocket.instances.length).toBe(3)
    })

    it('does not leave a stale "connected" status after a failed pre-emptive reconnect', async () => {
      const conn = new WebFormConnection(SCHEMA)
      const p = conn.connect('wss://example/ws/fill')
      MockWebSocket.instances[0].open()
      await p
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
      MockWebSocket.instances[1].error()
      await Promise.resolve()
      await Promise.resolve()

      // The whole point of the gap fix: status is NOT the misleading "connected"
      // (dead socket) it would have been if the .catch merely cleared the guard.
      expect(conn.getStatus()).not.toBe('connected')
    })
  })
})
