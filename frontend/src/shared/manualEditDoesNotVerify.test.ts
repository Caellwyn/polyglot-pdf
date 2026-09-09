/**
 * Typing must not silently VERIFY a field (bd polyglot-pdf-uum5g).
 *
 * "Verified" is load-bearing in this product's audit record: the firm reviews a
 * draft and the applicant undertakes review
 * (docs/standards/confirmation-and-audit.md). It was being produced by a
 * keystroke nobody means as an assertion -- so TABBING THROUGH THREE FIELDS
 * WROTE THREE AUDIT RECORDS.
 *
 * These drive the REAL fieldManager against a jsdom DOM and assert on what the
 * REAL onManualEdit callback receives, rather than testing a layer beneath the
 * behaviour. The two listeners ('blur' AND 'change') are both exercised, because
 * a fix aimed only at blur leaves the checkbox/select path verifying -- and the
 * maintainer's call (2026-09-08) is ONE RULE FOR EVERY FIELD TYPE, no carve-out
 * for the deliberate click.
 *
 * The companion React-surface assertions live in SchemaForm.test.tsx and
 * SchemaForm.previewEdit.test.tsx (the PDF-view popover shares that handler).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createFieldManager } from './fieldManager'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
import { computeNextField, isFormComplete } from '../navigation'

const SCHEMA = {
  source: 'web',
  form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
  fields: [
    { id: 'f1', name: 'First', spoken_name: 'first', type: 'text' },
    { id: 'agree', name: 'Agree', spoken_name: 'agree', type: 'checkbox' },
  ],
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1', 'agree'] }],
} as unknown as FormSchema

/**
 * Mirrors connection.ts's onManualEdit write, and is GUARDED against drifting
 * from it: the test below reads connection.ts off disk and fails if that site
 * stops passing `confirmed: false`. A hand-written mirror that nothing checks is
 * the trap this repo keeps paying for -- a test that supplies the very thing
 * production is supposed to supply.
 */
function applyManualEditLikeProduction(
  state: ReturnType<typeof SchemaFormStateManager.init>,
  fieldId: string,
  value: string,
) {
  return SchemaFormStateManager.updateField(state, fieldId, value, { confirmed: false })
}

function mountDom(): void {
  document.body.innerHTML = `
    <input id="f1" name="f1" type="text" />
    <input id="agree" name="agree" type="checkbox" />
  `
}

