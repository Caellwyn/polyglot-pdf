/**
 * Coverage for WebFormConnection GoAway handling (bd polyglot-pdf-c5t).
 *
 * The Gemini Live server sends a GoAway before terminating the connection; the
 * backend forwards it as {type:"go_away", time_left}. These tests cover the FE
 * dispatch: handleMessage routes a go_away to the onGoAway callback with the
 * time_left, and -- unlike idle_timeout -- does NOT set the no-reconnect flag (a
 * GoAway is a server lifecycle reset; reconnect IS wanted). The reconnect POLICY
 * itself is a follow-on (bd polyglot-pdf-l3a.2); here we only assert the signal
 * reaches the consumer.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
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

describe('WebFormConnection GoAway handling (bd polyglot-pdf-c5t)', () => {
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
