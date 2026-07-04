/**
 * Regression tests for canonicalizing voice checkbox-group values at the AI
 * ingress (bd polyglot-pdf-h76m.2).
 *
 * The backend prompt (config.py "Multiple checkboxes: comma-separated exact
 * values") makes Gemini deliver a checkbox-group selection as ONE comma-joined
 * string, but every downstream consumer expects string[]: the interactive
 * renderer stores arrays, and /api/fill-pdf fills a group only from a list (a
 * raw string is rejected as checkbox_unsupported_value and the group silently
 * stays empty on the printed PDF). applyAiValueWithValidation now splits the
 * comma string into string[] BEFORE validate/store, so state, callbacks,
 * conditionals, and fill all see the canonical array.
 *
 * No shipped kit sets group_kind (the older comma-split in shouldShowField is
 * gated on it and never fires), so the group detection here matches the
 * renderer's own rule: a checkbox field WITH options is a multi-select group.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { WebFormConnection, canonicalizeAiCheckboxGroupValue } from './webFormConnection'
import type { FormSchema, FormField } from './schema-forms/types/schema'

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

// One section, two fields, mirroring the shipped-kit reality (i-90 p3_race):
//  - a checkbox GROUP: type "checkbox" with an options array, NO group_kind
//  - a STANDALONE checkbox: type "checkbox" with no options (boolean value)
const SCHEMA: FormSchema = {
  source: 'web',
  fields: [
    {
      id: 'p3_race',
      name: 'Race (Select all applicable)',
      spoken_name: 'race',
      type: 'checkbox',
      options: [
        { value: 'P3_checkbox7_White[0]', label: 'White' },
        { value: 'P3_checkbox7_Black[0]', label: 'Black or African American' },
        { value: 'P3_checkbox7_Asian[0]', label: 'Asian' },
      ],
    },
    {
      id: 'p2_apt_checkbox',
      name: 'Apt',
      spoken_name: 'apartment',
      type: 'checkbox',
    },
  ],
  sections: [
    { id: 's1', label: 'S1', order: 1, fields: ['p3_race', 'p2_apt_checkbox'] },
  ],
} as unknown as FormSchema

function lastWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

function fireFieldUpdate(ws: MockWebSocket, updates: Record<string, any>): void {
  ws.onmessage?.({
    data: JSON.stringify({ type: 'field_update', updates }),
  })
}

describe('voice checkbox-group value canonicalization (bd polyglot-pdf-h76m.2)', () => {
  let onFieldUpdate: ReturnType<typeof vi.fn>
  let conn: WebFormConnection

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
    onFieldUpdate = vi.fn()
  })

  async function connect(): Promise<MockWebSocket> {
    conn = new WebFormConnection(SCHEMA, { onFieldUpdate })
    await conn.connect('wss://example/ws/fill')
    const ws = lastWs()
    ws.send.mockClear()
    onFieldUpdate.mockClear()
    return ws
  }

  function appliedValue(fieldId: string): any {
    const calls = onFieldUpdate.mock.calls.flatMap((c: any[]) => c[0])
    const entry = calls.find((u: any) => u.fieldId === fieldId)
    return entry?.value
  }

  it('splits a voice-shaped comma string into string[] before store + callback', async () => {
    const ws = await connect()
    fireFieldUpdate(ws, { p3_race: 'P3_checkbox7_White[0], P3_checkbox7_Black[0]' })

    const expected = ['P3_checkbox7_White[0]', 'P3_checkbox7_Black[0]']
    expect(appliedValue('p3_race')).toEqual(expected)
    expect(conn.getState().fieldValues['p3_race']?.value).toEqual(expected)
  })

  it('wraps a single no-comma selection into a one-element array', async () => {
    const ws = await connect()
    fireFieldUpdate(ws, { p3_race: 'P3_checkbox7_Asian[0]' })

    expect(appliedValue('p3_race')).toEqual(['P3_checkbox7_Asian[0]'])
    expect(conn.getState().fieldValues['p3_race']?.value).toEqual(['P3_checkbox7_Asian[0]'])
  })

  it('passes an already-array group value through unchanged', async () => {
    const ws = await connect()
    fireFieldUpdate(ws, { p3_race: ['P3_checkbox7_White[0]'] })

    expect(appliedValue('p3_race')).toEqual(['P3_checkbox7_White[0]'])
  })

  it('leaves a standalone boolean checkbox untouched', async () => {
    const ws = await connect()
    fireFieldUpdate(ws, { p2_apt_checkbox: true })

    expect(appliedValue('p2_apt_checkbox')).toBe(true)
    expect(conn.getState().fieldValues['p2_apt_checkbox']?.value).toBe(true)
  })

  it('splits a comma string arriving via the form_updated path too', async () => {
    // handleFormUpdated is a second, independently-reachable AI ingress (the
    // backend's form_updated message, callback_handler.py) with its own
    // canonicalization call sites -- cover it separately from field_update.
    const ws = await connect()
    ws.onmessage?.({
      data: JSON.stringify({
        type: 'form_updated',
        data: {
          form_state: { p3_race: 'P3_checkbox7_White[0], P3_checkbox7_Black[0]' },
          applied_fields: ['p3_race'],
        },
      }),
    })

    const expected = ['P3_checkbox7_White[0]', 'P3_checkbox7_Black[0]']
    expect(appliedValue('p3_race')).toEqual(expected)
    expect(conn.getState().fieldValues['p3_race']?.value).toEqual(expected)
  })
})

describe('canonicalizeAiCheckboxGroupValue unit behavior', () => {
  const groupField = SCHEMA.fields[0] as FormField
  const standaloneField = SCHEMA.fields[1] as FormField

  it('trims parts and drops empty segments', () => {
    expect(canonicalizeAiCheckboxGroupValue(groupField, ' a , , b ,')).toEqual(['a', 'b'])
  })

  it('canonicalizes an empty string to an empty array (no selection)', () => {
    expect(canonicalizeAiCheckboxGroupValue(groupField, '')).toEqual([])
  })

  it('does not touch non-string values on a group field', () => {
    expect(canonicalizeAiCheckboxGroupValue(groupField, ['x'])).toEqual(['x'])
    expect(canonicalizeAiCheckboxGroupValue(groupField, null)).toBeNull()
  })

  it('does not touch a standalone checkbox (no options) even for strings', () => {
    expect(canonicalizeAiCheckboxGroupValue(standaloneField, 'true')).toBe('true')
  })

  it('passes boolean-intent strings through untouched even on a group field', () => {
    // "true"/"false" are the literal boolean forms the backend tool contract
    // documents for a standalone checkbox -- never option selections. A
    // standalone checkbox carrying a single-widget options array must not have
    // its "true" wrapped into ["true"].
    expect(canonicalizeAiCheckboxGroupValue(groupField, 'true')).toBe('true')
    expect(canonicalizeAiCheckboxGroupValue(groupField, 'False')).toBe('False')
    expect(canonicalizeAiCheckboxGroupValue(groupField, ' TRUE ')).toBe(' TRUE ')
  })

  it('does not touch non-checkbox field types', () => {
    const textField = { id: 't', name: 'T', spoken_name: 'T', type: 'text' } as unknown as FormField
    expect(canonicalizeAiCheckboxGroupValue(textField, 'a, b')).toBe('a, b')
  })

  it('respects an explicit group_kind checkbox marker even without options', () => {
    const marked = {
      id: 'g', name: 'G', spoken_name: 'G', type: 'checkbox', group_kind: 'checkbox',
    } as unknown as FormField
    expect(canonicalizeAiCheckboxGroupValue(marked, 'a, b')).toEqual(['a', 'b'])
  })

  it('splits a wrapped FieldValue comma string into a plain array', () => {
    const wrapped = { value: 'a, b', confirmed: false }
    expect(canonicalizeAiCheckboxGroupValue(groupField, wrapped)).toEqual(['a', 'b'])
  })
})
