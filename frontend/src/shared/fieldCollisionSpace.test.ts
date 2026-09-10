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

function domFor(own: string, neigh: string): string {
  const self =
    own === 'select'   ? `<select id="f" name="f_own"><option value="v">v</option></select>`
  : own === 'textarea' ? `<textarea id="f" name="f_own"></textarea>`
  : `<input id="f" name="f_own" type="${own}" value="v" />`
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
      it(`own=${own} neighbour=${neigh}`, () => {
        document.body.innerHTML = domFor(own, neigh)
        const schema = mk({ id: 'f', name: 'F', spoken_name: 'f', type: own === 'select' ? 'select' : own,
                            ...(own === 'radio' ? { options: [{ value: 'v', label: 'v' }] } : {}) })
        restoreDOMFromSessionStorage(
          { fieldValues: { f: { value: own === 'checkbox' ? true : 'v', confirmed: false } } } as any, schema)

        const el = document.getElementById('f') as any
        const got = (own === 'checkbox' || own === 'radio') ? el.checked : el.value
        const want = (own === 'checkbox' || own === 'radio') ? true : 'v'
        expect(got, `own=${own} neighbour=${neigh} must receive its own value`).toEqual(want)

        // And the unrelated neighbour must never be written.
        if (neigh !== 'none') {
          const others = Array.from(document.querySelectorAll('input[name="f"], input[name="f[]"]')) as HTMLInputElement[]
          expect(others.some(o => o.checked), `neighbour must not be touched (${own}/${neigh})`).toBe(false)
        }
      })
    }
  }
})
