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

// One section, two fields. Editing f_a manually leaves it FILLED BUT UNVERIFIED
// (bd polyglot-pdf-uum5g), and Priority 1 (confirm a filled field) outranks
// Priority 2 (fill an empty one) -- so f_a is offered again, not f_b. These tests
// still do their real job: proving the hint is computed from POST-edit state
// rather than a stale copy.
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
   * (UNVERIFIED, with the search origin moved) and save -- without touching
   * conn.state. */
  function persistManualEdit(fieldId: string, value: string): void {
    const persisted = SchemaFormStateManager.load()!
    // Mirror what PRODUCTION's onManualEdit actually does (connection.ts): store
    // the value UNVERIFIED (bd polyglot-pdf-uum5g -- typing is not an assertion)
    // and move the search origin to the edited field (bd polyglot-pdf-a08po).
    //
    // This helper used to hard-code confirmed:true and skip setSearchOrigin, so
    // it SUPPLIED the very state production is supposed to supply -- and kept
    // three tests green through a behaviour change that altered every hint they
    // assert on.
    const edited = SchemaFormStateManager.updateField(persisted, fieldId, value, {
      confirmed: false,
    })
    SchemaFormStateManager.save(SchemaFormStateManager.setSearchOrigin(edited, fieldId))
  }

  it('computes the hint from the POST-edit state (re-offers the unverified f_a)', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    persistManualEdit('f_a', 'AA')
    conn!.sendManualFieldUpdate('f_a', 'Field A', 'AA')

    const msgs = ofType(ws, 'manual_field_update')
    expect(msgs).toHaveLength(1)
    // f_a is filled but UNVERIFIED, so it is re-offered to be confirmed --
    // Priority 1 beats the empty f_b. This asserted f_b until uum5g, when the
    // helper still hard-coded confirmed:true and so simulated the old behaviour.
    // The hint being computed from POST-edit state is what this test pins, and
    // that still holds: a stale this.state carries no search origin at all.
    expect(msgs[0].next_field_hint).toContain("field_id: 'f_a'")
  })

  it('in DTI mode, rides the NEXT field full schema on the message', async () => {
    const ws = await connected(ONE_SECTION_SCHEMA)
    ;(conn as any).dtiModeEnabled = true
    persistManualEdit('f_a', 'AA')
    conn!.sendManualFieldUpdate('f_a', 'Field A', 'AA')

    const msgs = ofType(ws, 'manual_field_update')
    expect(msgs).toHaveLength(1)
    expect(msgs[0].next_field_schema).toBeDefined()
    // f_a again, for the same reason as above: filled but unverified outranks
    // empty. What this test actually pins is the PAIRING rule below.
    expect(msgs[0].next_field_schema.id).toBe('f_a')
    // Hint and schema must refer to the SAME field (the Codex PR #229 rule).
    expect(msgs[0].next_field_hint).toContain("field_id: 'f_a'")
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
    // TYPING both fields no longer completes the form (bd polyglot-pdf-uum5g) --
    // that is the whole point of the bead, so they must be VERIFIED here. This
    // test used to reach "complete" by typing, which silently stopped testing
    // the complete-form branch the moment typing stopped verifying.
    persistManualEdit('f_a', 'AA')
    persistManualEdit('f_b', 'BB')
    let st = SchemaFormStateManager.load()!
    st = SchemaFormStateManager.confirmField(st, 'f_a', 'ai_voice')
    st = SchemaFormStateManager.confirmField(st, 'f_b', 'ai_voice')
    SchemaFormStateManager.save(st)
    conn!.reloadState()
    conn!.sendManualFieldUpdate('f_b', 'Field B', 'BB')

    const msgs = ofType(ws, 'manual_field_update')
    expect(msgs).toHaveLength(1)
    expect(msgs[0].next_field_hint).toBeNull()
    expect('next_field_schema' in msgs[0]).toBe(false)
  })
})
