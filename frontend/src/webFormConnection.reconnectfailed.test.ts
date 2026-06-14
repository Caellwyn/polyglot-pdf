/**
 * Coverage for the terminal-reconnect-failure status (bd polyglot-pdf-jf6w.3).
 *
 * On an unexpected drop the FE auto-reconnects with exponential backoff up to
 * maxReconnectAttempts. Before jf6w.3, exhausting those attempts collapsed to
 * the generic "disconnected" status -- indistinguishable from an intentional
 * teardown, so the UI could not tell "we gave up, user must act" from "we hung
 * up on purpose." jf6w.3 adds a distinct "reconnect_failed" status set only on
 * genuine give-up; it is the explicit signal that drives the connection-timeout
 * modal (jf6w.2). A transient drop that still has attempts left must NOT surface
 * it (silent auto-reconnect wins for blips).
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
  ],
  sections: [
    { id: 's1', label: 'S1', order: 1, fields: ['f1'] },
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

describe('WebFormConnection terminal reconnect failure (bd polyglot-pdf-jf6w.3)', () => {
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

  it('a drop with attempts remaining keeps auto-reconnecting, NOT reconnect_failed', () => {
    const statuses: string[] = []
    const conn = new WebFormConnection(SCHEMA, { onStatusChange: (s) => statuses.push(s) })
    // Simulate a live, auto-reconnect-enabled connection that drops once.
    ;(conn as any).enableAutoReconnect = true
    ;(conn as any).status = 'connected'
    ;(conn as any).reconnectAttempts = 0
    ;(conn as any).connectedUrl = 'ws://x'

    ;(conn as any).handleClose({ code: 1006 } as CloseEvent)

    // A transient blip: the FE silently retries, it does NOT give up.
    expect(conn.getStatus()).toBe('reconnecting')
    expect(statuses).not.toContain('reconnect_failed')
  })

  it('exhausting every reconnect attempt surfaces the distinct reconnect_failed status', () => {
    const statuses: string[] = []
    const conn = new WebFormConnection(SCHEMA, { onStatusChange: (s) => statuses.push(s) })
    ;(conn as any).enableAutoReconnect = true
    ;(conn as any).status = 'reconnecting'
    ;(conn as any).connectedUrl = 'ws://x'
    // Already at the cap: the next close is the give-up point.
    ;(conn as any).reconnectAttempts = (conn as any).maxReconnectAttempts

    ;(conn as any).handleClose({ code: 1006 } as CloseEvent)

    expect(conn.getStatus()).toBe('reconnect_failed')
    expect(statuses).toContain('reconnect_failed')
  })

  it('an INTENTIONAL teardown (already disconnected) stays disconnected, not reconnect_failed', () => {
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).enableAutoReconnect = true
    ;(conn as any).status = 'disconnected'
    ;(conn as any).reconnectAttempts = 0

    ;(conn as any).handleClose({ code: 1000 } as CloseEvent)

    expect(conn.getStatus()).toBe('disconnected')
  })

  it('an intentional teardown with a STALE at-max counter still stays disconnected', () => {
    // Regression (fresh-eyes): the give-up branch must not fire just because the
    // counter is at max -- an already-"disconnected" status is the deliberate
    // teardown and must win, regardless of a leftover reconnectAttempts value.
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).enableAutoReconnect = true
    ;(conn as any).status = 'disconnected'
    ;(conn as any).reconnectAttempts = (conn as any).maxReconnectAttempts

    ;(conn as any).handleClose({ code: 1000 } as CloseEvent)

    expect(conn.getStatus()).toBe('disconnected')
    expect(conn.getStatus()).not.toBe('reconnect_failed')
  })

  it('an idle timeout takes the idle_timeout path, never reconnect_failed', () => {
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).enableAutoReconnect = true
    ;(conn as any).status = 'connected'
    ;(conn as any).idleTimedOut = true
    ;(conn as any).reconnectAttempts = (conn as any).maxReconnectAttempts

    ;(conn as any).handleClose({ code: 1000 } as CloseEvent)

    // idleTimedOut is checked before the exhaustion branch -> idle_timeout wins.
    expect(conn.getStatus()).toBe('idle_timeout')
  })
})
