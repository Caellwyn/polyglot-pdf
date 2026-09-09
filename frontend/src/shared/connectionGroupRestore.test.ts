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
