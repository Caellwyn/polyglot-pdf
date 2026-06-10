/**
 * Coverage for WebFormConnection section-switch durability (bd polyglot-pdf-aun / WS-D).
 *
 * The FE used isSectionSwitching as both the auto-reconnect suppressor AND an
 * implicit switch guard. That conflated flag could leave the UI stuck on
 * `switching_section` when a switch failed mid-flight (a reconnect drop, a server
 * error, or a hang), and did not stop a second overlapping switch. These tests
 * cover the new behavior: a real re-entrancy guard (switchInFlight), a watchdog
 * that surfaces `error` on a hung switch, and `error` recovery from a server
 * error / mid-switch close instead of a stuck status.
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
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })
}

const SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { form_number: 'I-90', version: '1' },
  fields: [
    { id: 'f1', name: 'f1', spoken_name: 'F1', type: 'text' },
    { id: 'f2', name: 'f2', spoken_name: 'F2', type: 'text' },
  ],
  sections: [
    { id: 's1', label: 'S1', order: 1, fields: ['f1'] },
    { id: 's2', label: 'S2', order: 2, fields: ['f2'] },
  ],
  // The AI-initiated path (handlePrepareSectionSwitchRequest) guards on
  // schema.parts being present, so include a minimal parts list.
  parts: [{ id: 'p1', label: 'P1', order: 1, sections: ['s1', 's2'] }],
} as unknown as FormSchema

function installSessionStorage() {
  const store: Record<string, string> = {}
  global.sessionStorage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { for (const k of Object.keys(store)) delete store[k] },
    key: () => null,
    length: 0,
  } as unknown as Storage
}

describe('WebFormConnection section-switch durability (bd polyglot-pdf-aun)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    installSessionStorage()
    SchemaFormStateManager.save(SchemaFormStateManager.init(SCHEMA))
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('switchToSection REJECTS (throws) a second switch while one is in flight', async () => {
    const conn = new WebFormConnection(SCHEMA)
    await conn.switchToSection('s2', 'ws://x')
    expect(conn.getStatus()).toBe('switching_section')
    expect((conn as any).switchInFlight).toBe(true)

    // A second switch must be REJECTED (throw), not silently resolved -- the caller
    // pre-updates the UI and needs to know to roll back (Codex PR #137).
    await expect(conn.switchToSection('s1', 'ws://x')).rejects.toThrow(/already in progress/)
  })

  it('two CONCURRENT switchToSection calls: only ONE manual_section_switch is sent', async () => {
    // The TOCTOU race (Codex/fresh-eyes PR #137): guard must be claimed
    // SYNCHRONOUSLY before the waitForBufferDrain await, so two calls started in
    // the same tick can't both pass. The second rejects.
    const conn = new WebFormConnection(SCHEMA)
    // A live socket so switchToSection's send() has a target and waitForBufferDrain
    // is exercised.
    ;(conn as any).ws = { readyState: MockWebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn() }
    const sendSpy = (conn as any).ws.send

    const p1 = conn.switchToSection('s2', 'ws://x')
    const p2 = conn.switchToSection('s1', 'ws://x')
    const results = await Promise.allSettled([p1, p2])

    // Exactly one fulfilled, one rejected -- and exactly one manual_section_switch.
    const fulfilled = results.filter(r => r.status === 'fulfilled').length
    const rejected = results.filter(r => r.status === 'rejected').length
    expect(fulfilled).toBe(1)
    expect(rejected).toBe(1)
    // send() stringifies the message, so parse each call's first arg.
    const switchSends = sendSpy.mock.calls.filter((c: any[]) => {
      try { return JSON.parse(c[0])?.type === 'manual_section_switch' } catch { return false }
    }).length
    expect(switchSends).toBe(1)
  })

  it('a server error during a switch surfaces `error`, not a stuck switching_section', async () => {
    const errors: Error[] = []
    const conn = new WebFormConnection(SCHEMA, { onError: (e) => errors.push(e) })

    await conn.switchToSection('s2', 'ws://x')
    expect(conn.getStatus()).toBe('switching_section')

    // Backend rejects the switch (e.g. concurrent-switch reject, post-0c1).
    ;(conn as any).handleServerError({
      type: 'error', code: 'section_switch_failed', message: 'A section switch is already in progress.',
    })

    expect(conn.getStatus()).toBe('error')
    expect(errors.length).toBe(1)
    // The guard is released, so a NEW switch can proceed afterward.
    expect((conn as any).switchInFlight).toBe(false)
  })

  it('the watchdog surfaces `error` when a switch never confirms', async () => {
    const errors: Error[] = []
    const conn = new WebFormConnection(SCHEMA, { onError: (e) => errors.push(e) })

    await conn.switchToSection('s2', 'ws://x')
    expect(conn.getStatus()).toBe('switching_section')

    // No section_switched, no error -- advance past the watchdog timeout.
    vi.advanceTimersByTime(15000)

    expect(conn.getStatus()).toBe('error')
    expect(errors.length).toBe(1)
    expect((conn as any).switchInFlight).toBe(false)
  })

  it('section_switched completes the switch: status connected, guard + watchdog cleared', async () => {
    const errors: Error[] = []
    const conn = new WebFormConnection(SCHEMA, { onError: (e) => errors.push(e) })
    await conn.switchToSection('s2', 'ws://x')
    expect((conn as any).switchInFlight).toBe(true)

    ;(conn as any).handleSectionSwitched({ section_number: 2 })

    expect(conn.getStatus()).toBe('connected')
    expect((conn as any).switchInFlight).toBe(false)
    expect((conn as any).sectionSwitchWatchdog).toBeNull()

    // The watchdog must NOT fire after a successful completion.
    vi.advanceTimersByTime(15000)
    expect(errors.length).toBe(0)
    expect(conn.getStatus()).toBe('connected')
  })

  it('a server error when NO switch is in flight does not flip status to error', async () => {
    const errors: Error[] = []
    const conn = new WebFormConnection(SCHEMA, { onError: (e) => errors.push(e) })

    // Not switching -> the old behavior: fire onError, leave status as-is.
    ;(conn as any).handleServerError({ type: 'error', message: 'some unrelated error' })

    expect(errors.length).toBe(1)
    expect(conn.getStatus()).not.toBe('switching_section')
  })

  it('the AI-initiated path (prepare_section_switch) sets the guard, blocking a manual switch', async () => {
    // Codex PR #137: handlePrepareSectionSwitchRequest must mark the switch in
    // flight so a manual click during an AI switch is rejected.
    const conn = new WebFormConnection(SCHEMA)
    // The schema needs `parts` for this handler's guard; seed via the real init.
    ;(conn as any).ws = { readyState: MockWebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn() }
    ;(conn as any).handlePrepareSectionSwitchRequest({ request_id: 'r', identifier: 2 })

    expect((conn as any).switchInFlight).toBe(true)
    expect(conn.getStatus()).toBe('switching_section')

    // A manual switch during the AI window is now rejected.
    await expect(conn.switchToSection('s1', 'ws://x')).rejects.toThrow(/already in progress/)

    // section_switched releases the guard.
    ;(conn as any).handleSectionSwitched({ section_number: 2 })
    expect((conn as any).switchInFlight).toBe(false)
  })

  it('an INVALID AI section request does not leave the guard stuck (Codex round 2)', () => {
    // Codex PR #137 round 2: the guard is claimed only after a valid target, so an
    // unknown section sends section_info: null WITHOUT a stuck switching_section.
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).ws = { readyState: MockWebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn() }
    ;(conn as any).handlePrepareSectionSwitchRequest({ request_id: 'r', identifier: 999 })

    expect((conn as any).switchInFlight).toBe(false)
    expect(conn.getStatus()).not.toBe('switching_section')
    // It replied with a null section_info (error).
    const sent = (conn as any).ws.send.mock.calls.map((c: any[]) => JSON.parse(c[0]))
    const resp = sent.find((m: any) => m.type === 'section_info_response')
    expect(resp.section_info).toBeNull()
  })

  it('the AI path REJECTS a prepare_section_switch while a switch is already in flight (Codex round 2)', async () => {
    // Codex PR #137 round 2: manual-then-AI overlap -- a manual switch is in flight,
    // then Gemini emits prepare_section_switch. The AI path must reply null/error
    // and NOT mutate state or start a second backend switch.
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).ws = { readyState: MockWebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn() }
    await conn.switchToSection('s2', 'ws://x')
    expect((conn as any).switchInFlight).toBe(true)

    const sendCountBefore = (conn as any).ws.send.mock.calls.length
    ;(conn as any).handlePrepareSectionSwitchRequest({ request_id: 'r', identifier: 1 })

    // It replied with a null section_info + error (a rejection, not a switch).
    const newSends = (conn as any).ws.send.mock.calls.slice(sendCountBefore).map((c: any[]) => JSON.parse(c[0]))
    const resp = newSends.find((m: any) => m.type === 'section_info_response')
    expect(resp.section_info).toBeNull()
    expect(resp.error).toMatch(/already in progress/)
  })

  it('an INTENTIONAL disconnect during a switch cancels it silently (no false error)', async () => {
    // Codex PR #137: disconnect() (UI unmount / stop-session) must clear the guard
    // so the close it triggers does not fire a false onError/`error` status.
    const errors: Error[] = []
    const conn = new WebFormConnection(SCHEMA, { onError: (e) => errors.push(e) })
    await conn.switchToSection('s2', 'ws://x')
    expect((conn as any).switchInFlight).toBe(true)

    conn.disconnect()

    expect((conn as any).switchInFlight).toBe(false)
    expect((conn as any).sectionSwitchWatchdog).toBeNull()
    expect(errors.length).toBe(0) // no false switch-failure error
    expect(conn.getStatus()).not.toBe('error')
  })

  it('a STALE close from a replaced socket does not fail a healthy in-flight switch (Codex round 2)', async () => {
    // Codex PR #137 round 2: during startSection the old socket's close can arrive
    // after this.ws is swapped to the new socket. handleClose must ignore a close
    // from a socket that is not the current this.ws, else it falsely fails the switch.
    const errors: Error[] = []
    const conn = new WebFormConnection(SCHEMA, { onError: (e) => errors.push(e) })
    await conn.switchToSection('s2', 'ws://x')
    expect((conn as any).switchInFlight).toBe(true)

    const currentWs = { readyState: MockWebSocket.OPEN } as any
    ;(conn as any).ws = currentWs
    ;(conn as any).enableAutoReconnect = true

    // A close fires from a DIFFERENT (stale/old) socket.
    const staleWs = { readyState: MockWebSocket.CLOSED } as any
    ;(conn as any).handleClose({ code: 1006 } as any, staleWs)

    // The switch is untouched -- no error, still in flight.
    expect(errors.length).toBe(0)
    expect(conn.getStatus()).not.toBe('error')
    expect((conn as any).switchInFlight).toBe(true)
  })

  it('startSection releases the guard on session_ready, not merely on handshake send', async () => {
    // Codex/fresh-eyes PR #137: a stall after the handshake but before session_ready
    // must still be watchdog-covered, so the guard must survive until session_ready.
    const conn = new WebFormConnection(SCHEMA)
    const p = conn.startSection('s2', 'ws://x')
    // Let the mock socket open + the handshake send complete.
    await vi.advanceTimersByTimeAsync(1)
    await p

    // After the handshake send, the switch is still in flight (NOT released early).
    expect((conn as any).switchInFlight).toBe(true)

    // session_ready is the terminal success -> releases the guard + watchdog.
    ;(conn as any).handleSessionReady({ session_id: 's', native_vad: true })
    expect((conn as any).switchInFlight).toBe(false)
    expect((conn as any).sectionSwitchWatchdog).toBeNull()
    expect(conn.getStatus()).toBe('connected')
  })
})
