/**
 * bd polyglot-pdf-ezg2: manual_field_update must carry the NEXT field's hint and
 * (in DTI mode) its full schema, computed from the POST-edit persisted state.
 *
 * A manual edit is applied+saved to sessionStorage by the edit handler
 * (connection.ts onManualEdit) WITHOUT mutating WebFormConnection.this.state, and
 * it never triggers the confirm_field next-field round-trip that normally carries
 * the next field's schema to the backend. So sendManualFieldUpdate must (a)
 * refresh this.state from the persisted snapshot BEFORE computing the next field
 * -- or the hint points back at the just-edited field -- and (b) in DTI mode ride
 * the next field's schema on the message so the backend can re-establish the
 * current-field coercion pointer + validation entry (form_filling_service.
 * send_manual_field_update -> merge_field_schema).
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

// One section, two fields: editing f_a manually makes f_b the next field.
const ONE_SECTION_SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'f_a', name: 'fielda', spoken_name: 'Field A', type: 'text' },
    { id: 'f_b', name: 'fieldb', spoken_name: 'Field B', type: 'text' },
  ],
  sections: [{ id: 'only', label: 'Only', order: 1, fields: ['f_a', 'f_b'] }],
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

describe('WebFormConnection manual_field_update next-field rider (bd polyglot-pdf-ezg2)', () => {
  let conn: WebFormConnection | null = null

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

  afterEach(() => {
    conn?.disconnect()
    conn = null
  })

  async function connected(schema: FormSchema): Promise<MockWebSocket> {
    conn = new WebFormConnection(schema)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send
    return ws
  }

  /** Simulate connection.ts onManualEdit: apply the edit to the PERSISTED state
   * (confirmed via manual_edit) and save -- without touching conn.state. */
  function persistManualEdit(fieldId: string, value: string): void {
    const persisted = SchemaFormStateManager.load()!
    const edited = SchemaFormStateManager.updateField(persisted, fieldId, value, {
      confirmed: true,
      confirmationMethod: 'manual_edit',
    })
    SchemaFormStateManager.save(edited)
  }

  it('computes the hint from the POST-edit state (points at f_b, not the just-edited f_a)', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    persistManualEdit('f_a', 'AA')
    conn!.sendManualFieldUpdate('f_a', 'Field A', 'AA')

    const msgs = ofType(ws, 'manual_field_update')
    expect(msgs).toHaveLength(1)
    // The just-edited f_a is auto-confirmed, so the next field is f_b; a stale
    // this.state would have produced a hint for f_a.
    expect(msgs[0].next_field_hint).toContain("field_id: 'f_b'")
    expect(msgs[0].next_field_hint).not.toContain("field_id: 'f_a'")
  })

  it('in DTI mode, rides the NEXT field full schema on the message', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    ;(conn as any).dtiModeEnabled = true
    persistManualEdit('f_a', 'AA')
    conn!.sendManualFieldUpdate('f_a', 'Field A', 'AA')

    const msgs = ofType(ws, 'manual_field_update')
    expect(msgs).toHaveLength(1)
    expect(msgs[0].next_field_schema).toBeDefined()
    expect(msgs[0].next_field_schema.id).toBe('f_b')
    // Hint and schema must refer to the SAME field (the Codex PR #229 rule).
    expect(msgs[0].next_field_hint).toContain("field_id: 'f_b'")
  })

  it('outside DTI mode, sends NO next_field_schema key', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    persistManualEdit('f_a', 'AA')
    conn!.sendManualFieldUpdate('f_a', 'Field A', 'AA')

    const msgs = ofType(ws, 'manual_field_update')
    expect(msgs).toHaveLength(1)
    expect('next_field_schema' in msgs[0]).toBe(false)
  })

  it('in DTI mode with the form complete, sends no schema and a null hint', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    ;(conn as any).dtiModeEnabled = true
    persistManualEdit('f_a', 'AA')
    persistManualEdit('f_b', 'BB')
    conn!.sendManualFieldUpdate('f_b', 'Field B', 'BB')

    const msgs = ofType(ws, 'manual_field_update')
    expect(msgs).toHaveLength(1)
    expect(msgs[0].next_field_hint).toBeNull()
    expect('next_field_schema' in msgs[0]).toBe(false)
  })
})
