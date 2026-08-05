/**
 * Write-ownership between the React UI and WebFormConnection
 * (bd polyglot-pdf-uw3w / polyglot-pdf-3irc / polyglot-pdf-qim7).
 *
 * WebFormConnection holds `this.state` across turns while SchemaForm.tsx's
 * handleFieldChange / handleFieldSkip persist through SchemaFormStateManager
 * WITHOUT touching that object -- two independent writers of one fieldValues map.
 * Any handler ending in save(this.state) therefore persists its in-memory copy
 * over whatever the UI wrote since the last sync.
 *
 * These pin the reconcile that resolves it (reconcileFieldValues: per logical
 * field, last-writer-wins on lastModified, alias pairs collapsed to one entry):
 *   - uw3w: a value the user CLEARED on screen is not revived by a later
 *     confirm_field; a value the user TYPED is not blanked by a later skip_field.
 *   - 3irc: a confirm/skip cannot resurrect an []-alias key that updateField
 *     deleted on migration (the got6 one-entry invariant).
 *   - qim7: a field value written outside the connection survives session_ready.
 * Each is a REGRESSION direction, so each is mutation-verified.
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

// p1_a / p1_name are optional text fields (an optional field may legitimately
// confirm with ''), p1_grp is the checkbox group used for the []-alias case.
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    { id: 'p1_a', name: 'Field A', spoken_name: 'Field A', type: 'text', validation: { required: false } },
    { id: 'p1_name', name: 'Full Name', spoken_name: 'Full Name', type: 'text', validation: { required: false } },
    {
      id: 'p1_grp',
      name: 'Group',
      spoken_name: 'Group',
      type: 'checkbox_group',
      options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
      validation: { required: false },
    },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['p1_a', 'p1_name', 'p1_grp'] }],
} as unknown as FormSchema

function lastWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

/**
 * Drain the microtask queue. The message handlers are async and await several
 * times internally, so a fixed one-or-two `await Promise.resolve()` can let a
 * later step run BEFORE an earlier handler has finished -- which silently
 * inverts the ordering these tests depend on.
 */
async function flush(): Promise<void> {
  for (let i = 0; i < 20; i++) await Promise.resolve()
}

/**
 * A MONOTONIC Date.now() for these tests. lastModified is stamped with
 * Date.now(), whose millisecond resolution is coarser than the gap between an
 * AI write and the on-screen edit that follows it: on a fast machine both land
 * in the SAME millisecond, the stamps tie, and which side wins is decided by the
 * tie-break rather than by the ordering the test means to express. That made
 * this file pass or fail run-to-run with no code change. Advancing a counter on
 * every read gives each write a distinct, strictly increasing stamp, so these
 * tests exercise the reconcile RULE instead of racing the system clock.
 */
let fakeNow = 1_700_000_000_000
function installMonotonicClock(): void {
  fakeNow = 1_700_000_000_000
  vi.spyOn(Date, 'now').mockImplementation(() => ++fakeNow)
}

