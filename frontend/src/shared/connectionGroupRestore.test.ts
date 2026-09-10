import { describe, it, expect, beforeEach } from 'vitest'

/**
 * The RESTORE and CAPTURE halves of connection.ts, for a CHECKBOX GROUP.
 *
 * Both were dead for groups before bd polyglot-pdf-96um6: they resolve by
 * getElementById (null for a group, which carried no id) then fall back to
 * `input[name="race"]`, which never matches the real name `race[]`. Giving
 * option[0] an id made both paths LIVE, and both then treated the group as a
 * single boolean checkbox.
 *
 * These mirror the two loops' branch logic. The functions are module-private,
 * so this pins the DOM contract they implement rather than importing them.
 */
function renderGroup() {
  document.body.innerHTML = `
    <input id="race" name="race[]" type="checkbox" value="Asian" />
    <input name="race[]" type="checkbox" value="White" />`
  return Array.from(document.querySelectorAll('input')) as HTMLInputElement[]
}

function restore(fieldId: string, value: unknown) {
  const groupEls = document.querySelectorAll(`input[name="${fieldId}[]"]`) as NodeListOf<HTMLInputElement>
  if (groupEls.length) {
    const picked = Array.isArray(value) ? value.map(String) : [String(value)]
    groupEls.forEach(el => { el.checked = picked.includes(el.value) })
  }
}

function capture(fieldId: string): string | string[] | boolean | null {
  const groupEls = document.querySelectorAll(`input[name="${fieldId}[]"]`) as NodeListOf<HTMLInputElement>
  if (groupEls.length) {
    const picked = Array.from(groupEls).filter(el => el.checked).map(el => el.value)
    return picked.length ? picked : null
  }
  return null
}

describe('checkbox group restore/capture (bd polyglot-pdf-96um6)', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('restore checks the option the user PICKED, not option[0]', () => {
    // Boolean(['White']) is true, so the single-checkbox branch checked option[0]
    // whatever the user chose -- a silently wrong race answer on an immigration form.
    const [asian, white] = renderGroup()
    restore('race', ['White'])
    expect(asian.checked, 'option[0] must not be checked by a non-matching answer').toBe(false)
    expect(white.checked).toBe(true)
  })

  it('restore handles a multi-select', () => {
    const [asian, white] = renderGroup()
    restore('race', ['Asian', 'White'])
    expect([asian.checked, white.checked]).toEqual([true, true])
  })

  it('restore clears an option absent from the saved answer', () => {
    const [asian, white] = renderGroup()
    asian.checked = true
    restore('race', ['White'])
    expect(asian.checked, 'a stale selection must be cleared').toBe(false)
    expect(white.checked).toBe(true)
  })

  it('capture returns the SELECTION, never the boolean true', () => {
    // This path stores {confirmed: true}, so capturing `true` would have marked
    // a boolean as a VERIFIED answer -- contradicting this bead's whole thesis.
    const [, white] = renderGroup()
    white.checked = true
    expect(capture('race')).toEqual(['White'])
  })

  it('capture returns null when nothing is picked', () => {
    renderGroup()
    expect(capture('race')).toBeNull()
  })
})


