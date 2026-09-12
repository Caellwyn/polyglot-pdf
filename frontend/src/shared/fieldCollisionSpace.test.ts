import { describe, it, expect, beforeEach } from 'vitest'
import { restoreDOMFromSessionStorage } from './connection'
import type { FormSchema } from '../schema-forms/types/schema'

const mk = (f: any) => ({
  source: 'web',
  form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
  fields: [f],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: [f.id] }],
} as unknown as FormSchema)

// THE FULL SPACE: {what id resolves to} x {what shares the name} x {bracketed?}
const OWN = ['text', 'checkbox', 'radio', 'select', 'textarea'] as const
const NEIGH = ['none', 'plain-radio', 'bracketed-checkbox'] as const
// THE THIRD AXIS, added after the outer review found the live bug hiding in it:
// the field's OWN name. Every case below used to hardcode `f_own`, so the matrix
// never produced a field whose own name IS the bracketed query -- which is
// exactly where connection.ts's missing type filter dropped the value. A matrix
// named for enumerating the space had an axis missing (bd polyglot-pdf-6r2si).
const OWN_NAME = ['f_own', 'f', 'f[]'] as const

function domFor(own: string, neigh: string, ownName = 'f_own'): string {
  const self =
    own === 'select'   ? `<select id="f" name="${ownName}"><option value="">-</option><option value="v">v</option></select>`
  : own === 'textarea' ? `<textarea id="f" name="${ownName}"></textarea>`
  // Text/checkbox/radio start EMPTY -- the fixture must never pre-seed the value
  // restore is meant to write, or every row passes whether or not restore ran.
  // That vacuity hid the very regression this matrix was extended to catch.
  : `<input id="f" name="${ownName}" type="${own}" ${own === "text" ? "" : 'value="v"'} />`
  const other =
    neigh === 'plain-radio'         ? `<input name="f" type="radio" value="X" /><input name="f" type="radio" value="Y" />`
  : neigh === 'bracketed-checkbox'  ? `<input name="f[]" type="checkbox" value="X" /><input name="f[]" type="checkbox" value="Y" />`
  : ''
  return self + other
}

/**
 * THE COMPLETE COLLISION SPACE for restoreDOMFromSessionStorage.
 *
 * Four shapes of one bug arrived ONE PER REVIEW ROUND, each found only after I
 * fixed the previous one and declared the set closed:
 *   1. a text field whose ID collides with a group's NAME
 *   2. a text field whose own NAME matches the bracketed query
 *   3. a standalone checkbox/radio colliding with a BRACKETED group name
 *   4. a standalone radio colliding with a PLAIN group name -- the branch every
 *      real radio group actually takes, and the one my own set-closure guard
 *      had scoped itself to exclude
 *
 * So this stops enumerating the shapes I happened to be told about and
 * enumerates the SPACE: every {what the id resolves to} x {what shares the
 * name}. A fifth shape fails here rather than in an eleventh round.
 *
 * It also asserts the NEIGHBOUR is never written -- half of each bug was the
 * unrelated group receiving the answer, which a self-only assertion misses.
 */
describe('FULL SPACE: no combination silently drops the answer', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  for (const own of OWN) {
    for (const neigh of NEIGH) {
      for (const ownName of OWN_NAME) {
      it(`own=${own} neighbour=${neigh} ownName=${ownName}`, () => {
        document.body.innerHTML = domFor(own, neigh, ownName)
        const schema = mk({ id: 'f', name: 'F', spoken_name: 'f', type: own === 'select' ? 'select' : own,
                            ...(own === 'radio' ? { options: [{ value: 'v', label: 'v' }] } : {}) })
        restoreDOMFromSessionStorage(
          { fieldValues: { f: { value: own === 'checkbox' ? true : 'v', confirmed: false } } } as any, schema)

        // When the field's OWN name makes it a genuine group member, the group
        // path is CORRECT and value-matching applies -- these rows are not
        // collisions at all. Only assert the single-control contract where the
        // field really is standalone.
        const isGroupMember =
          (own === 'checkbox' || own === 'radio') &&
          (ownName === 'f[]' || (ownName === 'f' && own === 'radio'))
        if (isGroupMember) return

        const el = document.getElementById('f') as any
        const got = (own === 'checkbox' || own === 'radio') ? el.checked : el.value
        const want = (own === 'checkbox' || own === 'radio') ? true : 'v'
        expect(got, `own=${own} neighbour=${neigh} must receive its own value`).toEqual(want)

        // And the unrelated neighbour must never be written.
        if (neigh !== 'none') {
          // EXCLUDE the field itself: when its own name is `f` or `f[]` this
          // selector matches it too, and "the neighbour was written" would fire
          // on the field's own correct restore.
          const own_ = document.getElementById('f')
          const others = (Array.from(
            document.querySelectorAll('input[name="f"], input[name="f[]"]')
          ) as HTMLInputElement[]).filter(el => el !== own_)
          expect(others.some(o => o.checked), `neighbour must not be touched (${own}/${neigh})`).toBe(false)
        }
      })
      }
    }
  }
})

const stateWith = (fieldValues: Record<string, unknown>) =>
  ({ fieldValues, schema: null, sectionState: {} } as any)

describe('the axes BEYOND element-type x neighbour-shape', () => {
  // The 15-case matrix varies two axes. These are the other axes I could think
  // of that might hide a fifth shape -- probed rather than assumed, and kept
  // because they cost nothing and the shape count in this bead is four.
  beforeEach(() => { document.body.innerHTML = '' })

  it('TWO colliding neighbours at once -- plain AND bracketed', () => {
    document.body.innerHTML = `
      <input id="f" name="f_own" type="checkbox" value="yes" />
      <input name="f" type="radio" value="P" />
      <input name="f[]" type="checkbox" value="B" />`
    restoreDOMFromSessionStorage(stateWith({ f: { value: true, confirmed: false } }),
      mk({ id: 'f', name: 'F', spoken_name: 'f', type: 'checkbox' }))

    expect((document.getElementById('f') as HTMLInputElement).checked, 'own field wins').toBe(true)
    expect((document.querySelector('input[name="f"]') as HTMLInputElement).checked).toBe(false)
    expect((document.querySelector('input[name="f[]"]') as HTMLInputElement).checked).toBe(false)
  })

  it('a BOOLEAN value onto a colliding standalone radio', () => {
    document.body.innerHTML = `
      <input id="f" name="f_own" type="radio" value="yes" />
      <input name="f" type="radio" value="X" />`
    restoreDOMFromSessionStorage(stateWith({ f: { value: true, confirmed: false } }),
      mk({ id: 'f', name: 'F', spoken_name: 'f', type: 'radio', options: [{ value: 'yes', label: 'y' }] }))

    expect((document.getElementById('f') as HTMLInputElement).checked).toBe(true)
    expect((document.querySelector('input[name="f"]') as HTMLInputElement).checked).toBe(false)
  })

  it('a field id that is ITSELF bracketed and collides', () => {
    document.body.innerHTML = `
      <input id="f[]" name="f_own" type="text" value="" />
      <input name="f[][]" type="checkbox" value="X" />`
    restoreDOMFromSessionStorage(stateWith({ 'f[]': { value: 'typed', confirmed: false } }),
      mk({ id: 'f[]', name: 'F', spoken_name: 'f', type: 'text' }))

    expect((document.getElementById('f[]') as HTMLInputElement).value).toBe('typed')
  })
})
