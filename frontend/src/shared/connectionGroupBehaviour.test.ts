import { describe, it, expect, beforeEach, vi } from 'vitest'
import { restoreDOMFromSessionStorage, capturePreFilledValues } from './connection'
import type { FormSchema } from '../schema-forms/types/schema'

/**
 * BEHAVIOUR tests that drive the REAL restoreDOMFromSessionStorage and
 * capturePreFilledValues -- not a mirror of their logic.
 *
 * The sibling file's source-reading guards are DEFEATABLE, and I defeated them:
 * appending `|| inputEl.type === 'checkbox'` to the membership test keeps every
 * grep-based assertion green while regressing shape 3. A guard that passes while
 * the rule is violated is worse than none, so these call the functions instead.
 * The two functions were made `export` for exactly this reason.
 */
const mk = (fields: any[]) => ({
  source: 'web',
  form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
  fields,
  sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
} as unknown as FormSchema)

const stateWith = (fieldValues: Record<string, unknown>) =>
  ({ fieldValues, schema: null, sectionState: {} } as any)

describe('restoreDOMFromSessionStorage -- real function, real DOM', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('SHAPE 3: a standalone checkbox colliding with a group name restores ITSELF', () => {
    const schema = mk([{ id: 'race', name: 'Agree', spoken_name: 'agree', type: 'checkbox' }])
    document.body.innerHTML = `
      <input id="race" name="agree" type="checkbox" value="yes" />
      <input name="race[]" type="checkbox" value="Asian" />
      <input name="race[]" type="checkbox" value="White" />`

    restoreDOMFromSessionStorage(stateWith({ race: { value: true, confirmed: false } }), schema)

    expect((document.getElementById('race') as HTMLInputElement).checked).toBe(true)
    const group = Array.from(document.querySelectorAll('input[name="race[]"]')) as HTMLInputElement[]
    expect(group.some(g => g.checked), 'the unrelated group must not be touched').toBe(false)
  })

  it('a REAL checkbox group restores the picked options', () => {
    const schema = mk([{ id: 'race', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
                         options: [{ value: 'Asian', label: 'A' }, { value: 'White', label: 'W' }] }])
    document.body.innerHTML = `
      <input id="race" name="race[]" type="checkbox" value="Asian" />
      <input name="race[]" type="checkbox" value="White" />`

    restoreDOMFromSessionStorage(stateWith({ race: { value: ['White'], confirmed: false } }), schema)

    const [asian, white] = Array.from(document.querySelectorAll('input')) as HTMLInputElement[]
    expect([asian.checked, white.checked]).toEqual([false, true])
  })

  it('a RADIO group selects the matching option', () => {
    const schema = mk([{ id: 'sex', name: 'Sex', spoken_name: 'sex', type: 'radio',
                         options: [{ value: 'Male', label: 'M' }, { value: 'Female', label: 'F' }] }])
    document.body.innerHTML = `
      <input id="sex" name="sex" type="radio" value="Male" />
      <input name="sex" type="radio" value="Female" />`

    restoreDOMFromSessionStorage(stateWith({ sex: { value: 'Female', confirmed: false } }), schema)

    const [male, female] = Array.from(document.querySelectorAll('input')) as HTMLInputElement[]
    expect([male.checked, female.checked]).toEqual([false, true])
  })

  it('a TEXT field colliding with a bracketed group name still restores', () => {
    const schema = mk([{ id: 'race', name: 'Race note', spoken_name: 'race note', type: 'text' }])
    document.body.innerHTML = `
      <input id="race" name="race_text" type="text" value="" />
      <input name="race[]" type="checkbox" value="Asian" />`

    restoreDOMFromSessionStorage(stateWith({ race: { value: 'typed', confirmed: false } }), schema)

    expect((document.getElementById('race') as HTMLInputElement).value).toBe('typed')
  })
})

describe('capturePreFilledValues -- real function, real DOM', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  const conn = () => {
    const updateField = vi.fn()
    return { stub: { updateField } as any, updateField }
  }

  it('SHAPE 3: captures the standalone field, not the unrelated groups picks', () => {
    const schema = mk([{ id: 'race', name: 'Agree', spoken_name: 'agree', type: 'checkbox' }])
    document.body.innerHTML = `
      <input id="race" name="agree" type="checkbox" value="yes" checked />
      <input name="race[]" type="checkbox" value="Asian" />
      <input name="race[]" type="checkbox" value="White" checked />`
    const { stub, updateField } = conn()

    capturePreFilledValues(stub, schema)

    expect(updateField).toHaveBeenCalledWith('race', true, expect.anything())
  })

  it('a REAL group captures the checked values as an array', () => {
    const schema = mk([{ id: 'race', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
                         options: [{ value: 'Asian', label: 'A' }, { value: 'White', label: 'W' }] }])
    document.body.innerHTML = `
      <input id="race" name="race[]" type="checkbox" value="Asian" />
      <input name="race[]" type="checkbox" value="White" checked />`
    const { stub, updateField } = conn()

    capturePreFilledValues(stub, schema)

    expect(updateField).toHaveBeenCalledWith('race', ['White'], expect.anything())
  })

  it('an empty group captures nothing', () => {
    const schema = mk([{ id: 'race', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
                         options: [{ value: 'Asian', label: 'A' }] }])
    document.body.innerHTML = `<input id="race" name="race[]" type="checkbox" value="Asian" />`
    const { stub, updateField } = conn()

    capturePreFilledValues(stub, schema)

    expect(updateField).not.toHaveBeenCalled()
  })
})
