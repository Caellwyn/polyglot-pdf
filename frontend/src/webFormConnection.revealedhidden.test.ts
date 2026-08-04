/**
 * bd polyglot-pdf-ubam, WS half: a `hidden: true` field whose `show_if` is
 * SATISFIED must be reachable through the two VOICE-facing gates.
 *
 * The sibling test (`__tests__/revealedHiddenField.test.ts`) pins the pure
 * functions -- navigation, progress, completion. It never constructs a
 * WebFormConnection, so the two gates that actually answer the live model were
 * unpinned: mutating either back to `field.hidden || !shouldShowField(...)`
 * left the ENTIRE frontend suite green (fresh-eyes review, 2026-08-04).
 *
 * These are the sites that make the field "unreachable by voice":
 *   - handleFieldUpdate's isAvailable gate -- reports the field LOCKED back to
 *     the model, so a spoken answer is rejected rather than filled.
 *   - the switch_field handler -- refuses navigation with reason:'hidden', so
 *     the model cannot even move to the question.
 *
 * Both are driven here through the real WS message path, not by calling the
 * private methods, so the assertions survive a refactor of either.
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
    queueMicrotask(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.()
    })
  }
  send = vi.fn()
  close = vi.fn(() => { this.readyState = MockWebSocket.CLOSED })
}

/**
 * `trigger` is plain; `revealed` is hidden:true but shown once trigger is
 * non-empty -- the exact shape all seven ubam sites used to exclude.
 */
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'trigger', name: 'trigger', spoken_name: 'Trigger', type: 'text' },
    {
      id: 'revealed',
      name: 'revealed',
      spoken_name: 'Revealed',
      type: 'text',
      hidden: true,
      validation: { required: true },
      show_if: { field: 'trigger', operator: 'is_not_empty' },
    },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['trigger', 'revealed'] }],
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
const flush = () => new Promise<void>(r => setTimeout(r, 0))

describe('WS gates for a revealed hidden field (bd polyglot-pdf-ubam)', () => {
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

  async function connected(): Promise<MockWebSocket> {
    conn = new WebFormConnection(SCHEMA, {})
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    return ws
  }

  /** Answer `trigger`, which satisfies `revealed`'s show_if. */
  function reveal(ws: MockWebSocket): void {
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { trigger: 'yes' } }),
    })
  }

  it('ACCEPTS a spoken value for the revealed field (not reported as locked)', async () => {
    const ws = await connected()
    reveal(ws)
    await flush()

    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { revealed: 'an answer' } }),
    })
    await flush()

    // The value must actually land in client state -- the gate's real effect.
    const stored = conn!.getState().fieldValues['revealed']
    expect(stored?.value).toBe('an answer')

    // ...and nothing may report it back to the model as locked/unavailable.
    const locked = sentMessages(ws).filter(m =>
      JSON.stringify(m).includes('locked') || JSON.stringify(m).includes('lockedReason')
    )
    expect(locked).toEqual([])
  })

  it('STILL locks the field while its show_if is UNMET', async () => {
    // The other half: without the trigger answered, `revealed` is genuinely not
    // shown and must stay locked -- or the fix would have opened a real hole.
    const ws = await connected()
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { revealed: 'too early' } }),
    })
    await flush()
    expect(conn!.getState().fieldValues['revealed']?.value).toBeUndefined()
  })

  it('ALLOWS switch_field navigation to the revealed field', async () => {
    const ws = await connected()
    reveal(ws)
    await flush()
    ws.send.mockClear()

    ws.onmessage?.({
      data: JSON.stringify({
        type: 'switch_field', field: 'revealed', request_id: 'req-1',
      }),
    })
    await flush()

    const responses = ofType(ws, 'switch_field_response')
    expect(responses).toHaveLength(1)
    // The bug: this came back found:false with reason 'hidden'.
    expect(responses[0].reason).not.toBe('hidden')
    expect(responses[0].found).toBe(true)
  })

  it('STILL refuses switch_field while the show_if is UNMET', async () => {
    const ws = await connected()
    ws.send.mockClear()

    ws.onmessage?.({
      data: JSON.stringify({
        type: 'switch_field', field: 'revealed', request_id: 'req-2',
      }),
    })
    await flush()

    const responses = ofType(ws, 'switch_field_response')
    expect(responses).toHaveLength(1)
    expect(responses[0].found).toBe(false)
    expect(responses[0].reason).toBe('hidden')
  })
})
