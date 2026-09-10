import { describe, it, expect, vi } from 'vitest'
import { createFieldManager } from './fieldManager'
import type { FormSchema } from '../schema-forms/types/schema'

const mk = (fields: any[]) => ({
  source: 'web',
  form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
  fields,
  sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
} as unknown as FormSchema)

// EVERY combination of (what the id resolves to) x (what the name query finds).
const CASES: Array<[string, string, any, string, unknown]> = [
  ['text, no collision',        `<input id="a" name="a" type="text" value="v" />`,
   { id: 'a', type: 'text' }, 'a', 'v'],
  ['text vs radio-group name',  `<input id="a" name="a_t" type="text" value="v" /><input name="a" type="radio" value="M" />`,
   { id: 'a', type: 'text' }, 'a', 'v'],
  ['text vs bracketed name',    `<input id="a" name="a_t" type="text" value="v" /><input name="a[]" type="checkbox" value="X" />`,
   { id: 'a', type: 'text' }, 'a', 'v'],
  ['text NAMED bracketed',      `<input id="a" name="a[]" type="text" value="v" />`,
   { id: 'a', type: 'text' }, 'a', 'v'],
  // With REAL group members present, so the bracketed query returns a mix and
  // the source-level type filter is actually exercised. Without a sibling group
  // the filter is never consulted and this row would pass either way.
  ['text NAMED bracketed, group present',
   `<input id="a" name="a[]" type="text" value="v" /><input name="a[]" type="checkbox" value="X" />`,
   { id: 'a', type: 'text' }, 'a', 'v'],
  ['standalone cb vs group',    `<input id="a" name="agree" type="checkbox" value="y" /><input name="a[]" type="checkbox" value="X" />`,
   { id: 'a', type: 'checkbox' }, 'a', 'y'],
  ['standalone radio vs group', `<input id="a" name="mar" type="radio" value="s" /><input name="a" type="radio" value="M" />`,
   { id: 'a', type: 'radio', options: [{ value: 's', label: 'S' }] }, 'a', 's'],
  ['select vs bracketed name',  `<select id="a" name="a_s"><option value="b" selected>B</option></select><input name="a[]" type="checkbox" value="X" />`,
   { id: 'a', type: 'select', options: [] }, 'a', 'b'],
  ['textarea vs bracketed',     `<textarea id="a" name="a_t">v</textarea><input name="a[]" type="checkbox" value="X" />`,
   { id: 'a', type: 'textarea' }, 'a', 'v'],
]

/**
 * THE COMPLETE id-vs-name collision matrix (bd polyglot-pdf-96um6).
 *
 * Ids and names share no namespace in HTML, so a field's id can collide with
 * ANOTHER field's group name -- and this bead's group-by-name resolution turned
 * that into three separate regressions, each found one at a time by a reviewer
 * after I fixed the previous one:
 *
 *   1. a text field whose ID collides with a group's NAME  -> wrong value, or none
 *   2. a text field whose own NAME matches the bracketed query -> edits reported
 *      under the GROUP's id, overwriting the group's answer
 *   3. a STANDALONE checkbox/radio whose id collides with a group name -> no
 *      listener at all
 *
 * CLAUDE.md scar #8 says to pin the SET rather than the instance, so this
 * enumerates every combination of (what the id resolves to) x (what the name
 * query finds) instead of the three shapes that happened to be reported. A
 * fourth shape fails HERE rather than in a fourth review round.
 */
describe('MATRIX: every id-vs-name collision shape', () => {
  it.each(CASES)('%s', (_label, html, field, expectId, expectValue) => {
    document.body.innerHTML = html
    const onManualEdit = vi.fn()
    createFieldManager({ schema: mk([{ name: 'F', spoken_name: 'f', ...field }]), onManualEdit })
    const el = document.getElementById('a') as HTMLInputElement
    if (el.type === 'checkbox' || el.type === 'radio') el.checked = true
    el.dispatchEvent(new Event('change', { bubbles: true }))
    const call = onManualEdit.mock.calls.at(-1)
    expect(call?.[0], 'reported field id').toBe(expectId)
    expect(call?.[1], 'reported value').toEqual(expectValue)
  })

  it('a REAL group still reports the array', () => {
    document.body.innerHTML = `<input id="a" name="a[]" type="checkbox" value="X" checked /><input name="a[]" type="checkbox" value="Y" />`
    const onManualEdit = vi.fn()
    createFieldManager({ schema: mk([{ id: 'a', name: 'F', spoken_name: 'f', type: 'checkbox_group', options: [{ value: 'X', label: 'X' }, { value: 'Y', label: 'Y' }] }]), onManualEdit })
    const y = document.querySelectorAll('input')[1] as HTMLInputElement
    y.checked = true
    y.dispatchEvent(new Event('change', { bubbles: true }))
    expect(onManualEdit.mock.calls.at(-1)?.[1]).toEqual(['X', 'Y'])
  })
})
