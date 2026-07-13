/**
 * W4 (bd polyglot-pdf-ny4s): re-arm the `steered` marker on a VALUE change.
 *
 * The updateField write path used to carry `steered` forward unconditionally, so a
 * CORRECTION to an adjudicated field was never re-validated. W4 clears the marker
 * when the field's normalized value actually changes, and keeps it when the value is
 * unchanged (the no-nagging guarantee: a "both are intentional" confirm changes no
 * value). Covers the value-equality edge cases (empty, arrays/checkbox groups) the
 * re-arm decision keys on.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { FormSchema, FieldValue } from '../types/schema'

function schema(): FormSchema {
  return {
    source: 'web',
    form_metadata: { title: 'T', version: '1.0.0', language: 'en', form_number: 'W4', edition_date: '01/01/25', page_count: 1 },
    fields: [
      { id: 'text1', name: 'text1', spoken_name: 'Text 1', type: 'text', section_id: 'sec' },
      { id: 'box', name: 'box', spoken_name: 'Box', type: 'checkbox_group', section_id: 'sec',
        options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }, { value: 'c', label: 'C' }] },
    ],
    sections: [{ id: 'sec', label: 'Sec', order: 1, fields: ['text1', 'box'] }],
  } as unknown as FormSchema
}

function steer(state: any, id: string) {
  return SchemaFormStateManager.markFieldsSteered(state, [id])
}

describe('W4 re-arm steered on value change (bd polyglot-pdf-ny4s)', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null, length: 0,
    } as unknown as Storage
  })

  it('a value change clears steered; an unchanged write keeps it', () => {
    let s = SchemaFormStateManager.init(schema())
    s = SchemaFormStateManager.updateField(s, 'text1', 'hello')
    s = steer(s, 'text1')
    // unchanged
    s = SchemaFormStateManager.updateField(s, 'text1', 'hello')
    expect((s.fieldValues['text1'] as FieldValue).steered).toBe(true)
    // changed
    s = SchemaFormStateManager.updateField(s, 'text1', 'world')
    expect((s.fieldValues['text1'] as FieldValue).steered).toBeFalsy()
  })

  it('clearing a steered field to blank re-arms (non-empty -> empty is a change)', () => {
    let s = SchemaFormStateManager.init(schema())
    s = SchemaFormStateManager.updateField(s, 'text1', 'hello')
    s = steer(s, 'text1')
    s = SchemaFormStateManager.updateField(s, 'text1', '')
    expect((s.fieldValues['text1'] as FieldValue).steered).toBeFalsy()
  })

  it('a checkbox_group: changing the selected set re-arms; the same set (same order) keeps it', () => {
    let s = SchemaFormStateManager.init(schema())
    s = SchemaFormStateManager.updateField(s, 'box', ['a', 'b'])
    s = steer(s, 'box')
    // same set -> keep
    s = SchemaFormStateManager.updateField(s, 'box', ['a', 'b'])
    expect((s.fieldValues['box'] as FieldValue).steered).toBe(true)
    // different set -> re-arm
    s = SchemaFormStateManager.updateField(s, 'box', ['a', 'c'])
    expect((s.fieldValues['box'] as FieldValue).steered).toBeFalsy()
  })

  it('re-marking a re-armed field steers it again (the correction re-enters the net)', () => {
    let s = SchemaFormStateManager.init(schema())
    s = SchemaFormStateManager.updateField(s, 'text1', 'hello')
    s = steer(s, 'text1')
    s = SchemaFormStateManager.updateField(s, 'text1', 'world') // re-arm
    expect((s.fieldValues['text1'] as FieldValue).steered).toBeFalsy()
    // A new validation_result on the corrected value can steer it again.
    s = steer(s, 'text1')
    expect((s.fieldValues['text1'] as FieldValue).steered).toBe(true)
  })

  it('a never-steered field stays unsteered on edit (no spurious marker)', () => {
    let s = SchemaFormStateManager.init(schema())
    s = SchemaFormStateManager.updateField(s, 'text1', 'a')
    s = SchemaFormStateManager.updateField(s, 'text1', 'b')
    expect((s.fieldValues['text1'] as FieldValue).steered).toBeFalsy()
  })
})

// --------------------------------------------------------------------------- //
// The pure value-equality helper the re-arm decision keys on.
// --------------------------------------------------------------------------- //
describe('W4 _sameFieldValue (bd polyglot-pdf-ny4s)', () => {
  // Access the private static via a cast (it is implementation-critical enough to
  // pin directly, and the integration tests above exercise it end to end).
  const same = (a: any, b: any) => (SchemaFormStateManager as any)._sameFieldValue(a, b)

  it('treats all empty-ish values as equal', () => {
    for (const e of [undefined, null, '', [], ['', '']]) {
      expect(same(e, '')).toBe(true)
      expect(same('', e)).toBe(true)
    }
  })
  it('empty vs non-empty is a change', () => {
    expect(same('', 'x')).toBe(false)
    expect(same([], ['a'])).toBe(false)
  })
  it('primitives compare by ===', () => {
    expect(same('x', 'x')).toBe(true)
    expect(same('x', 'y')).toBe(false)
    expect(same(true, true)).toBe(true)
    expect(same(true, false)).toBe(false)
  })
  it('arrays compare element-wise, order-sensitive', () => {
    expect(same(['a', 'b'], ['a', 'b'])).toBe(true)
    expect(same(['a', 'b'], ['b', 'a'])).toBe(false)
    expect(same(['a'], ['a', 'b'])).toBe(false)
  })
})
