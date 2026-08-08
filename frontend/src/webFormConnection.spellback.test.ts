/**
 * Tests for the deterministic spell-back handler (bd polyglot-pdf-22h1f).
 *
 * The backend's name_spellback tool asks the client to play a Cloud TTS
 * letter-by-letter clip of the CURRENT field's stored value. The tool carries
 * no field_id (nothing for the model to hallucinate); this handler resolves
 * the current field itself, reads the stored value (through the []-alias
 * fallback), delegates playback to the onSpellbackRequest callback, and acks
 * spellback_response in EVERY path -- an unacked request parks the model until
 * the backend's timeout.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { WebFormConnection, type SpellbackPlaybackResult } from './webFormConnection'
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
  fields: [
    {
      id: 'p1_family_name',
      name: 'Family Name',
      spoken_name: 'family name',
      type: 'text',
      validation: { required: true },
    },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['p1_family_name'] }],
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

function fireSpellback(ws: MockWebSocket, requestId = 'req-sb-1'): void {
  ws.onmessage?.({
    data: JSON.stringify({ type: 'spellback', request_id: requestId }),
  })
}

function spellbackAcks(ws: MockWebSocket): any[] {
  return sentMessages(ws).filter(m => m.type === 'spellback_response')
}

async function settle(): Promise<void> {
  // The handler awaits the playback promise; give the microtask queue a few
  // turns plus a macrotask so every await chain resolves.
  await Promise.resolve()
  await Promise.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
}

describe('WebFormConnection spellback handler (bd polyglot-pdf-22h1f)', () => {
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

  async function connected(
    onSpellbackRequest?: (value: string, fieldId: string) => Promise<SpellbackPlaybackResult>
  ): Promise<{ conn: WebFormConnection; ws: MockWebSocket }> {
    const conn = new WebFormConnection(SCHEMA, { onSpellbackRequest })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send
    return { conn, ws }
  }

  function fillField(ws: MockWebSocket, value = 'Nguyen'): void {
    // Production field_update path (keyed by field NAME).
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { 'Family Name': value } }),
    })
  }

  it('plays the CURRENT field stored value and acks the playback outcome verbatim', async () => {
    const playback = vi.fn(async (): Promise<SpellbackPlaybackResult> => ({
      status: 'delivered', playback_ms: 5100, fetch_ms: 240,
    }))
    const { ws } = await connected(playback)

    fillField(ws, 'Nguyen')
    await settle()
    ws.send.mockClear()

    fireSpellback(ws)
    await settle()

    // Playback got the STORED value + the resolved current field id.
    expect(playback).toHaveBeenCalledTimes(1)
    expect(playback).toHaveBeenCalledWith('Nguyen', 'p1_family_name')

    const acks = spellbackAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].request_id).toBe('req-sb-1')
    expect(acks[0].status).toBe('delivered')
    expect(acks[0].playback_ms).toBe(5100)
    expect(acks[0].fetch_ms).toBe(240)
    // PII guard: the ack must never carry the field value.
    expect(JSON.stringify(acks[0])).not.toContain('Nguyen')
  })

  it('acks interrupted verbatim (the PTT barge-in outcome)', async () => {
    const playback = vi.fn(async (): Promise<SpellbackPlaybackResult> => ({
      status: 'interrupted', playback_ms: 900,
    }))
    const { ws } = await connected(playback)

    fillField(ws)
    await settle()
    ws.send.mockClear()

    fireSpellback(ws)
    await settle()

    const acks = spellbackAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].status).toBe('interrupted')
  })

  it('acks error/no_value WITHOUT invoking playback when the current field is empty', async () => {
    const playback = vi.fn()
    const { ws } = await connected(playback as any)

    fireSpellback(ws)
    await settle()

    expect(playback).not.toHaveBeenCalled()
    const acks = spellbackAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].status).toBe('error')
    expect(acks[0].reason).toBe('no_value')
  })

  it('acks error/no_playback_path when no callback is wired', async () => {
    const { ws } = await connected(undefined)

    fillField(ws)
    await settle()
    ws.send.mockClear()

    fireSpellback(ws)
    await settle()

    const acks = spellbackAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].status).toBe('error')
    expect(acks[0].reason).toBe('no_playback_path')
  })

  it('still acks (error/playback_exception) when the playback callback rejects', async () => {
    // The callback contract is resolve-never-reject; this pins the belt-and-
    // braces path so a callback bug can never strand the tool round-trip.
    const playback = vi.fn(async (): Promise<SpellbackPlaybackResult> => {
      throw new Error('boom')
    })
    const { ws } = await connected(playback)

    fillField(ws)
    await settle()
    ws.send.mockClear()

    fireSpellback(ws)
    await settle()

    const acks = spellbackAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].status).toBe('error')
    expect(acks[0].reason).toBe('playback_exception')
  })

  it('resolves a value stored under the []-alias key (bd 5k52 parity)', async () => {
    const playback = vi.fn(async (): Promise<SpellbackPlaybackResult> => ({
      status: 'delivered',
    }))
    const { conn, ws } = await connected(playback)

    // Seed the value under the bracketed alias directly (mirrors how an
    // alias-consolidated store can hold the answer under the other variant).
    ;(conn as any).state.fieldValues['p1_family_name[]'] = {
      value: 'Okafor', lastModified: Date.now(),
    }
    // Clear persisted state so the handler's refresh/reconcile step (which
    // consolidates alias pairs onto the schema variant) cannot mask a broken
    // alias READ -- this test pins the read layer itself (per-layer testing:
    // the reconcile layer is pinned by webFormConnection.statereconcile tests).
    global.sessionStorage.clear()

    fireSpellback(ws)
    await settle()

    expect(playback).toHaveBeenCalledWith('Okafor', 'p1_family_name')
    expect(spellbackAcks(ws)[0].status).toBe('delivered')
  })
})