describe('an id/name COLLISION must not hijack restore or capture', () => {
  // I assumed the "[]" suffix made the group lookup unambiguous. It does not:
  // the query is keyed on the field's OWN id, so a text field id="race" beside a
  // checkbox group name="race[]" took the group branch and restored NOTHING.
  // Measured before fixing. Same root cause as the fieldManager collision, in
  // code I had written two commits earlier.
  beforeEach(() => { document.body.innerHTML = '' })

  function restoreGated(fieldId: string, value: unknown) {
    const el = document.getElementById(fieldId) as HTMLInputElement | null
    if (!el) return
    const isGroupMember = el.type === 'radio' || el.type === 'checkbox'
    const groupEls = isGroupMember
      ? Array.from(document.querySelectorAll(`input[name="${fieldId}[]"]`) as NodeListOf<HTMLInputElement>)
      : []
    if (groupEls.length) {
      const picked = Array.isArray(value) ? value.map(String) : [String(value)]
      groupEls.forEach(e => { e.checked = picked.includes(e.value) })
    } else if (el.type === 'radio') {
      const radios = document.querySelectorAll(`input[name="${fieldId}"]`) as NodeListOf<HTMLInputElement>
      radios.forEach(e => { e.checked = e.value === String(value) })
    } else if (el.type === 'checkbox') {
      el.checked = Boolean(value)
    } else {
      el.value = String(value)
    }
  }

  it('a text field colliding with a CHECKBOX groups bracketed name still restores', () => {
    document.body.innerHTML = `
      <input id="race" name="race_text" type="text" value="" />
      <input name="race[]" type="checkbox" value="Asian" />`
    restoreGated('race', 'typed answer')
    expect((document.getElementById('race') as HTMLInputElement).value).toBe('typed answer')
  })

  it('a text field colliding with a RADIO groups name restores, touching no radio', () => {
    document.body.innerHTML = `
      <input id="sex" name="sex_text" type="text" value="" />
      <input name="sex" type="radio" value="Male" />
      <input name="sex" type="radio" value="Female" />`
    restoreGated('sex', 'Maria')
    expect((document.getElementById('sex') as HTMLInputElement).value).toBe('Maria')
    const radios = Array.from(document.querySelectorAll('input[type=radio]')) as HTMLInputElement[]
    expect(radios.some(r => r.checked), 'no radio must be touched').toBe(false)
  })

  it('a REAL group still restores -- so the gate did not break the thing it guards', () => {
    document.body.innerHTML = `
      <input id="race" name="race[]" type="checkbox" value="Asian" />
      <input name="race[]" type="checkbox" value="White" />`
    restoreGated('race', ['White'])
    const [asian, white] = Array.from(document.querySelectorAll('input')) as HTMLInputElement[]
    expect([asian.checked, white.checked]).toEqual([false, true])
  })
})

describe('SHAPE 3: a standalone group-type field colliding with a group name', () => {
  // I fixed this in fieldManager and told the review that connection.ts's
  // divergent spelling was "NOT drift". That was true when I checked it -- and
  // false the moment I added the membership dimension without carrying it here.
  // The reviewer caught it one commit later. Both sites now test MEMBERSHIP.
  beforeEach(() => { document.body.innerHTML = '' })

  function restore(fieldId: string, value: unknown) {
    const el = document.getElementById(fieldId) as HTMLInputElement | null
    if (!el) return
    const memberEls = Array.from(
      document.querySelectorAll(`input[name="${fieldId}[]"]`)
    ) as HTMLInputElement[]
    const isGroupMember = memberEls.includes(el)
    const groupEls = isGroupMember ? memberEls : []
    if (groupEls.length) {
      const picked = Array.isArray(value) ? value.map(String) : [String(value)]
      groupEls.forEach(e => { e.checked = picked.includes(e.value) })
    } else if (el.type === 'checkbox') {
      el.checked = Boolean(value)
    } else {
      el.value = String(value)
    }
  }

  function capture(fieldId: string): string | string[] | boolean | null {
    const el = document.getElementById(fieldId) as HTMLInputElement | null
    if (!el) return null
    const memberEls = Array.from(
      document.querySelectorAll(`input[name="${fieldId}[]"]`)
    ) as HTMLInputElement[]
    if (memberEls.includes(el)) {
      const picked = memberEls.filter(e => e.checked).map(e => e.value)
      return picked.length ? picked : null
    }
    return el.type === 'checkbox' ? el.checked : (el.value || null)
  }

  function render() {
    document.body.innerHTML = `
      <input id="race" name="agree" type="checkbox" value="yes" />
      <input name="race[]" type="checkbox" value="Asian" />
      <input name="race[]" type="checkbox" value="White" />`
  }

  it('RESTORE writes the standalone field, never the unrelated group', () => {
    render()
    restore('race', true)
    expect((document.getElementById('race') as HTMLInputElement).checked).toBe(true)
    const group = Array.from(document.querySelectorAll('input[name="race[]"]')) as HTMLInputElement[]
    expect(group.some(g => g.checked), 'the unrelated group must not be touched').toBe(false)
  })

  it('CAPTURE reads the standalone field, never the unrelated groups picks', () => {
    render()
    ;(document.getElementById('race') as HTMLInputElement).checked = true
    ;(document.querySelectorAll('input[name="race[]"]')[1] as HTMLInputElement).checked = true
    expect(capture('race'), 'must be the standalone boolean, not ["White"]').toBe(true)
  })

  it('a REAL group member still round-trips -- membership cuts both ways', () => {
    document.body.innerHTML = `
      <input id="race" name="race[]" type="checkbox" value="Asian" />
      <input name="race[]" type="checkbox" value="White" />`
    restore('race', ['White'])
    expect(capture('race')).toEqual(['White'])
  })
})

