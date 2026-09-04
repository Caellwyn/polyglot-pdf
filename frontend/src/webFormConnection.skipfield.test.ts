/**
 * Tests for the voice skip_field handler (bd polyglot-pdf-7yra).
 *
 * skip_field lets the assistant force-skip a REQUIRED field the user cannot
 * answer. Unlike confirm_field there is NO usable-value gate: an empty REQUIRED
 * field -- which confirm_field REFUSES (the 0y7 loop-breaker) -- is recorded as
 * intentionally skipped (markFieldSkipped: empty value + skipped flag) and the
 * frontend acks recorded:true so the backend advances.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import type { FormSchema } from './schema-forms/types/schema'
import { readFieldEntryWithAlias } from './schema-forms/utils/fieldValue'
import { SchemaFormStateManager } from './schema-forms/state/schemaFormState'

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

// One REQUIRED field in one section -- the case confirm_field cannot skip.
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    {
      id: 'p1_uscis_number',
      name: 'USCIS Number',
      spoken_name: 'USCIS Number',
      type: 'text',
      validation: { required: true },
    },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['p1_uscis_number'] }],
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

function fireSkip(ws: MockWebSocket, fieldId: string, requestId = 'req-1'): void {
  ws.onmessage?.({
    data: JSON.stringify({ type: 'skip_field', field_id: fieldId, request_id: requestId }),
  })
}

function skipAcks(ws: MockWebSocket): any[] {
  return sentMessages(ws).filter(m => m.type === 'skip_field_response')
}

describe('WebFormConnection skip_field handler (bd polyglot-pdf-7yra)', () => {
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

  async function connected(): Promise<{ conn: WebFormConnection; ws: MockWebSocket }> {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear() // drop the handshake send
    return { conn, ws }
  }

  it('records a skip on an empty REQUIRED field and acks recorded:true', async () => {
    const { conn, ws } = await connected()

    fireSkip(ws, 'p1_uscis_number')
    await Promise.resolve() // let the async handler run

    const acks = skipAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(true)
    expect(acks[0].request_id).toBe('req-1')

    // The field is marked skipped in state (empty value + skipped flag).
    const fv = (conn as any).state.fieldValues['p1_uscis_number']
    expect(fv?.skipped).toBe(true)
    expect(fv?.value ?? null).toBeNull()
  })

  it('REFUSES to skip an already-filled field (no data loss) and acks already_filled', async () => {
    const { conn, ws } = await connected()

    // Fill the field first (production field_update path keyed by name).
    ws.onmessage?.({
      data: JSON.stringify({ type: 'field_update', updates: { 'USCIS Number': 'A123456789' } }),
    })
    await Promise.resolve()
    ws.send.mockClear()

    fireSkip(ws, 'p1_uscis_number')
    await Promise.resolve()

    const acks = skipAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(false)
    expect(acks[0].reason).toBe('already_filled')

    // The real value is INTACT -- not blanked, not marked skipped.
    const fv = (conn as any).state.fieldValues['p1_uscis_number']
    expect(fv?.value).toBe('A123456789')
    expect(fv?.skipped).toBeFalsy()
  })

  it('REFUSES a skip when the value is stored under the []-alias key (no shadow data loss)', async () => {
    // A checkbox-group value can be stored under the bracketed variant while the
    // model sends the bare id (Gemini drops/adds the bracket). The guard must read
    // via the []-alias fallback, or it would see undefined, pass, and let
    // markFieldSkipped SHADOW the real aliased answer (fresh-eyes review round 2).
    const { conn, ws } = await connected()

    // Seed a filled value under the bracketed alias directly (mirrors how an
    // aliased group value lands in state).
    ;(conn as any).state.fieldValues['p1_uscis_number[]'] = { value: ['x'], confirmed: true }

    fireSkip(ws, 'p1_uscis_number') // bare id
    await Promise.resolve()

    const acks = skipAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(false)
    expect(acks[0].reason).toBe('already_filled')
    // The real value is INTACT and was NOT skip-shadowed. Read through the
    // alias fallback rather than a hardcoded key: the reconcile normalizes an
    // alias pair onto the key the SCHEMA declares (here the bare
    // `p1_uscis_number`), so asserting the bracketed key would pin a key
    // placement the reconcile deliberately changed -- the VALUE surviving
    // un-shadowed is what this test guards (bd polyglot-pdf-5k52).
    const entry = readFieldEntryWithAlias(
      (conn as any).state.fieldValues,
      'p1_uscis_number'
    )
    expect(entry?.value).toEqual(['x'])
    // Assert the SHADOW separately, across BOTH variants. Checking `skipped` on
    // the alias-read alone is not enough: that read is meaningful-wins, so it
    // would return the real ['x'] entry (skipped undefined) even if a hollow
    // skipped entry HAD been written beside it -- passing while the exact data
    // loss this test is named for occurred.
    const fv = (conn as any).state.fieldValues
    for (const k of ['p1_uscis_number', 'p1_uscis_number[]']) {
      expect(fv[k]?.skipped, `${k} must not be skip-shadowed`).toBeFalsy()
    }
  })

  it('acks recorded:false for an unknown field id', async () => {
    const { ws } = await connected()

    fireSkip(ws, 'no_such_field')
    await Promise.resolve()

    const acks = skipAcks(ws)
    expect(acks).toHaveLength(1)
    expect(acks[0].recorded).toBe(false)
    expect(acks[0].reason).toBe('unknown_field')
  })

  it('does not ack OR mutate state when request_id is missing', async () => {
    const { conn, ws } = await connected()

    // No request_id -> the handler cannot ack the synchronous round-trip, so it
    // must NOT record the skip or advance (that would silently diverge from what
    // the backend believes). The real backend always sends request_id.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'skip_field', field_id: 'p1_uscis_number' }),
    })
    await Promise.resolve()

    expect(skipAcks(ws)).toHaveLength(0)
    // State untouched: the field is not marked skipped.
    const fv = (conn as any).state.fieldValues['p1_uscis_number']
    expect(fv?.skipped).toBeFalsy()
  })
})

// ---------------------------------------------------------------------------
// Whitespace must not block a skip (bd polyglot-pdf-5ovod).
//
// The `alreadyFilled` guard exists to stop a skip ERASING a real answer. It was
// untrimmed, and once 5ovod tightened the other exits that became a DEADLOCK for
// a required field holding only spaces:
//   - confirm_field refuses  (hasUsableValue rejects whitespace)
//   - skip_field refused     (this guard: "already_filled")
//   - update_form_fields ''  is rejected by the required check
// ...while the backend marks the skip refusal NON-RETRYABLE ("Do NOT retry
// skip_field", callback_handler.py) and computeNextField keeps re-offering the
// field. The model would be handed a field it could not answer, skip or clear,
// and told not to try again.
//
// Found by the cross-surface review, which traced this diff's contracts OUT into
// the untouched handler. 5ovod's own escapability test called markFieldSkipped
// DIRECTLY, so it structurally could not see this -- these drive the real
// skip_field message instead.
// ---------------------------------------------------------------------------
describe('skip_field is not blocked by whitespace (bd polyglot-pdf-5ovod)', () => {
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

  async function connectedWith(value: any): Promise<MockWebSocket> {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    ;(conn as any).state.fieldValues['p1_uscis_number'] = { value }
    const ws = lastWs()
    ws.send.mockClear()
    return ws
  }

  it('a whitespace-only field CAN be skipped -- the voice path has an exit', async () => {
    const ws = await connectedWith('   ')

    fireSkip(ws, 'p1_uscis_number')

    const ack = skipAcks(ws)[0]
    expect(ack?.recorded, 'skip must be recorded, not refused as already_filled').toBe(true)
  })

  it('a REAL answer still blocks the skip -- the guard keeps its job', async () => {
    // The guard exists so a skip cannot erase an answer. That must survive.
    const ws = await connectedWith('A123456789')

    fireSkip(ws, 'p1_uscis_number')

    const ack = skipAcks(ws)[0]
    expect(ack?.recorded).toBe(false)
    expect(ack?.reason).toBe('already_filled')
  })
})

// ---------------------------------------------------------------------------
// switch_field must not claim a whitespace field "already holds a value".
//
// Sibling of the skip guard above (bd polyglot-pdf-5ovod). The ack's has_value
// drives the backend's guidance to the model: on true it says "it already holds
// an unconfirmed value -- read it back and verify it" (callback_handler.py). For
// a field containing only spaces there is nothing to read back, and confirm_field
// now refuses that very field -- so a true here steers the model at a closed
// exit. Found by the cross-surface review, which noticed the two predicates had
// drifted while a comment still claimed they matched.
// ---------------------------------------------------------------------------
describe('switch_field has_value ignores whitespace (bd polyglot-pdf-5ovod)', () => {
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

  async function switchAckFor(value: any): Promise<any> {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    // The handler RELOADS from the persisted snapshot before reading the value
    // (the staleness rule it shares with sendManualFieldUpdate), so seeding the
    // in-memory state alone is discarded -- persist it the way the app does.
    ;(conn as any).state.fieldValues['p1_uscis_number'] = { value }
    SchemaFormStateManager.save((conn as any).state)
    const ws = lastWs()
    ws.send.mockClear()
    // NOTE the key is `field`, not `field_id` -- switch_field takes a free-text
    // identifier the handler resolves (resolveFieldForNavigation).
    ws.onmessage?.({
      data: JSON.stringify({
        type: 'switch_field',
        field: 'p1_uscis_number',
        request_id: 'req-sf',
      }),
    })
    return sentMessages(ws).find(m => m.type === 'switch_field_response')
  }

  it('a whitespace field is reported as having NO value', async () => {
    const ack = await switchAckFor('   ')
    expect(ack?.has_value, 'whitespace must not read as an existing answer').toBe(false)
  })

  it('a real value is still reported as having one', async () => {
    const ack = await switchAckFor('A123456789')
    expect(ack?.has_value).toBe(true)
  })
})
