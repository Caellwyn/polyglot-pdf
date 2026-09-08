/**
 * Coverage for WebFormConnection.setVoiceMode -- the wire half of the
 * manual/voice mode toggle (bd polyglot-pdf-wurj8).
 *
 * This method had NO test of its own. That mattered more than it looks: manual
 * mode is enforced at the BACKEND (the adapter drops the model's proactive turns
 * before they reach Gemini), so a mode that never reaches the socket is not
 * manual mode at all -- the UI shows "quiet" while the assistant keeps talking,
 * and keeps billing. The user-visible failure is indistinguishable from the
 * feature simply not working.
 *
 * These drive the REAL WebFormConnection against a socket mock, so they pin the
 * actual frame that goes out (its `type` and `mode` keys are a wire contract the
 * backend's `voice_mode` handler matches on), not merely that some method was
 * called.
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
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  send = ((data: any) => {
    this.sent.push(typeof data === 'string' ? data : '[binary]')
  }) as (data: any) => void

  close = () => {
    this.readyState = MockWebSocket.CLOSED
  }
}

async function connectAndOpen(conn: WebFormConnection, url = 'wss://example/ws/fill') {
  const p = conn.connect(url)
  const sock = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  sock.open()
  await p
  return sock
}

/** Every voice_mode frame the socket was asked to send, parsed. */
function voiceModeFrames(sock: MockWebSocket): Array<Record<string, unknown>> {
  return sock.sent
    .map((raw) => {
      try {
        return JSON.parse(raw) as Record<string, unknown>
      } catch {
        return null
      }
    })
    .filter((m): m is Record<string, unknown> => m !== null && m.type === 'voice_mode')
}

describe('WebFormConnection.setVoiceMode (bd polyglot-pdf-wurj8)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
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

  it('sends the manual mode as a voice_mode frame', async () => {
    const conn = new WebFormConnection(SCHEMA, {})
    const sock = await connectAndOpen(conn)

    conn.setVoiceMode('manual')

    expect(voiceModeFrames(sock)).toEqual([{ type: 'voice_mode', mode: 'manual' }])
  })

  it('sends voice mode the same way', async () => {
    const conn = new WebFormConnection(SCHEMA, {})
    const sock = await connectAndOpen(conn)

    conn.setVoiceMode('voice')

    expect(voiceModeFrames(sock)).toEqual([{ type: 'voice_mode', mode: 'voice' }])
  })

  it('carries the mode verbatim -- the backend matches on these exact strings', async () => {
    // The backend REJECTS any mode outside {"manual","voice"} rather than
    // coercing it, so a client that abbreviated or capitalised differently would
    // have its toggle silently refused.
    const conn = new WebFormConnection(SCHEMA, {})
    const sock = await connectAndOpen(conn)

    conn.setVoiceMode('manual')
    conn.setVoiceMode('voice')

    expect(voiceModeFrames(sock).map((m) => m.mode)).toEqual(['manual', 'voice'])
  })

  it('does not throw or send when the socket is not open', async () => {
    // Deliberately fire-and-forget: the mode is re-asserted on every reconnect
    // from the client's own state, so a send that misses a closed socket is
    // repaired by the reconnect rather than needing to be queued here. What must
    // NOT happen is a throw -- this is called straight from a click handler and
    // from the session-ready callback.
    const conn = new WebFormConnection(SCHEMA, {})
    const sock = await connectAndOpen(conn)
    sock.readyState = MockWebSocket.CLOSED

    expect(() => conn.setVoiceMode('manual')).not.toThrow()
    expect(voiceModeFrames(sock)).toEqual([])
  })

  it('does not throw before any connect', () => {
    const conn = new WebFormConnection(SCHEMA, {})

    expect(() => conn.setVoiceMode('manual')).not.toThrow()
  })
})
