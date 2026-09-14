/**
 * Browser PII hygiene on WebFormConnection (bd polyglot-pdf-8v8i7).
 *
 * Two things pinned here:
 *  1. send()'s not-OPEN and "suspicious" console.error branches log only
 *     {type, size} -- never the raw message body, which can carry a field
 *     value or a client-link token. Both are console.error, so the
 *     build-time `pure: ['console.log', 'console.debug']` backstop does NOT
 *     strip them; the redaction has to hold in source.
 *  2. reset() no longer exists -- it was dead code (no caller anywhere in
 *     the app) that combined disconnect() with a raw
 *     SchemaFormStateManager.clear() outside the documented Clear-form path.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
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

const SCHEMA: FormSchema = {
  source: 'web',
  fields: [],
  sections: [{ id: 's1', label: 'S1', order: 1 }],
} as unknown as FormSchema

describe('WebFormConnection browser PII hygiene (bd polyglot-pdf-8v8i7)', () => {
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

  it('does not exist as a method any more (reset() was dead code, deleted)', () => {
    const conn = new WebFormConnection(SCHEMA)
    expect((conn as any).reset).toBeUndefined()
  })

  it('redacts the not-OPEN send() error to {type, size} -- never the raw message', () => {
    const conn = new WebFormConnection(SCHEMA)
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    // No connect() call -- this.ws is null, so send() takes the not-OPEN branch.
    conn.send({ type: 'confirm_field', field_id: 'f1', value: 'super-secret-answer' })

    expect(spy).toHaveBeenCalled()
    const loggedArgs = spy.mock.calls[0]
    const serialized = JSON.stringify(loggedArgs)
    expect(serialized).not.toContain('super-secret-answer')
    expect(serialized).not.toContain('field_id')
    // The redacted payload is the last argument to console.error.
    const payload = loggedArgs[loggedArgs.length - 1]
    expect(payload).toMatchObject({ type: 'confirm_field' })
    expect(typeof payload.size).toBe('number')

    spy.mockRestore()
  })

  it('redacts the "suspicious" (no type) send() branch to {type, size} -- never keys/preview/stack', async () => {
    const conn = new WebFormConnection(SCHEMA)
    conn.setGetToken(async () => 'fresh-token')
    await conn.connect('wss://example/ws/fill')

    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    conn.send({ field_id: 'f1', value: 'super-secret-answer', linkToken: 'abc.def' } as any)

    expect(spy).toHaveBeenCalled()
    const loggedArgs = spy.mock.calls[0]
    const serialized = JSON.stringify(loggedArgs)
    expect(serialized).not.toContain('super-secret-answer')
    expect(serialized).not.toContain('abc.def')
    expect(serialized).not.toContain('field_id')
    const payload = loggedArgs[loggedArgs.length - 1]
    expect(Object.keys(payload).sort()).toEqual(['size', 'type']);

    spy.mockRestore()
  })
})
