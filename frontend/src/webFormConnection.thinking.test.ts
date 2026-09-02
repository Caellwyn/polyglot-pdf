/**
 * Tests for the thinking-indicator signal (bd polyglot-pdf-wpw.5).
 *
 * The backend drives a calm "thinking" indicator via an `agent_processing` WS
 * message (true on a real user turn -- BOTH VAD modes -- false at the agent's first
 * response audio / turn end). The client forwards it via onThinkingChange and
 * clears it defensively on first audio, turn_complete, and any move off
 * "connected" so it can never stick on.
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
    queueMicrotask(() => { this.readyState = MockWebSocket.OPEN; this.onopen?.() })
  }
  send = vi.fn()
  close = vi.fn(() => { this.readyState = MockWebSocket.CLOSED })
}

const SCHEMA: FormSchema = {
  source: 'web',
  fields: [{ id: 'f1', name: 'f1', spoken_name: 'F1', type: 'text' }],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1'] }],
} as unknown as FormSchema

function lastWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

function fire(ws: MockWebSocket, msg: any): void {
  ws.onmessage?.({ data: JSON.stringify(msg) })
}

describe('WebFormConnection thinking indicator (bd polyglot-pdf-wpw.5)', () => {
  let onThinkingChange: ReturnType<typeof vi.fn>

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
      key: () => null, length: 0,
    } as unknown as Storage
    onThinkingChange = vi.fn()
  })

  async function connect(): Promise<MockWebSocket> {
    const conn = new WebFormConnection(SCHEMA, { onThinkingChange })
    await conn.connect('wss://example/ws/fill')
    // Drive to "connected" so the safety-clear-on-status tests start connected.
    const ws = lastWs()
    fire(ws, { type: 'session_ready', session_id: 's', ephemeral: true })
    onThinkingChange.mockClear()
    return ws
  }

  it('agent_processing:true -> onThinkingChange(true); :false -> (false)', async () => {
    const ws = await connect()

    fire(ws, { type: 'agent_processing', processing: true })
    expect(onThinkingChange).toHaveBeenLastCalledWith(true)

    fire(ws, { type: 'agent_processing', processing: false })
    expect(onThinkingChange).toHaveBeenLastCalledWith(false)
  })

  it('dedups: a repeated processing:true does not re-fire the callback', async () => {
    const ws = await connect()

    fire(ws, { type: 'agent_processing', processing: true })
    fire(ws, { type: 'agent_processing', processing: true })

    const trueCalls = onThinkingChange.mock.calls.filter(c => c[0] === true)
    expect(trueCalls).toHaveLength(1)
  })

  it('turn_complete clears thinking (text-only turn safety)', async () => {
    const ws = await connect()
    fire(ws, { type: 'agent_processing', processing: true })
    onThinkingChange.mockClear()

    fire(ws, { type: 'turn_complete' })
    expect(onThinkingChange).toHaveBeenLastCalledWith(false)
  })

  it('a response audio frame clears thinking (belt-and-suspenders)', async () => {
    const ws = await connect()
    fire(ws, { type: 'agent_processing', processing: true })
    onThinkingChange.mockClear()

    // Binary audio frame from the server.
    ws.onmessage?.({ data: new ArrayBuffer(8) })
    // handleAudioFrame is async; let microtasks flush.
    await Promise.resolve()
    await Promise.resolve()
    expect(onThinkingChange).toHaveBeenLastCalledWith(false)
  })

  it('a move OFF connected (error) clears a stuck thinking indicator', async () => {
    const ws = await connect()
    fire(ws, { type: 'agent_processing', processing: true })
    onThinkingChange.mockClear()

    // Simulate a socket error -> status leaves "connected".
    ws.onerror?.(new Event('error'))
    expect(onThinkingChange).toHaveBeenLastCalledWith(false)
  })

  it('sendActivityStart (barge-in / new turn) clears a pending thinking indicator', async () => {
    const conn = new WebFormConnection(SCHEMA, { onThinkingChange })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    fire(ws, { type: 'session_ready', session_id: 's', ephemeral: true })
    fire(ws, { type: 'agent_processing', processing: true })
    onThinkingChange.mockClear()

    // User starts a new turn (barge-in over the still-"thinking" window).
    conn.sendActivityStart()
    expect(onThinkingChange).toHaveBeenLastCalledWith(false)
  })

  it('a server {type:error} message clears a pending thinking indicator (Codex PR #273)', async () => {
    const conn = new WebFormConnection(SCHEMA, { onThinkingChange })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    fire(ws, { type: 'session_ready', session_id: 's', ephemeral: true })
    fire(ws, { type: 'agent_processing', processing: true })
    onThinkingChange.mockClear()

    // A server error that does NOT change status (no section switch in flight).
    fire(ws, { type: 'error', code: 'some_error', message: 'boom' })
    expect(onThinkingChange).toHaveBeenLastCalledWith(false)
  })

  it('fires window.vffOnAgentProcessing on each agent_processing message (bd polyglot-pdf-fa4x)', async () => {
    const observed: boolean[] = []
    // jsdom provides a real `window`; set the harness hook on it.
    ;(window as any).vffOnAgentProcessing = (p: boolean) => { observed.push(p) }
    try {
      const ws = await connect()
      fire(ws, { type: 'agent_processing', processing: true })
      fire(ws, { type: 'agent_processing', processing: false })
      // The thinking START (true) and its CLEAR (false) both reach the harness
      // observer, so the E2E harness can assert the indicator armed without a mic.
      expect(observed).toEqual([true, false])
    } finally {
      delete (window as any).vffOnAgentProcessing
    }
  })

  it('getThinking() reflects the current state', async () => {
    const conn = new WebFormConnection(SCHEMA, { onThinkingChange })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    fire(ws, { type: 'session_ready', session_id: 's', ephemeral: true })

    expect(conn.getThinking()).toBe(false)
    fire(ws, { type: 'agent_processing', processing: true })
    expect(conn.getThinking()).toBe(true)
    fire(ws, { type: 'agent_processing', processing: false })
    expect(conn.getThinking()).toBe(false)
  })
})
