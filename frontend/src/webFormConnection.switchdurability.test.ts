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

  it('switchToSection rejects a SECOND switch while one is in flight (re-entrancy)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    // First switch goes in flight (no section_switched yet -> stays in flight).
    await conn.switchToSection('s2', 'ws://x')
    expect(conn.getStatus()).toBe('switching_section')

    const ws = MockWebSocket.instances[0]
    const sendCountAfterFirst = ws ? ws.send.mock.calls.length : 0

    // A concurrent second switch must be ignored (no extra manual_section_switch).
    await conn.switchToSection('s1', 'ws://x')
    const sendCountAfterSecond = ws ? ws.send.mock.calls.length : 0
    expect(sendCountAfterSecond).toBe(sendCountAfterFirst)
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
})
