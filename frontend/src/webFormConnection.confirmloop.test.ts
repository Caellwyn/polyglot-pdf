/**
 * Regression tests for the confirm_field / next_field_hint loop-breaker
 * (bd polyglot-pdf-0y7).
 *
 * SchemaFormStateManager.confirmField no-ops when a field has no value, so the
 * backend could re-request confirm_field for the SAME unconfirmable field
 * forever (computeNextField keeps returning it) while Gemini stalls. The fix in
 * handleConfirmFieldRequest counts consecutive confirms that did NOT actually
 * confirm the field and, at CONFIRM_FAIL_LIMIT (2), breaks the spin by sending a
 * level-1 recovery_prompt instead of falling through to another no-op cycle.
 * A successful confirm (or a switch to a different field) resets the streak.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import type { FormSchema } from './schema-forms/types/schema'

// Minimal mock WebSocket: OPEN immediately so send()/sendRecoveryPrompt work.
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3
  url: string
  readyState = MockWebSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((e: any) => void) | null = null
  onerror: ((e: any) => void) | null = null
  onclose: ((e: any) => void) | null = null
  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }
  send = vi.fn()
  close = vi.fn(() => { this.readyState = MockWebSocket.CLOSED })
}

// One section, one text field. The field has NO value seeded -> confirmField
// no-ops -> the loop scenario.
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'f1', name: 'A-Number', type: 'text', section_id: 's1', order: 1, validation: { required: true } },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1 }],
} as unknown as FormSchema

function sentMessages(ws: MockWebSocket): any[] {
  return ws.send.mock.calls
    .map(c => c[0])
    .map((m: any) => { try { return typeof m === 'string' ? JSON.parse(m) : m } catch { return m } })
}

describe('WebFormConnection confirm-loop breaker (bd polyglot-pdf-0y7)', () => {
  let conn: WebFormConnection
  let ws: MockWebSocket

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

    conn = new WebFormConnection(SCHEMA)
    ws = new MockWebSocket('wss://x/ws/fill')
    // Attach the mock ws so send()/sendRecoveryPrompt have an OPEN socket.
    ;(conn as any).ws = ws
    ;(conn as any).state.currentSectionId = 's1'
  })

  async function confirm(fieldId: string) {
    await (conn as any).handleConfirmFieldRequest({ field_id: fieldId, confirmation_method: 'verbal' })
  }

  it('does NOT recovery-prompt on the first failed confirm (under the limit)', async () => {
    await confirm('f1')
    const recovery = sentMessages(ws).filter(m => m?.type === 'recovery_prompt')
    expect(recovery.length).toBe(0)
  })

  it('breaks the loop with a level-1 recovery_prompt after CONFIRM_FAIL_LIMIT failures on the same field', async () => {
    await confirm('f1') // fail 1
    await confirm('f1') // fail 2 -> break
    const recovery = sentMessages(ws).filter(m => m?.type === 'recovery_prompt')
    expect(recovery.length).toBe(1)
    expect(recovery[0].level).toBe(1)
  })

  it('re-arms after firing (does not spam a recovery prompt every subsequent cycle)', async () => {
    await confirm('f1') // fail 1
    await confirm('f1') // fail 2 -> break (counter reset)
    await confirm('f1') // fail 1 again (re-armed)
    let recovery = sentMessages(ws).filter(m => m?.type === 'recovery_prompt')
    expect(recovery.length).toBe(1) // still just the one
    await confirm('f1') // fail 2 again -> break again
    recovery = sentMessages(ws).filter(m => m?.type === 'recovery_prompt')
    expect(recovery.length).toBe(2)
  })

  it('resets the failure streak when a field actually confirms', async () => {
    await confirm('f1') // fail 1
    // Seed a value so confirmField succeeds this time.
    ;(conn as any).state.fieldValues['f1'] = { value: 'A123456789', confirmed: false }
    await confirm('f1') // now confirms -> streak resets, no recovery prompt
    const recovery = sentMessages(ws).filter(m => m?.type === 'recovery_prompt')
    expect(recovery.length).toBe(0)
    // A subsequent single failure on a fresh (valueless) field is fail-1, not fail-2.
    ;(conn as any).state.fieldValues = {}
    await confirm('f1')
    expect(sentMessages(ws).filter(m => m?.type === 'recovery_prompt').length).toBe(0)
  })

  it('tracks failures per field id (an intervening field resets the streak; A-B-A does not accumulate)', async () => {
    await confirm('f1') // fail 1 on f1
    await confirm('fX') // fail 1 on a different field -> f1's streak is gone
    await confirm('f1') // back to f1: this is fail 1 again (NOT fail 2), so no break
    const recovery = sentMessages(ws).filter(m => m?.type === 'recovery_prompt')
    expect(recovery.length).toBe(0)
  })

  it('surfaces the stall via onError when the loop is broken (works even though the backend recovery channel is currently broken, bd zy3)', async () => {
    // Inject an onError spy onto the existing connection's callbacks (the
    // beforeEach already set up a clean sessionStorage + connection).
    const onError = vi.fn()
    ;(conn as any).callbacks.onError = onError
    await confirm('f1') // fail 1
    await confirm('f1') // fail 2 -> break -> onError fires
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
    expect(String(onError.mock.calls[0][0].message)).toContain('f1')
  })

  it('resets the streak on a section switch (no stale count carried into the next section)', async () => {
    ;(conn as any).confirmFailField = 'f1'
    ;(conn as any).confirmFailCount = 1
    // switchToSection clears the streak before doing its work; stub out the parts
    // that need a live socket so we only exercise the reset.
    try {
      await (conn as any).switchToSection('s1', '')
    } catch {
      // switchToSection may throw later (no real session) -- the reset happens first.
    }
    expect((conn as any).confirmFailField).toBeNull()
    expect((conn as any).confirmFailCount).toBe(0)
  })

  it('resets the streak on startSection too (the completeSection transition path, Copilot PR #111)', async () => {
    ;(conn as any).confirmFailField = 'f1'
    ;(conn as any).confirmFailCount = 1
    try {
      await (conn as any).startSection('s1', 'wss://x/ws/fill')
    } catch {
      // startSection drives a reconnect that the mock can't complete; the reset
      // runs first (before any awaited work).
    }
    expect((conn as any).confirmFailField).toBeNull()
    expect((conn as any).confirmFailCount).toBe(0)
  })
})
