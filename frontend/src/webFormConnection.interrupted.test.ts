/**
 * Coverage for WebFormConnection `interrupted` handling (bd polyglot-pdf-s7uf).
 *
 * Gemini stops generating the moment the user barges in; the backend forwards
 * that as {type:"interrupted"}. handleMessage must clear the STAGING audioQueue
 * (chunks received but not yet handed to the audio manager) and invoke
 * onInterrupted so the consumer drains the SCHEDULED playback too -- two queues
 * exist, and clearing only one leaves ghost audio. Without this the dead
 * generation's tail keeps playing, which is why barge-in felt broken.
 *
 * Modeled on webFormConnection.goaway.test.ts (dispatch-style, no socket).
 * ASCII only. jsdom env.
 */

import { describe, it, expect, beforeEach } from 'vitest'
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

describe('WebFormConnection interrupted dispatch (bd polyglot-pdf-s7uf)', () => {
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

  it('clears the staging audioQueue and fires onInterrupted', async () => {
    let fired = 0
    const conn = new WebFormConnection(SCHEMA, { onInterrupted: () => { fired++ } })
    ;(conn as any).audioQueue = [new ArrayBuffer(4), new ArrayBuffer(4)]

    await (conn as any).handleMessage(msg({ type: 'interrupted' }))

    expect((conn as any).audioQueue).toEqual([])
    expect(fired).toBe(1)
  })

  it('still clears the queue when no onInterrupted is registered', async () => {
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).audioQueue = [new ArrayBuffer(4)]

    await expect(
      (conn as any).handleMessage(msg({ type: 'interrupted' }))
    ).resolves.toBeUndefined()
    expect((conn as any).audioQueue).toEqual([])
  })

  it('does not set the idle-timeout no-reconnect flag', async () => {
    // An interruption is a normal conversational event on a LIVE connection --
    // it must never be confused with a connection-lifecycle close.
    const conn = new WebFormConnection(SCHEMA, { onInterrupted: () => {} })
    await (conn as any).handleMessage(msg({ type: 'interrupted' }))
    expect((conn as any).idleTimedOut).toBe(false)
  })
})