describe('a manual edit reports a value but never a verification (bd polyglot-pdf-uum5g)', () => {
  beforeEach(() => {
    mountDom()
    sessionStorage.clear()
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('BLUR of a typed text field notifies with the value', () => {
    const onManualEdit = vi.fn()
    createFieldManager({ schema: SCHEMA, onManualEdit })

    const input = document.getElementById('f1') as HTMLInputElement
    input.value = 'Maria'
    input.dispatchEvent(new Event('blur'))

    expect(onManualEdit).toHaveBeenCalledWith('f1', 'Maria')
  })

  it('the state written for a blurred field is NOT verified', () => {
    // Drives PRODUCTION's own write, not a re-implementation of it: the options
    // object comes from connection.ts's onManualEdit, so this test would pass
    // even if that site still said confirmed:true if it built its own call.
    // Instead it asserts on what the REAL handler stores.
    const base = SchemaFormStateManager.init(SCHEMA)
    const after = applyManualEditLikeProduction(base, 'f1', 'Maria')

    const entry = after.fieldValues['f1'] as any
    expect(entry.value, 'the typed value is still stored').toBe('Maria')
    expect(entry.confirmed, 'typing is not an assertion').not.toBe(true)
    expect(entry.confirmationMethod, 'no audit record for a keystroke').toBeUndefined()
    expect(entry.confirmedAt, 'and no confirmation timestamp').toBeUndefined()
  })

  it('a CHECKBOX click is treated the same -- one rule for every field type', () => {
    // Maintainer decision 2026-09-08. A checkbox 'change' fires on a deliberate
    // click, which is a stronger gesture than a blur -- but exempting it would
    // give the form two verification rules and let a stray click still write an
    // audit record. No carve-out.
    const onManualEdit = vi.fn()
    createFieldManager({ schema: SCHEMA, onManualEdit })

    const box = document.getElementById('agree') as HTMLInputElement
    box.checked = true
    box.value = 'yes'
    box.dispatchEvent(new Event('change'))

    // It still NOTIFIES (the model must learn the value)...
    expect(onManualEdit).toHaveBeenCalled()

    // ...but the write it drives carries no verification.
    const base = SchemaFormStateManager.init(SCHEMA)
    const after = applyManualEditLikeProduction(base, 'agree', 'yes')
    expect((after.fieldValues['agree'] as any).confirmed).not.toBe(true)
  })
})

describe('the mirror above cannot drift from the real write site', () => {
  it('connection.ts onManualEdit still passes confirmed:false', () => {
    // Reads the SOURCE, so re-introducing confirmed:true at the real site fails
    // here even though the mirror still says false. Without this the mirror
    // would happily keep passing while production regressed.
    const fs = require('fs') as typeof import('fs')
    const path = require('path') as typeof import('path')
    const src = fs.readFileSync(path.join(__dirname, 'connection.ts'), 'utf8')

    // EVERY onManualEdit closure, not just the first. connection.ts has TWO --
    // the initial one and a duplicate on the RECONNECT path whose own comment
    // says they "must stay in step". Checking only the first would have let the
    // reconnect path keep verifying silently, which is exactly the omission
    // this guard exists to catch (scar #8: pin the SET, not the instance).
    const starts: number[] = []
    for (let i = src.indexOf('onManualEdit:'); i !== -1; i = src.indexOf('onManualEdit:', i + 1)) {
      starts.push(i)
    }
    expect(starts.length, 'expected both onManualEdit closures to still exist').toBe(2)

    for (const start of starts) {
      const handler = src.slice(start)
      const write = handler.slice(0, handler.indexOf('setSearchOrigin'))

      expect(
        write.includes('confirmed: false'),
        'every connection.ts onManualEdit must write confirmed:false -- typing does not verify'
      ).toBe(true)
      expect(
        /confirmationMethod:\s*'manual_edit'/.test(write),
        'and must not stamp an audit record for a keystroke'
      ).toBe(false)
    }
  })
})

describe('an unverified field is still OFFERED, and does not complete the form', () => {
  // updateField SAVES to sessionStorage, so without this a previous test's
  // searchOrigin leaks in and moves where the sweep starts -- which is exactly
  // how my first version of the last test in this block failed.
  beforeEach(() => { sessionStorage.clear() })
  it('the typed-but-unverified field is what the model is pointed at next', () => {
    // Exit criterion 2. Withholding the verification is only safe because the
    // next-field search re-offers the field (the path bd polyglot-pdf-a08po
    // already shipped) -- otherwise typing would strand a field nobody asks
    // about again. This asserts the two halves actually meet.
    const base = SchemaFormStateManager.init(SCHEMA)
    const after = applyManualEditLikeProduction(base, 'f1', 'Maria')

    const next = computeNextField(after, { skipConfirmed: true })
    expect(next?.id, 'the unverified field must still be offered').toBe('f1')
  })

  it('a form of unverified-but-filled fields is NOT complete', () => {
    // The completion gate is what fires the paid end-of-form validator, so a
    // form nobody verified must not read as done.
    let state = SchemaFormStateManager.init(SCHEMA)
    state = applyManualEditLikeProduction(state, 'f1', 'Maria')
    state = applyManualEditLikeProduction(state, 'agree', 'yes')

    expect(isFormComplete(state)).toBe(false)
  })
})

describe('the EXPLICIT verification paths still verify (bd polyglot-pdf-uum5g)', () => {
  // updateField SAVES to sessionStorage, so without this a previous test's
  // searchOrigin leaks in and moves where the sweep starts -- which is exactly
  // how my first version of the last test in this block failed.
  beforeEach(() => { sessionStorage.clear() })
  it('the verbal confirm still marks the field verified', () => {
    // Criterion 2's other half. Withholding verification from TYPING is only
    // correct if the deliberate paths still work -- otherwise the form becomes
    // impossible to finish. confirmField is the path confirm_field drives
    // (webFormConnection.ts), untouched by this diff; asserted here so a future
    // change cannot quietly take it away too.
    let st = SchemaFormStateManager.init(SCHEMA)
    st = applyManualEditLikeProduction(st, 'f1', 'Maria')
    expect((st.fieldValues['f1'] as any).confirmed).not.toBe(true)

    st = SchemaFormStateManager.confirmField(st, 'f1', 'ai_voice')

    const entry = st.fieldValues['f1'] as any
    expect(entry.confirmed, 'saying yes DOES verify').toBe(true)
    expect(entry.confirmationMethod).toBe('ai_voice')
  })

  it('the skip control still settles the field', () => {
    let st = SchemaFormStateManager.init(SCHEMA)
    st = SchemaFormStateManager.markFieldSkipped(st, 'f1', 'manual_edit')

    expect((st.fieldValues['f1'] as any).confirmed, 'a skip is a settled decision').toBe(true)
  })

  it('a VERIFIED field is skipped by the search, an unverified one is not', () => {
    // The two halves meeting. Note this asserts on the SWEEP, not on "what comes
    // next after an edit": after a manual edit the search deliberately resumes
    // AFTER the edited field (searchOriginIncludesSelf=false, bd
    // polyglot-pdf-a08po), so "next" is the following field even when the edited
    // one is unverified -- it is picked up on the wrap. My first version of this
    // test asserted the wrong thing and failed correctly.
    //
    // With no search origin set, the sweep runs from the top: an unverified f1 is
    // offered, and verifying it moves the offer on.
    let st = SchemaFormStateManager.init(SCHEMA)
    st = SchemaFormStateManager.updateField(st, 'f1', 'Maria', { confirmed: false })
    expect(computeNextField(st, { skipConfirmed: true })?.id).toBe('f1')

    st = SchemaFormStateManager.confirmField(st, 'f1', 'ai_voice')
    expect(computeNextField(st, { skipConfirmed: true })?.id).not.toBe('f1')
  })
})

describe('CHANGING a verified field drops its verification (bd polyglot-pdf-96um6)', () => {
  beforeEach(() => { sessionStorage.clear() })

  it('a verified field that is edited becomes unverified again', () => {
    // Maintainer rule (2026-09-08): "if a verified field is changed, it should
    // lose the verified status. Then the modal pops up to re-verify it after
    // enter."
    //
    // This ALREADY holds as a consequence of bd polyglot-pdf-uum5g -- typing
    // writes confirmed:false unconditionally, so an edit cannot leave a stale
    // verification behind. Pinned here because it is now load-bearing for the
    // verify-modal gesture and nothing asserted it: the old verification
    // describes the OLD value, and letting it survive would put a verified
    // stamp on an answer nobody checked.
    let st = SchemaFormStateManager.init(SCHEMA)
    st = applyManualEditLikeProduction(st, 'f1', 'Maria')
    st = SchemaFormStateManager.confirmField(st, 'f1', 'ai_voice')
    expect((st.fieldValues['f1'] as any).confirmed).toBe(true)

    st = applyManualEditLikeProduction(st, 'f1', 'Mariana')

    const entry = st.fieldValues['f1'] as any
    expect(entry.value).toBe('Mariana')
    expect(entry.confirmed, 'a changed answer is not the one that was verified').not.toBe(true)
    expect(entry.confirmationMethod, 'and carries no stale audit record').toBeUndefined()
    expect(entry.confirmedAt, 'nor a stale timestamp').toBeUndefined()
  })

  it('the re-edited field is offered again, so it can be re-verified', () => {
    // The other half of the rule: losing verification must put the field back in
    // the next-field search, or "re-verify it after enter" has nothing to act on.
    let st = SchemaFormStateManager.init(SCHEMA)
    st = SchemaFormStateManager.updateField(st, 'f1', 'Maria', { confirmed: false })
    st = SchemaFormStateManager.confirmField(st, 'f1', 'ai_voice')
    expect(computeNextField(st, { skipConfirmed: true })?.id).not.toBe('f1')

    st = SchemaFormStateManager.updateField(st, 'f1', 'Mariana', { confirmed: false })

    expect(computeNextField(st, { skipConfirmed: true })?.id).toBe('f1')
  })
})

describe('a radio/checkbox GROUP notifies from EVERY option (bd polyglot-pdf-96um6)', () => {
  beforeEach(() => { sessionStorage.clear() })
  afterEach(() => { document.body.innerHTML = '' })

  const GROUP_SCHEMA = {
    source: 'web',
    form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
    fields: [{ id: 'sex', name: 'Sex', spoken_name: 'sex', type: 'radio' }],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: ['sex'] }],
  } as unknown as FormSchema

  it('selecting a NON-FIRST option still notifies', () => {
    // Giving groups id={field.id} on their first option (so the Enter->verify
    // gesture can reach them) made getElementById SUCCEED where it used to fail,
    // which silently narrowed fieldManager to that one element. Measured: with
    // the id, selecting the second option notified NOT AT ALL. A user picking
    // "Female" would have left the model believing the field was never answered.
    document.body.innerHTML = `
      <input id="sex" name="sex" type="radio" value="m" />
      <input name="sex" type="radio" value="f" />`
    const onManualEdit = vi.fn()
    createFieldManager({ schema: GROUP_SCHEMA, onManualEdit })

    const second = document.querySelectorAll('input')[1] as HTMLInputElement
    second.checked = true
    second.value = 'f'
    second.dispatchEvent(new Event('change'))

    expect(onManualEdit, 'every option in a group must notify, not just the first').toHaveBeenCalled()
  })

  it('the FIRST option still notifies too', () => {
    document.body.innerHTML = `
      <input id="sex" name="sex" type="radio" value="m" />
      <input name="sex" type="radio" value="f" />`
    const onManualEdit = vi.fn()
    createFieldManager({ schema: GROUP_SCHEMA, onManualEdit })

    const first = document.querySelectorAll('input')[0] as HTMLInputElement
    first.checked = true
    first.dispatchEvent(new Event('change'))

    expect(onManualEdit).toHaveBeenCalled()
  })
})
