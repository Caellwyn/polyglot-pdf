/**
 * Regression tests for clearing radio / checkbox groups (bd polyglot-pdf-qc46).
 *
 * An update_form_fields value of '' means "clear this field". Before the fix,
 * handleRadioGroup / handleCheckboxGroup / handleSingleRadio fell into a
 * fuzzy-match loop where `lowerValue.includes('')` (and the checkbox-group
 * `normalizedCheckbox.includes('')`) is true for EVERY option, so the FIRST
 * radio got selected (and every checkbox got checked) -- the opposite of
 * clearing. These tests pin the clear behavior across all three input shapes.
 *
 * Drives the real public API (createFieldManager().applyUpdates) against a
 * jsdom DOM, since the handlers operate on document.querySelectorAll.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createFieldManager } from './fieldManager'

function radioGroup(name: string, values: string[]): void {
  document.body.innerHTML = ''
  for (const v of values) {
    const input = document.createElement('input')
    input.type = 'radio'
    input.name = name
    input.value = v
    document.body.appendChild(input)
  }
}

function checkboxGroup(name: string, values: string[]): void {
  document.body.innerHTML = ''
  for (const v of values) {
    const input = document.createElement('input')
    input.type = 'checkbox'
    input.name = name
    input.value = v
    document.body.appendChild(input)
  }
}

function inputsByName(name: string): HTMLInputElement[] {
  return Array.from(
    document.querySelectorAll(`input[name="${name}"]`)
  ) as HTMLInputElement[]
}

describe('fieldManager radio/checkbox clear (bd polyglot-pdf-qc46)', () => {
  let mgr: ReturnType<typeof createFieldManager>

  beforeEach(() => {
    mgr = createFieldManager()
  })

  afterEach(() => {
    mgr.destroy()
    document.body.innerHTML = ''
  })

  it('selects the matching radio for a non-empty value (control)', () => {
    radioGroup('marital', ['single', 'married', 'divorced'])
    mgr.applyUpdates([{ fieldId: 'marital', value: 'married' }])
    const inputs = inputsByName('marital')
    expect(inputs.find(i => i.value === 'married')!.checked).toBe(true)
    expect(inputs.filter(i => i.checked)).toHaveLength(1)
  })

  it('clears the radio group (unchecks all) for an empty value, not first-option', () => {
    radioGroup('marital', ['single', 'married', 'divorced'])
    // Pre-select one so we can prove the clear actually unchecks it.
    inputsByName('marital')[1].checked = true

    mgr.applyUpdates([{ fieldId: 'marital', value: '' }])

    const inputs = inputsByName('marital')
    expect(inputs.filter(i => i.checked)).toHaveLength(0)
    // Specifically: the FIRST option must NOT have been selected (the old bug).
    expect(inputs[0].checked).toBe(false)
  })

  it('clears a single radio (found by id) for an empty value', () => {
    document.body.innerHTML = ''
    const input = document.createElement('input')
    input.type = 'radio'
    input.id = 'agree'
    input.value = 'yes'
    input.checked = true
    document.body.appendChild(input)

    mgr.applyUpdates([{ fieldId: 'agree', value: '' }])

    expect((document.getElementById('agree') as HTMLInputElement).checked).toBe(false)
  })

  it('checks the matching checkbox for a non-empty value (control)', () => {
    checkboxGroup('concerns', ['health', 'safety', 'finance'])
    mgr.applyUpdates([{ fieldId: 'concerns', value: 'safety' }])
    const inputs = inputsByName('concerns')
    expect(inputs.find(i => i.value === 'safety')!.checked).toBe(true)
  })

  it('clears the checkbox group (unchecks all) for an empty value, not check-all', () => {
    checkboxGroup('concerns', ['health', 'safety', 'finance'])
    inputsByName('concerns').forEach(i => { i.checked = true })

    mgr.applyUpdates([{ fieldId: 'concerns', value: '' }])

    expect(inputsByName('concerns').filter(i => i.checked)).toHaveLength(0)
  })

  it('clears the checkbox group for an all-empty array value', () => {
    checkboxGroup('concerns', ['health', 'safety', 'finance'])
    inputsByName('concerns').forEach(i => { i.checked = true })

    mgr.applyUpdates([{ fieldId: 'concerns', value: ['', ''] }])

    expect(inputsByName('concerns').filter(i => i.checked)).toHaveLength(0)
  })
})
