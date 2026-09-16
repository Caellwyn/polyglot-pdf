/**
 * Regression tests for auth-token plumbing on (re)connect (bd polyglot-pdf-wq0).
 *
 * The backend /ws/fill gate rejects tokenless connections with HTTP 403. The
 * reconnect paths (startSection, attemptReconnect) used to call connect() with
 * no token, so the post-disclaimer first-section switch -- the first reconnect
 * after auth was added -- got 403 and the socket closed with code 1006. These
 * tests pin the fix: connect() must fetch a fresh token via the registered
 * getToken callback even when called with no explicit token argument.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { WebFormConnection, stripToken } from './webFormConnection'
import type { FormSchema } from './schema-forms/types/schema'

// Minimal mock WebSocket that records the URL it was constructed with and
// auto-fires onopen so connect()'s promise resolves.
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
    // Fire onopen on the next microtask so the connect() listeners are attached.
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

function firstFrameToken(): string | undefined {
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  const first = ws.send.mock.calls[0]?.[0]
  return first ? JSON.parse(first as string).token : undefined
}

function lastUrl(): string {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1].url
}

describe('WebFormConnection auth-token plumbing (bd polyglot-pdf-wq0)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    // sessionStorage is touched by SchemaFormStateManager during construction.
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

  it('sends the token from getToken in the FIRST FRAME, never on the URL, when connect() is called WITHOUT an explicit token (reconnect path)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    conn.setGetToken(async () => 'fresh-token-123')

    // No token argument -- mirrors startSection()/attemptReconnect() calling connect(wsUrl).
    await conn.connect('wss://example/ws/fill')

    expect(lastUrl()).not.toContain('token=')
    expect(firstFrameToken()).toBe('fresh-token-123')
  })

  it('re-fetches a fresh token on each reconnect (covers token expiry)', async () => {
    let n = 0
    const conn = new WebFormConnection(SCHEMA)
    conn.setGetToken(async () => `token-${++n}`)

    await conn.connect('wss://example/ws/fill')
    expect(firstFrameToken()).toBe('token-1')
    expect(lastUrl()).not.toContain('token=')

    conn.disconnect()
    await conn.connect('wss://example/ws/fill')
    expect(firstFrameToken()).toBe('token-2')
  })

  it('strips a stale baked-in token from the URL and sends the fresh one in the first frame', async () => {
    const conn = new WebFormConnection(SCHEMA)
    conn.setGetToken(async () => 'fresh')

    // connectedUrl-style URL that already carries a stale token.
    await conn.connect('wss://example/ws/fill?token=STALE')

    const url = lastUrl()
    expect(url).not.toContain('token=')
    expect(url).not.toContain('STALE')
    expect(firstFrameToken()).toBe('fresh')
  })

  it('strips a stale token that is the FIRST of several params without leaving ?& (regression for the strip edge case)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    conn.setGetToken(async () => 'fresh')

    // token first, with trailing params -- the case the old regex mangled into "?&".
    await conn.connect('wss://example/ws/fill?token=STALE&version=2')

    const url = lastUrl()
    expect(url).not.toContain('STALE')
    expect(url).not.toContain('?&')
    expect(url).toContain('version=2')
    expect(url).not.toContain('token=')
    expect(firstFrameToken()).toBe('fresh')
  })

  it('falls back to the last-known token when getToken throws', async () => {
    let calls = 0
    const conn = new WebFormConnection(SCHEMA)
    conn.setGetToken(async () => {
      calls++
      if (calls === 1) return 'good-token'
      throw new Error('network blip')
    })

    await conn.connect('wss://example/ws/fill')
    expect(firstFrameToken()).toBe('good-token')

    conn.disconnect()
    // Second connect: getToken throws -> fall back to cached 'good-token'.
    await conn.connect('wss://example/ws/fill')
    expect(firstFrameToken()).toBe('good-token')
    expect(lastUrl()).not.toContain('token=')
  })

  it('explicit token argument still wins (back-compat)', async () => {
    const conn = new WebFormConnection(SCHEMA)
    conn.setGetToken(async () => 'callback-token')

    await conn.connect('wss://example/ws/fill', 10000, 'explicit-token')

    expect(firstFrameToken()).toBe('explicit-token')
    expect(lastUrl()).not.toContain('token=')
    expect(JSON.stringify(MockWebSocket.instances[MockWebSocket.instances.length - 1].send.mock.calls[0])).not.toContain('callback-token')
  })
})

describe('stripToken (bd polyglot-pdf-wq0)', () => {
  it('returns the URL unchanged when there is no token', () => {
    expect(stripToken('wss://x/ws')).toBe('wss://x/ws')
    expect(stripToken('wss://x/ws?a=b')).toBe('wss://x/ws?a=b')
  })
  it('strips a token that is the only param', () => {
    expect(stripToken('wss://x/ws?token=abc')).toBe('wss://x/ws')
  })
  it('strips a token that is first of several (no dangling ?&)', () => {
    expect(stripToken('wss://x/ws?token=abc&a=b')).toBe('wss://x/ws?a=b')
  })
  it('strips a token that is in the middle', () => {
    expect(stripToken('wss://x/ws?a=b&token=abc&c=d')).toBe('wss://x/ws?a=b&c=d')
  })
  it('strips a token that is last (no trailing separator)', () => {
    expect(stripToken('wss://x/ws?a=b&token=abc')).toBe('wss://x/ws?a=b')
  })
})

describe('WebFormConnection handshake send sites (sprint 23 C2)', () => {
  it('EVERY handshake send site carries the token (connect, continuous-session switch, legacy switch)', async () => {
    // A static pin over the source: the backend verifies the first frame of
    // every socket, and a section switch opens a new socket, so a handshake
    // literal or spread without `token: this.lastToken` is a refused switch.
    const fs = await import('node:fs')
    const path = await import('node:path')
    const src = fs.readFileSync(path.resolve(__dirname, 'webFormConnection.ts'), 'utf8')
    const sends = (src.match(/type: ["']handshake["']|getHandshakePayload\(/g) ?? []).length
    const withToken = (src.match(/token: this\.lastToken/g) ?? []).length
    expect(sends).toBeGreaterThanOrEqual(3)
    expect(withToken).toBe(sends)
  })
})
