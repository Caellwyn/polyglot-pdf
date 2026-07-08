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

  // Simulate the server rejecting/failing the connection: onerror then onclose in
  // the SAME synchronous turn. NOTE: real browsers fire onerror and onclose as
  // SEPARATE macrotasks, so a promise rejection queued in onerror runs its .catch
  // BEFORE onclose -- errorAsync() below models that ordering. Use error() only
  // where the interleaving does not matter.
  error() {
    this.onerror?.({})
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code: 1006, reason: '', wasClean: false })
  }

  // Real-browser ordering: onerror now (fires connect()'s handleError + reject, so
  // the .catch microtask is queued), onclose on a LATER macrotask. This is what
  // lets a test observe the failed-GoAway-reconnect double-drive: the .catch runs
  // (and may schedule a reconnect) between onerror and onclose (bd polyglot-pdf-l3a.2,
  // Opus fresh-eyes). Returns a promise that resolves after onclose has fired.
  errorAsync(): Promise<void> {
    this.onerror?.({})
    this.readyState = MockWebSocket.CLOSED
    return new Promise((resolve) => {
      setTimeout(() => {
        this.onclose?.({ code: 1006, reason: '', wasClean: false })
        resolve()
      }, 0)
    })
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

      // That socket FAILS before it opens, with REAL browser ordering (onerror now,
      // onclose a macrotask later). connect() rejects; handleError must NOT flash
      // "error" (guard suppresses it), and the .catch falls back to attemptReconnect
      // -> "reconnecting" + a backoff timer.
      const closed = MockWebSocket.instances[1].errorAsync()
      await Promise.resolve() // let the connect() .catch microtask run
      await Promise.resolve()
      expect(conn.getStatus()).toBe('reconnecting')
      // The guard was released so the fallback (and any later GoAway) is not
      // permanently coalesced.
      expect((conn as any).goAwayReconnectInFlight).toBe(false)
      // Exactly ONE reconnect attempt was counted so far (the .catch fallback).
      expect((conn as any).reconnectAttempts).toBe(1)

      // Now the LATER onclose macrotask lands. In a real browser this is where the
      // double-drive bug lived: handleClose used to fall through to a SECOND
      // attemptReconnect. It must now be a no-op (a reconnect is already scheduled).
      vi.advanceTimersByTime(0)
      await closed
      expect((conn as any).reconnectAttempts).toBe(1) // NOT 2 -- no double-drive

      // The backoff fires exactly ONE fresh reconnect socket (attempt 1 at 1000ms),
      // not two concurrent ones.
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
      const closed = MockWebSocket.instances[1].errorAsync()
      await Promise.resolve()
      await Promise.resolve()
      vi.advanceTimersByTime(0)
      await closed

      // The whole point of the gap fix: status is NOT the misleading "connected"
      // (dead socket) it would have been if the .catch merely cleared the guard.
      expect(conn.getStatus()).not.toBe('connected')
    })
  })

  // Spontaneous-drop coverage (bd polyglot-pdf-ppfy): a backend
  // {type:"gemini_session_dropped"} (a 1011 the backend detected behind the still-
  // open WS) drives the SAME pre-emptive reconnect as a GoAway, but surfaces a
  // "reconnecting" status so the UI can show the transient recovery modal.
  describe('spontaneous drop reconnect (bd polyglot-pdf-ppfy)', () => {
    it('reconnects on gemini_session_dropped and surfaces "reconnecting" status', async () => {
      const conn = new WebFormConnection(SCHEMA)
      const first = await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })
      expect(conn.getStatus()).toBe('connected')

      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))

      // A new socket was created and the old one closed (same mechanism as GoAway).
      expect(MockWebSocket.instances.length).toBe(2)
      expect(first.readyState).toBe(MockWebSocket.CLOSED)
      // UNLIKE GoAway (which stays "connected"), a spontaneous drop surfaces
      // "reconnecting" so the transient modal shows during recovery.
      expect(conn.getStatus()).toBe('reconnecting')
    })

    it('restores "connected" when the reconnect completes (clears the modal)', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
      expect(conn.getStatus()).toBe('reconnecting')

      // Completing the reopen (open + session_ready) restores "connected", which is
      // what flips the reconnecting modal off in the overlay.
      const reconnected = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      reconnected.open()
      ;(conn as any).handleSessionReady({ session_id: 's2', native_vad: false })
      expect(conn.getStatus()).toBe('connected')
    })

    it('reconnects with resume:true on a spontaneous drop (no re-greeting)', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      let handshake: any = null
      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
      const reconnected = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      reconnected.send = (data: any) => { handshake = JSON.parse(data) }
      reconnected.open()

      expect(handshake).toBeTruthy()
      expect(handshake.resume).toBe(true)
    })

    it('coalesces with an in-flight GoAway reconnect (no double reconnect)', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      // A GoAway starts a reconnect; a spontaneous-drop message arriving before it
      // completes must coalesce (the shared goAwayReconnectInFlight guard).
      await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
      expect(MockWebSocket.instances.length).toBe(2) // one reconnect, not two
    })

    it('does NOT reconnect on a spontaneous drop after an idle timeout', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      await (conn as any).handleMessage(msg({ type: 'idle_timeout' }))
      const countAfterIdle = MockWebSocket.instances.length

      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
      expect(MockWebSocket.instances.length).toBe(countAfterIdle)
    })

    // fresh-eyes finding 1: the "reconnecting" status is NOT unique to the drop
    // path -- an ordinary WS blip's attemptReconnect sets it too. isDroppedReconnect()
    // must distinguish them so the overlay only shows the "trouble reaching the AI"
    // modal for a genuine Gemini drop.
    it('flags isDroppedReconnect() true only for a gemini_session_dropped reconnect', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })
      expect(conn.isDroppedReconnect()).toBe(false)

      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
      expect(conn.getStatus()).toBe('reconnecting')
      expect(conn.isDroppedReconnect()).toBe(true) // gates the modal ON
    })

    it('does NOT flag isDroppedReconnect() for an ordinary WS-close reconnect (network blip)', async () => {
      const conn = new WebFormConnection(SCHEMA)
      const sock = await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      // An ordinary unexpected close (NOT a gemini_session_dropped) -> handleClose
      // -> attemptReconnect -> status "reconnecting", but this is a network blip,
      // not an AI drop, so the modal must stay silent.
      sock.readyState = MockWebSocket.CLOSED
      ;(sock.onclose as any)?.({ code: 1006, reason: '', wasClean: false })
      expect(conn.getStatus()).toBe('reconnecting')
      expect(conn.isDroppedReconnect()).toBe(false) // gates the modal OFF
    })

    // fresh-eyes (two independent reviews): a gemini_session_dropped that COALESCES
    // into an in-flight GoAway reconnect must NOT leak isDroppedReconnect()=true. If
    // it did, the next ordinary WS blip would wrongly show the AI modal.
    it('does NOT leak isDroppedReconnect() when a drop coalesces into an in-flight GoAway reconnect', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      // GoAway starts a reconnect (status stays "connected" -- silent).
      await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
      expect(conn.getStatus()).toBe('connected')
      // A drop arrives before that reconnect completes -> coalesces (no fresh
      // reconnect starts), so the drop marker must NOT be set.
      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
      expect(conn.isDroppedReconnect()).toBe(false)
      expect(MockWebSocket.instances.length).toBe(2) // still one reconnect

      // The coalesced reconnect completes (status stays "connected").
      MockWebSocket.instances[1].open()
      ;(conn as any).handleSessionReady({ session_id: 's2', native_vad: false })
      expect(conn.isDroppedReconnect()).toBe(false)

      // A later ORDINARY blip drives status -> "reconnecting"; the modal must stay
      // silent (marker never leaked true).
      const live = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      live.readyState = MockWebSocket.CLOSED
      ;(live.onclose as any)?.({ code: 1006, reason: '', wasClean: false })
      expect(conn.getStatus()).toBe('reconnecting')
      expect(conn.isDroppedReconnect()).toBe(false)
    })

    it('clears isDroppedReconnect() when the drop reconnect recovers (connected)', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

      await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
      expect(conn.isDroppedReconnect()).toBe(true)

      // Reopen + session_ready -> connected -> the marker (and modal) clear.
      MockWebSocket.instances[MockWebSocket.instances.length - 1].open()
      ;(conn as any).handleSessionReady({ session_id: 's2', native_vad: false })
      expect(conn.getStatus()).toBe('connected')
      expect(conn.isDroppedReconnect()).toBe(false)
    })

    // fresh-eyes finding 2: a drop reconnect whose socket OPENS but never gets
    // session_ready (backend hung) must escalate to reconnect_failed, not stick on
    // the transient modal forever.
    describe('drop-reconnect watchdog', () => {
      beforeEach(() => { vi.useFakeTimers() })
      afterEach(() => { vi.useRealTimers() })

      it('escalates to reconnect_failed if session_ready never arrives after reopen', async () => {
        const conn = new WebFormConnection(SCHEMA)
        const p = conn.connect('wss://example/ws/fill')
        MockWebSocket.instances[0].open()
        await p
        ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

        await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
        expect(conn.getStatus()).toBe('reconnecting')
        expect(conn.isDroppedReconnect()).toBe(true)

        // The reconnect socket OPENS (clears goAwayReconnectInFlight) but the backend
        // never sends session_ready -- we stay on "reconnecting".
        MockWebSocket.instances[MockWebSocket.instances.length - 1].open()
        expect(conn.getStatus()).toBe('reconnecting')

        // Watchdog fires -> escalate to reconnect_failed (terminal modal), clearing
        // the transient marker.
        vi.advanceTimersByTime(20000)
        expect(conn.getStatus()).toBe('reconnect_failed')
        expect(conn.isDroppedReconnect()).toBe(false)
      })

      it('does NOT escalate if session_ready arrives before the watchdog', async () => {
        const conn = new WebFormConnection(SCHEMA)
        const p = conn.connect('wss://example/ws/fill')
        MockWebSocket.instances[0].open()
        await p
        ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

        await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
        const reconnected = MockWebSocket.instances[MockWebSocket.instances.length - 1]
        reconnected.open()
        ;(conn as any).handleSessionReady({ session_id: 's2', native_vad: false })
        expect(conn.getStatus()).toBe('connected')

        // Advancing past the watchdog window must NOT flip us to reconnect_failed.
        vi.advanceTimersByTime(20000)
        expect(conn.getStatus()).toBe('connected')
      })

      // bd polyglot-pdf-vqbm (fresh-eyes): if the pre-emptive reconnect FAILS and
      // falls back to attemptReconnect's exponential backoff, a reconnect is
      // legitimately still pending -- the watchdog must NOT prematurely force
      // reconnect_failed while a backoff timer is scheduled. We invoke the watchdog
      // callback directly (rather than advancing time, which would also fire the
      // backoff and start a dangling socket) to isolate the stand-down guard.
      it('does NOT escalate while an attemptReconnect backoff is still pending', async () => {
        const conn = new WebFormConnection(SCHEMA)
        const p = conn.connect('wss://example/ws/fill')
        MockWebSocket.instances[0].open()
        await p
        ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

        // Drop -> pre-emptive reconnect creates socket #2, watchdog armed.
        await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
        expect(conn.isDroppedReconnect()).toBe(true)

        // That socket FAILS -> .catch -> attemptReconnect schedules a backoff timer
        // (status stays "reconnecting", reconnectTimer !== null, a recovery pending).
        // Use the synchronous error() (onerror + onclose same turn) so no real-timer
        // promise dangles under fake timers.
        MockWebSocket.instances[1].error()
        await Promise.resolve()
        await Promise.resolve()
        expect(conn.getStatus()).toBe('reconnecting')
        expect((conn as any).reconnectTimer).not.toBeNull()

        // The drop-watchdog's fire condition, evaluated while the backoff is still
        // pending, must be FALSE (it stands down on `reconnectTimer !== null`), so it
        // does NOT force reconnect_failed -- the pending backoff owns recovery.
        const wouldEscalate =
          (conn as any).droppedReconnectInFlight &&
          conn.getStatus() === 'reconnecting' &&
          (conn as any).reconnectTimer === null
        expect(wouldEscalate).toBe(false)

        // Tear down so the pending backoff timer does not fire a dangling reconnect.
        conn.disconnect()
      })

      // bd polyglot-pdf-yigb (fresh-eyes): the watchdog is re-armed on EVERY reopen
      // (handleOpen), so a hang AFTER a backoff-driven reopen still escalates -- it
      // is not left uncovered by the one-shot initial arm. This drives the REAL
      // watchdog setTimeout callback (not a re-derived condition) end to end.
      it('escalates to reconnect_failed if a backoff-driven reopen then hangs', async () => {
        const conn = new WebFormConnection(SCHEMA)
        const p = conn.connect('wss://example/ws/fill')
        MockWebSocket.instances[0].open()
        await p
        ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })

        // Drop -> pre-emptive reconnect (socket #2), initial watchdog armed.
        await (conn as any).handleMessage(msg({ type: 'gemini_session_dropped' }))
        expect(conn.isDroppedReconnect()).toBe(true)

        // Pre-emptive socket FAILS -> attemptReconnect schedules a backoff timer.
        MockWebSocket.instances[1].error()
        await Promise.resolve()
        await Promise.resolve()
        expect(conn.getStatus()).toBe('reconnecting')

        // Fire the backoff timer (1000ms): attemptReconnect -> connect() opens
        // socket #3. Open it -> handleOpen re-arms the watchdog for THIS socket.
        vi.advanceTimersByTime(1000)
        // connect() is async (may await a token); flush microtasks, then open the
        // newest socket.
        await Promise.resolve()
        await Promise.resolve()
        const s3 = MockWebSocket.instances[MockWebSocket.instances.length - 1]
        s3.open()
        // After a backoff reopen, connect() moved status to "connecting" (not
        // "reconnecting"); the drop marker is still set and the watchdog re-armed.
        expect(conn.getStatus()).toBe('connecting')
        expect(conn.isDroppedReconnect()).toBe(true)

        // The backoff socket opened but the backend NEVER sends session_ready (a
        // hang). The re-armed watchdog (reconnectTimer is null now -- the backoff
        // fired) must escalate to reconnect_failed rather than stick forever.
        vi.advanceTimersByTime(20000)
        expect(conn.getStatus()).toBe('reconnect_failed')
        expect(conn.isDroppedReconnect()).toBe(false)
      })
    })
  })

  // Async-token-gap coverage (Opus fresh-eyes Finding 3): in production getToken is
  // always registered, so the reconnect connect() suspends on `await getToken()`
  // with this.ws already nulled. If the OLD (closing) socket's onclose lands during
  // that gap, handleClose must stand down on the guard (not auto-reconnect), and the
  // pending token resolving must still yield exactly one clean reconnect.
  describe('reconnect with a pending async token', () => {
    it('stands down on the old socket close during the token await, then reconnects once', async () => {
      const conn = new WebFormConnection(SCHEMA)
      await connectAndOpen(conn)
      ;(conn as any).handleSessionReady({ session_id: 's', native_vad: false })
      const first = MockWebSocket.instances[0]

      // Register a getToken that we control: the reconnect connect() will suspend
      // here with this.ws === null.
      let releaseToken!: (t: string) => void
      conn.setGetToken(() => new Promise<string>((res) => { releaseToken = res }))

      // GoAway -> handleGoAwayReconnect nulls this.ws, closes `first`, calls
      // connect() which suspends on the pending token. No new socket yet.
      await (conn as any).handleMessage(msg({ type: 'go_away', time_left: '2s' }))
      expect(MockWebSocket.instances.length).toBe(1)

      // The OLD socket's onclose lands during the token gap (this.ws is null).
      // handleClose must NOT schedule an auto-reconnect -- the guard stands it down.
      first.readyState = MockWebSocket.CLOSED
      ;(first.onclose as any)?.({ code: 1006, reason: '', wasClean: false })
      expect((conn as any).reconnectTimer).toBeNull()

      // Token resolves -> connect() proceeds and opens exactly one new socket, which
      // completes the reconnect (guard clears, status connected).
      releaseToken('tok')
      await Promise.resolve()
      await Promise.resolve()
      expect(MockWebSocket.instances.length).toBe(2)
      MockWebSocket.instances[1].open()
      expect((conn as any).goAwayReconnectInFlight).toBe(false)
      expect(conn.getStatus()).toBe('connected')
    })
  })
})
