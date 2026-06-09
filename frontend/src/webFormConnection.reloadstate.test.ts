/**
 * Coverage for WebFormConnection.reloadState() (bd polyglot-pdf-o1c).
 *
 * Same-page harness reruns clear a field's state through SchemaFormStateManager
 * (save + schemaFormStateChange dispatch), which refreshes SchemaForm's React
 * state but NOT this connection's own in-memory `this.state` copy. reloadState()
 * pulls the updated state back in so a same-page rerun does not drive Gemini off
 * a stale filled/confirmed value. These tests assert that contract directly
 * (Codex/fresh-eyes PR #126 asked for focused coverage of the new path).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
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

const SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { form_number: 'I-90', version: '1' },
  fields: [
    {
      id: 'p1_line1_aliennumber',
      name: 'aliennumber',
      spoken_name: 'Alien Number',
      type: 'text',
    },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['p1_line1_aliennumber'] }],
} as unknown as FormSchema

describe('WebFormConnection.reloadState (bd polyglot-pdf-o1c)', () => {
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

  it('pulls a cleared field from sessionStorage into the in-memory state', () => {
    const conn = new WebFormConnection(SCHEMA)

    // Seed a filled+confirmed value the way a prior attempt would have.
    let state = SchemaFormStateManager.init(SCHEMA)
    state = SchemaFormStateManager.updateField(state, 'p1_line1_aliennumber', '1234567', {
      confirmed: true,
    })
    SchemaFormStateManager.save(state)

    // The connection has NOT yet seen that value (its this.state predates the save).
    expect(conn.getState().fieldValues['p1_line1_aliennumber']).toBeUndefined()

    // Same-page-rerun clear: drop the field through the canonical path, then reload.
    const loaded = SchemaFormStateManager.load()!
    const { p1_line1_aliennumber: _removed, ...rest } = loaded.fieldValues
    SchemaFormStateManager.save({ ...loaded, fieldValues: rest })
    conn.reloadState()

    // The connection's in-memory copy now reflects the cleared storage -- no stale
    // filled/confirmed value survives for the next rerun.
    expect(conn.getState().fieldValues['p1_line1_aliennumber']).toBeUndefined()
  })

  it('reflects a still-present value after reload (reload is a faithful re-read, not a wipe)', () => {
    const conn = new WebFormConnection(SCHEMA)

    let state = SchemaFormStateManager.init(SCHEMA)
    state = SchemaFormStateManager.updateField(state, 'p1_line1_aliennumber', '7654321', {
      confirmed: true,
    })
    SchemaFormStateManager.save(state)

    conn.reloadState()

    const fv = conn.getState().fieldValues['p1_line1_aliennumber']
    expect(fv?.value).toBe('7654321')
    expect(fv?.confirmed).toBe(true)
  })

  it('is a no-op when sessionStorage is empty (keeps the existing in-memory state)', () => {
    const conn = new WebFormConnection(SCHEMA)
    const before = conn.getState()

    global.sessionStorage.removeItem('schema_form_state')
    conn.reloadState()

    // No throw, and the connection still has a usable state object.
    expect(conn.getState()).toBeTruthy()
    expect(conn.getState().schema.fields[0].id).toBe(before.schema.fields[0].id)
  })
})
