/**
 * Field-level navigation pin tests (bd polyglot-pdf-jnjj.36).
 *
 * The AI's switch_to_field tool pins a target field in client state; while the
 * pin is live (field visible + unconfirmed), computeNextField returns it FIRST,
 * so every "what's next" consumer -- the hint, the DTI schema drip, UI focus --
 * follows the jump. Confirm/skip release the pin; a section switch abandons it.
 * The resolver searches the WHOLE schema deliberately (NOT the section-scoped
 * getFieldBySpokenName -- bd polyglot-pdf-lt9z).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { SchemaFormState } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
import { computeNextField } from '../navigation'

describe('switch_to_field pin (bd jnjj.36)', () => {
  let sessionStorageMock: { [key: string]: string }

  beforeEach(() => {
    sessionStorageMock = {}
    global.sessionStorage = {
      getItem: vi.fn((key: string) => sessionStorageMock[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStorageMock[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete sessionStorageMock[key]
      }),
      clear: vi.fn(() => {
        sessionStorageMock = {}
      }),
      length: 0,
      key: vi.fn(() => null)
    } as any
  })

  const schema: FormSchema = {
    source: 'pdf',
    form_metadata: {
      title: 'Test Form', version: '1', language: 'en',
      form_number: 'T-1', edition_date: '01/01/25', page_count: 1,
    },
    sections: [
      { id: 'sec1', label: 'One', order: 1, fields: ['a', 'b'] },
      { id: 'sec2', label: 'Two', order: 2, fields: ['c', 'd'] },
    ],
    fields: [
      { id: 'a', name: 'Field A', spoken_name: 'field alpha', type: 'text', section_id: 'sec1' },
      { id: 'b', name: 'Field B', spoken_name: 'field beta', type: 'text', section_id: 'sec1' },
      { id: 'c', name: 'Field C', spoken_name: 'field gamma', type: 'text', section_id: 'sec2', spoken_aliases: ['the third one'] },
      {
        id: 'd', name: 'Field D', spoken_name: 'field delta', type: 'text', section_id: 'sec2',
        show_if: { field: 'c', operator: 'equals', value: 'open sesame' },
      },
    ],
  } as unknown as FormSchema

  const baseState = (over: Partial<SchemaFormState> = {}): SchemaFormState => ({
    schema,
    fieldValues: {},
    currentSectionId: 'sec1',
    completedSections: new Set<string>(),
    validationErrors: {},
    lastUpdated: Date.now(),
    formSessionId: 'fss_test',
    loadedFieldIds: new Set<string>(),
    jitModeEnabled: false,
    continuousSessionEnabled: true,
    disclaimerAccepted: true,
    pinnedFieldId: null,
    ...over,
  }) as SchemaFormState

  // ---- resolveFieldForNavigation (whole-schema, bd lt9z-aware) -------------

  it('resolves by exact field_id first', () => {
    expect(SchemaFormStateManager.resolveFieldForNavigation(baseState(), 'c')).toBe('c')
  })

  it('resolves by spoken name, display name, and alias, case-insensitively', () => {
    const s = baseState()
    expect(SchemaFormStateManager.resolveFieldForNavigation(s, 'Field Gamma')).toBe('c')
    expect(SchemaFormStateManager.resolveFieldForNavigation(s, 'field c')).toBe('c')
    expect(SchemaFormStateManager.resolveFieldForNavigation(s, 'THE THIRD ONE')).toBe('c')
  })

  it('resolves fields OUTSIDE the current section (whole schema, not the lt9z scope)', () => {
    // currentSectionId is sec1 and completedSections is empty -- the
    // section-scoped getFieldBySpokenName would go blind here.
    const s = baseState({ currentSectionId: 'sec1' })
    expect(SchemaFormStateManager.resolveFieldForNavigation(s, 'field gamma')).toBe('c')
  })

  it('returns null for an unknown identifier or empty input', () => {
    expect(SchemaFormStateManager.resolveFieldForNavigation(baseState(), 'nope')).toBeNull()
    expect(SchemaFormStateManager.resolveFieldForNavigation(baseState(), '')).toBeNull()
  })

  // ---- computeNextField pin priority ---------------------------------------

  it('returns the pinned field first even when earlier fields are unfilled', () => {
    const s = baseState({ pinnedFieldId: 'c' })
    expect(computeNextField(s, { skipConfirmed: true })?.id).toBe('c')
  })

  it('ignores a pin on a confirmed field (dormant until the value changes)', () => {
    const s = baseState({
      pinnedFieldId: 'c',
      fieldValues: { c: { value: 'x', confirmed: true } as any },
    })
    expect(computeNextField(s, { skipConfirmed: true })?.id).toBe('a')
  })

  it('ignores a pin on a conditionally hidden field', () => {
    // d is show_if c == 'open sesame'; c is empty, so d is hidden.
    const s = baseState({ pinnedFieldId: 'd' })
    expect(computeNextField(s, { skipConfirmed: true })?.id).toBe('a')
  })

  it('ignores a pin that resolves to no field', () => {
    const s = baseState({ pinnedFieldId: 'ghost' })
    expect(computeNextField(s, { skipConfirmed: true })?.id).toBe('a')
  })

  // ---- pin lifecycle --------------------------------------------------------

  it('pinField sets and persists the pin', () => {
    const s = SchemaFormStateManager.pinField(baseState(), 'c')
    expect(s.pinnedFieldId).toBe('c')
    expect(computeNextField(s)?.id).toBe('c')
  })

  it('confirmField releases the pin for the confirmed field only', () => {
    let s = baseState({
      pinnedFieldId: 'c',
      fieldValues: { c: { value: 'x', confirmed: false } as any },
    })
    s = SchemaFormStateManager.confirmField(s, 'c', 'ai_voice')
    expect(s.pinnedFieldId).toBeNull()

    let other = baseState({
      pinnedFieldId: 'c',
      fieldValues: { a: { value: 'y', confirmed: false } as any },
    })
    other = SchemaFormStateManager.confirmField(other, 'a', 'ai_voice')
    expect(other.pinnedFieldId).toBe('c') // an unrelated confirm keeps the pin
  })

  it('markFieldSkipped releases the pin', () => {
    let s = baseState({ pinnedFieldId: 'b' })
    s = SchemaFormStateManager.markFieldSkipped(s, 'b', 'ai_voice')
    expect(s.pinnedFieldId).toBeNull()
  })

  it('switchToSection abandons any pin', () => {
    let s = baseState({ pinnedFieldId: 'c' })
    s = SchemaFormStateManager.switchToSection(s, 'sec2')
    expect(s.pinnedFieldId).toBeNull()
  })

  it('navigateToSection (the manual section jump) also abandons any pin', () => {
    let s = baseState({ pinnedFieldId: 'c' })
    s = SchemaFormStateManager.navigateToSection(s, 'sec2')
    expect(s.pinnedFieldId).toBeNull()
  })

  it('load() migrates old persisted state without a pin field', () => {
    const legacy: any = { ...baseState() }
    delete legacy.pinnedFieldId
    legacy.completedSections = []
    legacy.loadedFieldIds = []
    sessionStorageMock['schema_form_state'] = JSON.stringify(legacy)
    const loaded = SchemaFormStateManager.load()
    expect(loaded?.pinnedFieldId).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// End-to-end probe (exit criterion 2, bd jnjj.36): drive the REAL
// WebFormConnection message dispatch with a switch_field request and assert
// the full observable contract -- the identifier resolves to the right field,
// the pin persists, UI focus follows (onNextField), and the ack carries the
// hint + (DTI) schema the backend renders guidance from. Together with the
// backend's real-coordinator round-trip test
// (backend/tests/unit/test_switch_to_field_tool.py) this pins both ends of
// the wire contract.
// ---------------------------------------------------------------------------

import { WebFormConnection } from '../webFormConnection'

describe('switch_field end-to-end probe (WebFormConnection)', () => {
  let sessionStorageMock: { [key: string]: string }

  beforeEach(() => {
    sessionStorageMock = {}
    global.sessionStorage = {
      getItem: vi.fn((key: string) => sessionStorageMock[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStorageMock[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete sessionStorageMock[key]
      }),
      clear: vi.fn(() => {
        sessionStorageMock = {}
      }),
      length: 0,
      key: vi.fn(() => null)
    } as any
  })

  const probeSchema: any = {
    source: 'pdf',
    form_metadata: {
      title: 'Probe Form', version: '1', language: 'en',
      form_number: 'P-1', edition_date: '01/01/25', page_count: 1,
    },
    sections: [
      { id: 'sec1', label: 'One', order: 1, fields: ['a'] },
      { id: 'sec2', label: 'Two', order: 2, fields: ['c'] },
    ],
    fields: [
      { id: 'a', name: 'Field A', spoken_name: 'field alpha', type: 'text', section_id: 'sec1' },
      { id: 'c', name: 'Field C', spoken_name: 'field gamma', type: 'text', section_id: 'sec2' },
    ],
  }

  function makeConn(opts: { continuous?: boolean; dti?: boolean } = {}) {
    const onNextField = vi.fn()
    const conn = new WebFormConnection(probeSchema, { onNextField })
    const anyConn = conn as any
    // Both flags normally arrive on the session_ready handshake: the class
    // field is what the handlers read (same convention as the skip path);
    // the state flag drives computeNextField.
    anyConn.continuousSessionEnabled = opts.continuous ?? true
    anyConn.state.continuousSessionEnabled = opts.continuous ?? true
    anyConn.dtiModeEnabled = opts.dti ?? true
    SchemaFormStateManager.save(anyConn.state)
    const sent: any[] = []
    anyConn.send = vi.fn((m: any) => sent.push(m))
    return { conn: anyConn, sent, onNextField }
  }

  async function dispatch(conn: any, message: any) {
    await conn.handleMessage({ data: JSON.stringify(message) } as MessageEvent)
  }

  it('resolves a spoken name to the right field, pins it, moves UI focus, and acks with hint + schema', async () => {
    const { conn, sent, onNextField } = makeConn({ continuous: true, dti: true })
    await dispatch(conn, { type: 'switch_field', request_id: 'r1', field: 'field gamma' })

    const ack = sent.find(m => m.type === 'switch_field_response')
    expect(ack).toBeTruthy()
    expect(ack.request_id).toBe('r1')
    expect(ack.found).toBe(true)
    expect(ack.field_id).toBe('c')                       // the RIGHT field
    expect(ack.spoken_name).toBe('field gamma')
    // The hint uses the frontend's standard format (display name + field_id)
    // -- same producer as every other next-field hint.
    expect(ack.next_field_hint).toContain("field_id: 'c'")
    expect(ack.next_field_schema?.id).toBe('c')          // DTI guidance source
    expect(onNextField).toHaveBeenCalledWith('c')        // UI focus followed
    const persisted = SchemaFormStateManager.load()
    expect(persisted?.pinnedFieldId).toBe('c')           // pin persisted
    // And the pin drives the next-field computation end-to-end.
    expect(computeNextField(persisted!)?.id).toBe('c')
  })

  it('acks unknown_field for an unresolvable identifier and does not pin', async () => {
    const { conn, sent, onNextField } = makeConn()
    await dispatch(conn, { type: 'switch_field', request_id: 'r2', field: 'nope' })
    const ack = sent.find(m => m.type === 'switch_field_response')
    expect(ack.found).toBe(false)
    expect(ack.reason).toBe('unknown_field')
    expect(onNextField).not.toHaveBeenCalled()
    expect(SchemaFormStateManager.load()?.pinnedFieldId ?? null).toBeNull()
  })

  it('acks other_section (with the section label) in section-scoped mode', async () => {
    const { conn, sent } = makeConn({ continuous: false })
    await dispatch(conn, { type: 'switch_field', request_id: 'r3', field: 'field gamma' })
    const ack = sent.find(m => m.type === 'switch_field_response')
    expect(ack.found).toBe(false)
    expect(ack.reason).toBe('other_section')
    expect(ack.section_label).toBe('Two')
    expect(ack.section_order).toBe(2)
  })

  it('ignores a malformed request with no request_id (nothing to ack)', async () => {
    const { conn, sent } = makeConn()
    await dispatch(conn, { type: 'switch_field', field: 'field gamma' })
    expect(sent.find(m => m.type === 'switch_field_response')).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// isFormComplete pin integration (fresh-eyes gap, bd jnjj.36): with every
// REQUIRED field confirmed, a live pin on an unconfirmed OPTIONAL field must
// keep the form incomplete -- otherwise the completion-gated consumers (the
// post-confirm hint round-trip, reconnect hints, manual-edit hints, the
// form-complete event) report "complete" and silently abandon the jump.
// ---------------------------------------------------------------------------

import { isFormComplete } from '../navigation'

describe('isFormComplete honors a live pin (bd jnjj.36)', () => {
  const pinSchema: any = {
    source: 'pdf',
    form_metadata: {
      title: 'Pin Form', version: '1', language: 'en',
      form_number: 'PN-1', edition_date: '01/01/25', page_count: 1,
    },
    sections: [{ id: 's1', label: 'S1', order: 1, fields: ['req', 'opt'] }],
    fields: [
      { id: 'req', name: 'Required', spoken_name: 'required', type: 'text', section_id: 's1', validation: { required: true } },
      { id: 'opt', name: 'Optional', spoken_name: 'optional', type: 'text', section_id: 's1' },
    ],
  }

  const pinState = (pin: string | null): any => ({
    schema: pinSchema,
    fieldValues: { req: { value: 'x', confirmed: true } },
    currentSectionId: 's1',
    completedSections: new Set<string>(),
    validationErrors: {},
    lastUpdated: Date.now(),
    formSessionId: 'fss_pin',
    loadedFieldIds: new Set<string>(),
    jitModeEnabled: false,
    continuousSessionEnabled: true,
    disclaimerAccepted: true,
    pinnedFieldId: pin,
  })

  it('all required confirmed + NO pin -> complete (baseline behavior unchanged)', () => {
    expect(isFormComplete(pinState(null))).toBe(true)
  })

  it('all required confirmed + live pin on an unconfirmed optional field -> NOT complete', () => {
    const s = pinState('opt')
    expect(isFormComplete(s)).toBe(false)
    // ...and the pin IS what the next-field consumers get.
    expect(computeNextField(s, { skipConfirmed: true })?.id).toBe('opt')
  })

  it('a stale pin (confirmed target) does not hold the form open', () => {
    const s = pinState('opt')
    s.fieldValues.opt = { value: 'y', confirmed: true }
    expect(isFormComplete(s)).toBe(true)
  })

  it('a stale pin (unknown field) does not hold the form open', () => {
    expect(isFormComplete(pinState('ghost'))).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Checkbox-group []-alias reads (outer review, bd jnjj.36 / bd 5k52 class):
// a group's fieldValues entry may sit under the bracket key variant. The
// switch ack and the pin's confirmed-check must both read via the alias
// fallback, or a filled+confirmed group is misreported as unanswered (the
// correction flow degrades to a fresh fill) / a confirmed pin holds the form
// open.
// ---------------------------------------------------------------------------

describe('switch_to_field []-alias reads (bd jnjj.36)', () => {
  let storageMock: { [key: string]: string }

  beforeEach(() => {
    storageMock = {}
    global.sessionStorage = {
      getItem: vi.fn((k: string) => storageMock[k] || null),
      setItem: vi.fn((k: string, v: string) => { storageMock[k] = v }),
      removeItem: vi.fn((k: string) => { delete storageMock[k] }),
      clear: vi.fn(() => { storageMock = {} }),
      length: 0,
      key: vi.fn(() => null)
    } as any
  })

  const groupSchema: any = {
    source: 'pdf',
    form_metadata: {
      title: 'Alias Form', version: '1', language: 'en',
      form_number: 'AL-1', edition_date: '01/01/25', page_count: 1,
    },
    sections: [{ id: 's1', label: 'S1', order: 1, fields: ['race[]', 'req'] }],
    fields: [
      {
        id: 'race[]', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
        section_id: 's1',
        options: [{ value: 'x', label: 'X' }, { value: 'y', label: 'Y' }],
      },
      { id: 'req', name: 'Required', spoken_name: 'required', type: 'text', section_id: 's1', validation: { required: true } },
    ],
  }

  it('the switch ack reports value/confirmed for a group stored under the alias key', async () => {
    const conn: any = new WebFormConnection(groupSchema, {})
    conn.continuousSessionEnabled = true
    conn.state.continuousSessionEnabled = true
    conn.dtiModeEnabled = false
    // The value landed under the UNbracketed alias (Gemini dropped the bracket).
    conn.state.fieldValues['race'] = { value: ['x'], confirmed: true }
    SchemaFormStateManager.save(conn.state)
    const sent: any[] = []
    conn.send = vi.fn((m: any) => sent.push(m))
    await conn.handleMessage({ data: JSON.stringify({ type: 'switch_field', request_id: 'ra', field: 'race' }) } as MessageEvent)
    const ack = sent.find(m => m.type === 'switch_field_response')
    expect(ack.found).toBe(true)
    expect(ack.field_id).toBe('race[]')
    expect(ack.already_confirmed).toBe(true)   // alias-aware read
    expect(ack.has_value).toBe(true)
    expect(ack.value).toEqual(['x'])
  })

  it('a pin on a group confirmed under the alias key is stale (does not hold the form open)', () => {
    const state: any = {
      schema: groupSchema,
      fieldValues: {
        req: { value: 'v', confirmed: true },
        race: { value: ['x'], confirmed: true },  // alias key
      },
      currentSectionId: 's1',
      completedSections: new Set<string>(),
      validationErrors: {},
      lastUpdated: Date.now(),
      formSessionId: 'fss_alias',
      loadedFieldIds: new Set<string>(),
      jitModeEnabled: false,
      continuousSessionEnabled: true,
      disclaimerAccepted: true,
      pinnedFieldId: 'race[]',
    }
    expect(isFormComplete(state)).toBe(true)
    // NOTE deliberately NOT asserting computeNextField here: its MAIN loop's
    // bare fieldValues reads have a PRE-EXISTING alias blindness (it offers an
    // alias-keyed group as unconfirmed with or without a pin) -- out of this
    // bead's scope. This test pins only that the PIN path (resolveLivePin)
    // reads alias-aware, so a confirmed-under-alias pin cannot hold
    // isFormComplete open.
  })
})
