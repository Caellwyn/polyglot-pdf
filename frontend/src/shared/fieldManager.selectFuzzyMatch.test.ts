/**
 * Regression tests for handleSelect's fuzzy match on short PDF export codes
 * (bd polyglot-pdf-jbek5).
 *
 * The bidirectional substring fuzzy-match branch was written when a select's
 * option.value was a long minted slug ('wyoming'), where accidental
 * containment was unlikely. Since bd polyglot-pdf-4we6j a select's
 * option.value can be the PDF's own short export code ('WY', 'AL', 'AK'),
 * and short codes collide readily under substring matching: 'al' is a
 * substring of both 'alaska' and 'alabama' by TEXT containment, and the old
 * first-hit-wins loop silently picked whichever option came first, writing a
 * wrong answer onto a legal form with no warning (the "no match" warn only
 * fired when NOTHING matched).
 *
 * Drives the real public API (createFieldManager().applyUpdates) against a
 * jsdom DOM, since handleSelect operates on document.querySelectorAll.
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

describe('fieldManager select fuzzy match (bd polyglot-pdf-jbek5)', () => {
  let mgr: ReturnType<typeof createFieldManager>
  let warnSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    mgr = createFieldManager()
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    mgr.destroy()
    document.body.innerHTML = ''
    warnSpy.mockRestore()
  })

  it('selects the exact option for the exact-criterion case: value "AL" against short state codes', () => {
    const select = selectField('state', [
      ['AL', 'Alabama'],
      ['AK', 'Alaska'],
      ['CA', 'California'],
    ])
    mgr.applyUpdates([{ fieldId: 'state', value: 'AL' }])
    expect(select.value).toBe('AL')
    expect(select.selectedOptions[0].text).toBe('Alabama')
  })

  it('is case-insensitive for the same short-code case, via the case-insensitive-exact tier specifically', () => {
    // Lowercase 'al' cannot hit tier 1 (option.value === 'AL' is a strict,
    // case-sensitive ===), so this can only pass via the new tier-2
    // case-insensitive-exact match, or by accidentally falling through to
    // the tier-3 fuzzy match (since 'al' is ALSO a substring of 'alabama').
    // Alaska is listed FIRST so a jsdom selected-index default of 0 (i.e.
    // "nothing actually matched") would read back as Alaska, not Alabama --
    // this distinguishes a real tier-2 hit from a vacuous pass.
    const select = selectField('state', [
      ['AK', 'Alaska'],
      ['AL', 'Alabama'],
      ['CA', 'California'],
    ])
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    mgr.applyUpdates([{ fieldId: 'state', value: 'al' }])
    expect(select.value).toBe('AL')
    expect(select.selectedOptions[0].text).toBe('Alabama')
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] [check] Case-insensitive exact match for select:', 'state', '->', 'Alabama')
    logSpy.mockRestore()
  })

  it.each([
    ['Crabapple listed first', ['crab', 'Crabapple'], ['cab', 'Cabbage']],
    ['Cabbage listed first', ['cab', 'Cabbage'], ['crab', 'Crabapple']],
  ])('selects nothing (and warns) for an ambiguous fuzzy match, regardless of option order (%s)', (_label, first, second) => {
    // 'ab' is a substring of neither option's VALUE, but is a substring of
    // BOTH 'crabapple' AND 'cabbage' by TEXT -- genuinely ambiguous, no
    // exact or case-insensitive-exact hit anywhere to break the tie. The
    // old first-hit-wins loop would have picked whichever option is
    // listed first; this must select NEITHER, in either order.
    const select = selectField('fruit', [first as [string, string], second as [string, string]])
    const before = select.value
    mgr.applyUpdates([{ fieldId: 'fruit', value: 'ab' }])
    expect(select.value).toBe(before)
    expect(warnSpy).toHaveBeenCalled()
  })

  it('still selects via fuzzy substring match when the match is genuinely unique', () => {
    // 'america' is not case-insensitive-equal to any option's value/text (so
    // tier 2 cannot fire), but is a genuine, unique substring of 'United
    // States of America' by TEXT containment -- this can only pass via
    // tier 3's collect-then-apply-if-unique branch.
    const select = selectField('country', [
      ['us', 'United States of America'],
      ['uk', 'United Kingdom'],
      ['fr', 'France'],
    ])
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    mgr.applyUpdates([{ fieldId: 'country', value: 'america' }])
    expect(select.value).toBe('us')
    expect(logSpy).toHaveBeenCalledWith(
      '[VFF FieldManager] ~= Fuzzy match for select:', 'country', '->', 'United States of America')
    logSpy.mockRestore()
  })

  it('exact match still wins over fuzzy/case-insensitive tiers (control, unchanged)', () => {
    const select = selectField('state', [
      ['AL', 'Alabama'],
      ['AK', 'Alaska'],
    ])
    mgr.applyUpdates([{ fieldId: 'state', value: 'AK' }])
    expect(select.value).toBe('AK')
  })

  it('clearing with an empty value is unchanged', () => {
    const select = selectField('state', [
      ['', '-- Select --'],
      ['AL', 'Alabama'],
      ['AK', 'Alaska'],
    ])
    select.value = 'AL'
    mgr.applyUpdates([{ fieldId: 'state', value: '' }])
    expect(select.selectedIndex).toBe(0)
  })
})