describe('fieldValues write-ownership (uw3w / 3irc / qim7)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    // A FRESH store per test. Stub it on BOTH `global` and `window`: under jsdom
    // those are distinct objects, and SchemaFormStateManager resolves the bare
    // `sessionStorage` binding while save() dispatches its change event on
    // `window`. Overriding only one leaves the other holding the PREVIOUS test's
    // state, which makes these tests pass alone and fail as a file.
    const store: Record<string, string> = {}
    const stub = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    } as unknown as Storage
    global.sessionStorage = stub
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, 'sessionStorage', {
        value: stub, writable: true, configurable: true,
      })
    }
    installMonotonicClock()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function connected(): Promise<{ conn: WebFormConnection; ws: MockWebSocket }> {
    const conn = new WebFormConnection(SCHEMA)
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    return { conn, ws }
  }

  /**
   * Simulate the on-screen editor: SchemaForm.tsx persists through
   * SchemaFormStateManager and never touches WebFormConnection.this.state.
   * updateField stamps lastModified, which is what makes the edit win.
   */
  function uiWrites(fieldId: string, value: unknown): void {
    const persisted = SchemaFormStateManager.load()
    SchemaFormStateManager.updateField(persisted as any, fieldId, value as any)
  }

  function persistedEntry(fieldId: string): any {
    return SchemaFormStateManager.load()?.fieldValues?.[fieldId]
  }

  // ---- bd polyglot-pdf-uw3w -------------------------------------------------

  it('confirm_field does NOT revive a value the user cleared on screen', async () => {
    const { conn, ws } = await connected()

    // AI fills the field (lands in BOTH memory and storage).
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { 'Field A': 'WRONG' } }) })
    await flush()
    expect((conn as any).state.fieldValues['p1_a'].value).toBe('WRONG')

    // The user clears it in the on-screen form. Storage now holds ''; the
    // connection's in-memory copy still holds 'WRONG'.
    uiWrites('p1_a', '')
    expect(persistedEntry('p1_a').value).toBe('')

    // The model then confirms the field.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'confirm_field', field_id: 'p1_a', confirmation_method: 'verbal' }),
    })
    await flush()

    // The cleared value must NOT come back -- and must not be marked confirmed
    // (a revived+confirmed value never re-prompts and prints on the PDF).
    expect(persistedEntry('p1_a').value).toBe('')
  })

  it('skip_field does NOT blank an answer the user just typed on screen', async () => {
    const { conn, ws } = await connected()

    // AI writes an empty value (memory + storage).
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { 'Full Name': '' } }) })
    await flush()

    // The user types a real answer on screen; storage holds it, memory does not.
    uiWrites('p1_name', 'Real Answer')
    expect(persistedEntry('p1_name').value).toBe('Real Answer')

    // A skip lands. The already-filled DATA-LOSS guard must SEE the typed answer
    // through the reconcile and refuse, rather than blanking it.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'skip_field', field_id: 'p1_name', request_id: 'req-1' }),
    })
    await flush()

    expect(persistedEntry('p1_name').value).toBe('Real Answer')
    expect(persistedEntry('p1_name').skipped).toBeFalsy()

    const acks = ws.send.mock.calls
      .map((c: any[]) => c[0])
      .filter((a: any) => typeof a === 'string')
      .map((s: string) => JSON.parse(s))
      .filter((m: any) => m.type === 'skip_field_response')
    expect(acks[0].recorded).toBe(false)
    expect(acks[0].reason).toBe('already_filled')
  })

  it('keeps an in-memory-only entry visible to the confirm gate (pjws direction holds)', async () => {
    const { conn, ws } = await connected()

    // An entry that exists ONLY in memory -- never persisted. The reconcile must
    // keep it, or the confirm would become a spurious 'no_value' refusal.
    ;(conn as any).state.fieldValues['p1_a'] = { value: 'in-memory-only' }

    ws.onmessage?.({
      data: JSON.stringify({ type: 'confirm_field', field_id: 'p1_a', confirmation_method: 'verbal' }),
    })
    await flush()

    expect((conn as any).state.fieldValues['p1_a'].value).toBe('in-memory-only')
    expect((conn as any).state.fieldValues['p1_a'].confirmed).toBe(true)
  })

  // ---- bd polyglot-pdf-3irc -------------------------------------------------

  it('confirm_field leaves exactly ONE entry when a group value migrated across the []-alias', async () => {
    const { conn, ws } = await connected()

    // AI writes the bracketed variant (memory + storage).
    ;(conn as any).state.fieldValues['p1_grp[]'] = { value: ['a'], lastModified: 1000 }
    const seeded = SchemaFormStateManager.load()
    SchemaFormStateManager.updateField(seeded as any, 'p1_grp[]', ['a'] as any)

    // A later writer MIGRATES it to the bare key; updateField deletes the stale
    // bracketed variant so exactly one entry represents the field (got6).
    uiWrites('p1_grp', ['b'])
    const afterMigration = Object.keys(SchemaFormStateManager.load()!.fieldValues)
      .filter(k => k.startsWith('p1_grp'))
    expect(afterMigration).toHaveLength(1)

    // The model confirms. The reconcile must not resurrect the deleted variant.
    ws.onmessage?.({
      data: JSON.stringify({ type: 'confirm_field', field_id: 'p1_grp', confirmation_method: 'verbal' }),
    })
    await flush()

    const keys = Object.keys(SchemaFormStateManager.load()!.fieldValues)
      .filter(k => k.startsWith('p1_grp'))
    expect(keys).toHaveLength(1)
    // and it is the MIGRATED value that survived, not the stale one.
    expect(SchemaFormStateManager.load()!.fieldValues[keys[0]].value).toEqual(['b'])
  })

  // ---- bd polyglot-pdf-qim7 -------------------------------------------------

  it('section_switched does not persist stale in-memory state over a concurrent UI write', async () => {
    // A section switch is a ROUND-TRIP (prepare_section_switch out,
    // section_switched back) and the handler ends in a bare save(this.state),
    // so an on-screen edit landing inside that window would be reverted.
    const { conn, ws } = await connected()

    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { 'Field A': 'old' } }) })
    await flush()

    uiWrites('p1_a', 'typed during switch')
    expect(persistedEntry('p1_a').value).toBe('typed during switch')

    ws.onmessage?.({
      data: JSON.stringify({ type: 'section_switched', section_number: 1 }),
    })
    await flush()

    expect(persistedEntry('p1_a').value).toBe('typed during switch')
  })

  it('drain_findings_result does not DROP a field written on screen mid-drain', async () => {
    // The validator drain is a round-trip (validation_result -> drain_findings ->
    // drain_findings_result) and markFieldsSteered rebuilds the whole fieldValues
    // map from this.state, so a field this object has never seen is dropped
    // OUTRIGHT here, not merely staled -- the worst version of the two-writer bug.
    const { conn, ws } = await connected()

    // The AI fills p1_a, so a finding has something to steer about.
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { 'Field A': 'a value' } }) })
    await flush()

    // The user types into a DIFFERENT field on screen, mid-drain. The connection
    // object has never seen p1_name at all.
    uiWrites('p1_name', 'typed mid-drain')
    expect(persistedEntry('p1_name').value).toBe('typed mid-drain')

    ws.onmessage?.({
      data: JSON.stringify({
        type: 'drain_findings_result',
        conflicts: [{ field_ids: ['p1_a'], reason: 'mismatch', field_names: { p1_a: 'Field A' } }],
      }),
    })
    await flush()

    // The on-screen field must still exist -- this asserts presence, not just value.
    expect(persistedEntry('p1_name')).toBeDefined()
    expect(persistedEntry('p1_name').value).toBe('typed mid-drain')
  })

  it('session_ready does not persist stale in-memory state over a concurrent UI write', async () => {
    const { conn, ws } = await connected()

    // AI fills the field (memory + storage).
    ws.onmessage?.({ data: JSON.stringify({ type: 'field_update', updates: { 'Field A': 'old' } }) })
    await flush()

    // The user edits it on screen -- storage only; this.state still holds 'old'.
    uiWrites('p1_a', 'typed by user')
    expect(persistedEntry('p1_a').value).toBe('typed by user')

    // A routine session_ready lands (idle-timeout reconnect / network drop).
    // Its setSessionId/setJitMode/setContinuousSession mutators each save().
    ws.onmessage?.({
      data: JSON.stringify({
        type: 'session_ready',
        session_id: 'sess-2',
        jit_mode_enabled: true,
        continuous_session_enabled: true,
      }),
    })
    await flush()

    // The on-screen edit must SURVIVE the reconnect.
    expect(persistedEntry('p1_a').value).toBe('typed by user')
  })
})
