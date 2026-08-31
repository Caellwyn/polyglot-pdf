/**
 * Regression tests: an unmatched/ambiguous update must NOT be badged as
 * AI-confirmed (bd polyglot-pdf-c6t0e).
 *
 * applyUpdates used to set data-vff-confirmed + add the green checkmark
 * badge, and report results.success, UNCONDITIONALLY whenever an element
 * was resolved for a select or single radio -- it never consulted whether
 * handleSelect/handleSingleRadio actually applied a value. A no-match (or,
 * since bd polyglot-pdf-jbek5, an ambiguous fuzzy match) left the field
 * EMPTY but still decorated as AI-confirmed -- a misleading signal on a
 * legal intake form. Radio/checkbox GROUPS had a related but distinct bug:
 * their success was tracked in a separate unconditional push in
 * applyUpdates itself (they never reach the blanket badge block below),
 * so a totally-unmatched group reported success with NO badge at all --
 * arguably worse, since nothing in the DOM even hints a value was
 * attempted.
 *
 * Drives the real public API (createFieldManager().applyUpdates) against a
 * jsdom DOM.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createFieldManager } from './fieldManager'

function selectField(name: string, options: Array<[value: string, text: string]>): HTMLSelectElement {
  document.body.innerHTML = ''
  const select = document.createElement('select')
  select.name = name
  for (const [value, text] of options) {
    const opt = document.createElement('option')
    opt.value = value
    opt.text = text
    select.appendChild(opt)
  }
  document.body.appendChild(select)
  return select
}

function radioGroup(name: string, values: string[]): HTMLInputElement[] {
  document.body.innerHTML = ''
  const inputs: HTMLInputElement[] = []
  for (const v of values) {
    const input = document.createElement('input')
    input.type = 'radio'
    input.name = name
    input.value = v
    document.body.appendChild(input)
    inputs.push(input)
  }
  return inputs
}

function singleRadio(id: string, value: string): HTMLInputElement {
  document.body.innerHTML = ''
  const input = document.createElement('input')
  input.type = 'radio'
  input.id = id
  input.value = value
  document.body.appendChild(input)
  return input
}

function checkboxGroup(name: string, values: string[]): HTMLInputElement[] {
  document.body.innerHTML = ''
  const inputs: HTMLInputElement[] = []
  for (const v of values) {
    const input = document.createElement('input')
    input.type = 'checkbox'
    input.name = name
    input.value = v
    document.body.appendChild(input)
    inputs.push(input)
  }
  return inputs
}

function hasBadge(el: HTMLElement): boolean {
  return el.parentElement?.querySelector('.vff-field-badge') != null
}

describe('fieldManager confirmation badge only on an actual match (bd polyglot-pdf-c6t0e)', () => {
  let mgr: ReturnType<typeof createFieldManager>
  let warnSpy: ReturnType<typeof vi.spyOn>
  let logSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    mgr = createFieldManager()
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    mgr.destroy()
    document.body.innerHTML = ''
    warnSpy.mockRestore()
    logSpy.mockRestore()
  })

  it('a genuine select match DOES get the badge and reports success', () => {
    const select = selectField('state', [['AL', 'Alabama'], ['AK', 'Alaska']])
    mgr.applyUpdates([{ fieldId: 'state', value: 'AL' }])
    expect(select.getAttribute('data-vff-confirmed')).toBe('true')
    expect(hasBadge(select)).toBe(true)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 1, notFound: 0 }))
  })

  it('a total non-match select gets NO badge and is NOT reported as success', () => {
    const select = selectField('state', [['AL', 'Alabama'], ['AK', 'Alaska']])
    mgr.applyUpdates([{ fieldId: 'state', value: 'Wyoming' }])
    expect(select.hasAttribute('data-vff-confirmed')).toBe(false)
    expect(hasBadge(select)).toBe(false)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 0, notFound: 1 }))
  })

  it('an ambiguous fuzzy select match (bd jbek5) gets NO badge and is NOT reported as success', () => {
    // 'ab' matches both 'Crabapple' and 'Cabbage' by text containment --
    // handleSelect's fuzzy tier deliberately selects nothing for this.
    const select = selectField('fruit', [['crab', 'Crabapple'], ['cab', 'Cabbage']])
    mgr.applyUpdates([{ fieldId: 'fruit', value: 'ab' }])
    expect(select.hasAttribute('data-vff-confirmed')).toBe(false)
    expect(hasBadge(select)).toBe(false)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 0, notFound: 1 }))
  })

  it('a genuine single-radio match (found by id) DOES get the badge', () => {
    const radio = singleRadio('agree', 'yes')
    mgr.applyUpdates([{ fieldId: 'agree', value: 'yes' }])
    expect(radio.checked).toBe(true)
    expect(radio.getAttribute('data-vff-confirmed')).toBe('true')
    expect(hasBadge(radio)).toBe(true)
  })

  it('a single-radio value mismatch gets NO badge and is NOT reported as success', () => {
    const radio = singleRadio('agree', 'yes')
    mgr.applyUpdates([{ fieldId: 'agree', value: 'no' }])
    expect(radio.checked).toBe(false)
    expect(radio.hasAttribute('data-vff-confirmed')).toBe(false)
    expect(hasBadge(radio)).toBe(false)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 0, notFound: 1 }))
  })

  it('a genuine radio GROUP match DOES get the badge and reports success', () => {
    const [single, married] = radioGroup('marital', ['single', 'married'])
    mgr.applyUpdates([{ fieldId: 'marital', value: 'married' }])
    expect(married.checked).toBe(true)
    expect(married.getAttribute('data-vff-confirmed')).toBe('true')
    expect(hasBadge(married)).toBe(true)
    expect(single.checked).toBe(false)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 1, notFound: 0 }))
  })

  it('an unmatched radio GROUP reports notFound, not success (the bug: it previously reported success with no badge at all)', () => {
    const [single, married] = radioGroup('marital', ['single', 'married'])
    mgr.applyUpdates([{ fieldId: 'marital', value: 'divorced' }])
    expect(single.checked).toBe(false)
    expect(married.checked).toBe(false)
    expect(single.hasAttribute('data-vff-confirmed')).toBe(false)
    expect(married.hasAttribute('data-vff-confirmed')).toBe(false)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 0, notFound: 1 }))
  })

  it('a checkbox group with at least one real match reports success', () => {
    const [health] = checkboxGroup('concerns', ['health', 'safety'])
    mgr.applyUpdates([{ fieldId: 'concerns', value: ['health'] }])
    expect(health.checked).toBe(true)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 1, notFound: 0 }))
  })

  it('a checkbox group where NOTHING matches reports notFound, not success', () => {
    const [health, safety] = checkboxGroup('concerns', ['health', 'safety'])
    mgr.applyUpdates([{ fieldId: 'concerns', value: ['finance'] }])
    expect(health.checked).toBe(false)
    expect(safety.checked).toBe(false)
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [chart] Update summary:',
      expect.objectContaining({ success: 0, notFound: 1 }))
  })

  it('a no-match select does not leave a same-tick window where a later change event misfires onManualEdit (bd polyglot-pdf-pg0m6)', () => {
    // The no-match branch itself dispatches change/input SYNCHRONOUSLY
    // inside applyUpdates, so a test driving only THAT dispatch cannot
    // distinguish a synchronous vs. deferred aiUpdatingFields clear --
    // handleEdit always runs and returns early before either clear takes
    // effect (this was my first, wrong attempt at pinning this). The
    // clear's timing actually matters for a SECOND, LATER change event --
    // e.g. a controlled re-render or a genuinely-coincident user
    // interaction -- landing in the same tick AFTER applyUpdates returns.
    // With a synchronous clear, aiUpdatingFields is already empty by then,
    // so that second event is misread as a manual edit even though it is
    // really just the tail of the AI's own update.
    const select = selectField('state', [['AL', 'Alabama'], ['AK', 'Alaska']])
    select.id = 'state'
    const onManualEdit = vi.fn()
    const scopedMgr = createFieldManager({
      onManualEdit,
      schema: { fields: [{ id: 'state' }] },
    })
    scopedMgr.applyUpdates([{ fieldId: 'state', value: 'Wyoming' }]) // no-match
    // Simulate a change event landing right after applyUpdates returns,
    // still within the guard's intended window.
    select.value = 'AK'
    select.dispatchEvent(new Event('change', { bubbles: true }))
    expect(onManualEdit).not.toHaveBeenCalled()
    scopedMgr.destroy()
  })

  it('a no-match fill on a field NOT yet in the DOM at construction still gets a manual-edit listener attached (bd polyglot-pdf-c6t0e, Opus round 3)', () => {
    // The bug this pins: setupEditListener used to live INSIDE the
    // matched-only branch, so a no-match fill left the field with NO
    // listener at all. setupAllFieldListeners only finds elements present
    // in the DOM at FieldManager CONSTRUCTION time (SchemaForm renders one
    // section at a time), so for a field added to the DOM later, THIS
    // call inside applyUpdates is its only chance to ever get a listener.
    // Construct the manager BEFORE the select exists (mirroring a later
    // section rendering after construction), fill it with a non-matching
    // value, then add a genuine LATER manual edit and confirm it still
    // reaches onManualEdit -- a real correction on a field the AI failed
    // to fill must never be silently dropped.
    document.body.innerHTML = ''
    const onManualEdit = vi.fn()
    const scopedMgr = createFieldManager({
      onManualEdit,
      schema: { fields: [{ id: 'state' }] }, // field not in the DOM yet
    })
    const select = document.createElement('select')
    select.id = 'state'
    for (const [value, text] of [['AL', 'Alabama'], ['AK', 'Alaska']] as const) {
      const opt = document.createElement('option')
      opt.value = value
      opt.text = text
      select.appendChild(opt)
    }
    document.body.appendChild(select) // now the field exists

    scopedMgr.applyUpdates([{ fieldId: 'state', value: 'Wyoming' }]) // no-match

    // A genuine manual edit some time later (past the 50ms guard window).
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        select.value = 'AK'
        select.dispatchEvent(new Event('change', { bubbles: true }))
        expect(onManualEdit).toHaveBeenCalledWith('state', 'AK')
        scopedMgr.destroy()
        resolve()
      }, 60)
    })
  })
})