describe('the mirrors above cannot drift from the real functions', () => {
  // restoreDOMFromSessionStorage and capturePreFilledValues are module-private,
  // so the tests above necessarily MIRROR their logic. A mirror nothing pins is
  // worse than no test: it keeps passing while production regresses.
  //
  // The sibling guard in manualEditDoesNotVerify.test.ts exists for exactly this
  // reason. I wrote that one, then shipped this mirror without it -- the omission
  // scar #8 warns about: pin the SET, not the instance.
  const readSource = (): string => {
    const fs = require('fs') as typeof import('fs')
    const path = require('path') as typeof import('path')
    return fs.readFileSync(path.join(__dirname, 'connection.ts'), 'utf8')
  }

  // Body of a named top-level function, without matching its own declaration.
  const bodyOf = (src: string, name: string): string => {
    const at = src.indexOf('function ' + name)
    expect(at, 'expected ' + name + ' to still exist in connection.ts').toBeGreaterThan(-1)
    const rest = src.slice(at + 'function '.length)
    const end = rest.indexOf('\nfunction ')
    return end === -1 ? rest : rest.slice(0, end)
  }

  it('BOTH sites gate on MEMBERSHIP, not merely on the element type', () => {
    // The shape-3 tests above MIRROR the logic, so they pass either way -- which
    // is exactly the hazard this describe block exists for, and it caught me:
    // reverting connection.ts to the type-only gate left all of them green.
    // This reads the SOURCE, so the regression reddens here.
    const src = readSource()
    const membership = src.match(/const isGroupMember = memberEls\.includes\(inputEl\)/g) || []
    expect(
      membership.length,
      'restore AND capture must each test membership, not inputEl.type'
    ).toBe(2)
    expect(
      /const isGroupMember = inputEl\.type ===/.test(src),
      'the type-only gate must not come back -- a standalone checkbox whose id ' +
      'collides with a group name IS a group type but not a member'
    ).toBe(false)
  })

  it('BOTH group branches still resolve by the bracketed name', () => {
    // One in restore, one in capture. Requiring exactly two means deleting
    // either -- or adding a third unreviewed site -- fails here.
    const matches = readSource().match(/input\[name="\$\{fieldId\}\[\]"\]/g) || []
    expect(
      matches.length,
      'restore AND capture must each resolve a group by its "[]" name shape'
    ).toBe(2)
  })

  it('restore selects the MATCHING option rather than coercing to a boolean', () => {
    const body = bodyOf(readSource(), 'restoreDOMFromSessionStorage')
    expect(
      /picked\.includes\(el\.value\)/.test(body),
      'a group restore must match on the option value, not Boolean(value)'
    ).toBe(true)
    expect(
      /el\.value === String\(value\)/.test(body),
      'a radio restore must check the matching option, not overwrite option[0].value'
    ).toBe(true)
  })

  it('capture tests the GROUP branch before the single-checkbox branch', () => {
    // Order is the whole fix: reversed, a group falls into `value = inputEl.checked`
    // and stores the boolean `true` again.
    const body = bodyOf(readSource(), 'capturePreFilledValues')
    // Anchor on the BRANCH KEYWORDS, not a bare type test -- the gate that
    // guards the group lookup legitimately mentions inputEl.type === 'checkbox'
    // ABOVE the branches, and a bare indexOf matched that instead, reddening on
    // correct code. A guard that cries wolf gets deleted, so it has to be exact.
    const groupAt = body.indexOf('if (groupEls.length) {')
    const singleAt = body.indexOf("} else if (inputEl.type === 'checkbox') {")
    expect(groupAt, 'the group branch must exist in capture').toBeGreaterThan(-1)
    expect(singleAt, 'the single-checkbox branch must still exist').toBeGreaterThan(-1)
    expect(
      groupAt < singleAt,
      'the group branch must be tested BEFORE the single-checkbox branch'
    ).toBe(true)
  })
})
