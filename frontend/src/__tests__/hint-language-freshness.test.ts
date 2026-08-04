/**
 * Mid-session spoken-language changes must reach the next-field hint
 * (bd polyglot-pdf-pjws).
 *
 * After bd polyglot-pdf-0rm1 the hint resolves option labels from the session
 * language, so a stale language is no longer harmless: the pre-0rm1 hint fell
 * back to English (merely redundant beside a translated guidance block), but a
 * STALE one asserts confident labels in the language the user just switched
 * AWAY from. The model then holds two different non-English languages for the
 * same options on the same turn.
 *
 * The staleness is structural: changeSpokenLanguage() (shared/connection.ts)
 * persists through SchemaFormStateManager, which builds a NEW state object and
 * save()s it -- it never mutates WebFormConnection's in-memory `this.state`.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { WebFormConnection } from '../webFormConnection'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'

const SCHEMA = {
  form_id: 'test_form',
  title: 'Test Form',
  fields: [
    {
      id: 'p1_sex',
      name: 'Sex',
      spoken_name: 'sex',
      type: 'radio',
      section_id: 'section-1',
      options: [
        {
          value: 'male', label: 'Male',
          label_translations: { spanish: 'Masculino', ukrainian: 'Cholovik' }
        },
        {
          value: 'female', label: 'Female',
          label_translations: { spanish: 'Femenino', ukrainian: 'Zhinka' }
        },
      ],
    },
  ],
  sections: [
    { id: 'section-1', label: 'Section 1', order: 1, fields: ['p1_sex'] },
  ],
} as unknown as FormSchema

/** Drive the private handler and return the hint it puts on the wire. */
function hintFrom(conn: WebFormConnection): string | null {
  const sent: any[] = []
  ;(conn as any).send = (m: any) => sent.push(m)
  ;(conn as any).handleGetNextFieldHintRequest({ request_id: 'r1' })
  const response = sent.find(m => m.type === 'next_field_hint_response')
  expect(response, 'handler sent no next_field_hint_response').toBeDefined()
  return response.hint
}

describe('next-field hint language freshness (bd polyglot-pdf-pjws)', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('uses the NEW language after a mid-session change', () => {
    const conn = new WebFormConnection(SCHEMA)

    // Session starts in Spanish, exactly as the disclaimer flow leaves it.
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Spanish'
    )
    ;(conn as any).state = started
    expect(hintFrom(conn)).toContain('options: [Masculino, Femenino]')

    // The user switches to Ukrainian. This is what changeSpokenLanguage() does:
    // persist through the state manager. It deliberately does NOT touch
    // `conn.state` -- reproducing the real staleness rather than hiding it.
    SchemaFormStateManager.setSelectedLanguage(started, 'Ukrainian')
    expect((conn as any).state.selectedLanguage).toBe('Spanish')

    const hint = hintFrom(conn)
    expect(hint).toContain('options: [Cholovik, Zhinka]')
    expect(hint).not.toContain('Masculino')
  })

  it('a later confirm_field does not revert the persisted language', () => {
    // handleConfirmFieldRequest ends in save(this.state), so running it on a
    // stale copy PERSISTS the old language over the new one -- the switch would
    // survive exactly one turn and then silently undo itself.
    //
    // ORDER MATTERS, and it is the real order: the model fills the field (which
    // updates the in-memory copy), the user switches language, THEN the confirm
    // lands. If the fill were only persisted and never in memory, the handler
    // would bail at the no-usable-value loop-breaker before reaching its save()
    // -- the clobber would not fire and this test would pass vacuously
    // (verified by mutation).
    const conn = new WebFormConnection(SCHEMA)
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Spanish'
    )
    // The fill: in memory AND persisted, exactly as the update path leaves it.
    const filled = SchemaFormStateManager.updateField(started, 'p1_sex', 'male')
    ;(conn as any).state = filled
    SchemaFormStateManager.save(filled)

    // The switch: persisted only -- changeSpokenLanguage never touches
    // `conn.state`, so the in-memory copy still says Spanish.
    SchemaFormStateManager.setSelectedLanguage(filled, 'Ukrainian')
    expect((conn as any).state.selectedLanguage).toBe('Spanish')

    ;(conn as any).send = () => {}
    ;(conn as any).handleConfirmFieldRequest({
      field_id: 'p1_sex', confirmation_method: 'verbal', request_id: 'c1',
    })

    // The confirm must have taken (proving the handler ran past the
    // loop-breaker and DID reach its save) without reverting the language.
    const after = SchemaFormStateManager.load()
    expect(after?.fieldValues.p1_sex?.confirmed).toBe(true)
    expect(after?.selectedLanguage).toBe('Ukrainian')
  })

  it('a later skip_field does not revert the persisted language either', async () => {
    // The SIBLING of the confirm case above, and the same defect:
    // handleSkipFieldRequest also ends in save(this.state), so on a stale copy
    // it persists the old language over the new one. A skip is as routine a
    // per-turn tool call as a confirm -- the pjws fix originally covered only
    // the confirm path, and both final Opus outer reviews found this
    // independently.
    //
    // The field is left EMPTY on purpose: the handler's data-loss guard refuses
    // to skip a field that already holds a value.
    const conn = new WebFormConnection(SCHEMA)
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Spanish'
    )
    ;(conn as any).state = started
    SchemaFormStateManager.save(started)

    SchemaFormStateManager.setSelectedLanguage(started, 'Ukrainian')
    expect((conn as any).state.selectedLanguage).toBe('Spanish')

    ;(conn as any).send = () => {}
    await (conn as any).handleSkipFieldRequest({
      field_id: 'p1_sex', request_id: 's1',
    })

    const after = SchemaFormStateManager.load()
    // The skip must have taken (proving the handler ran through to its save)...
    expect(after?.fieldValues['p1_sex']?.skipped).toBe(true)
    // ...without reverting the language.
    expect(after?.selectedLanguage).toBe('Ukrainian')
  })

  it('the confirm/skip refresh MERGES fieldValues rather than replacing them', () => {
    // The refresh must not drop an entry that exists only in memory. Both
    // handlers gate on the field holding a usable value, so a plain replace
    // makes the skip handler's data-loss guard miss a filled field (it then
    // BLANKS a real answer) and makes a legitimate confirm fail as 'no_value'.
    //
    // SCOPE, stated precisely: this pins the merge against a plain REPLACE
    // only. A persisted-wins merge still passes, and that is deliberate --
    // persisted-wins is arguably the better direction and bd polyglot-pdf-uw3w
    // exists to decide it, so asserting in-memory-wins as correct here would
    // prejudge that bead. What IS guaranteed is the property both handlers
    // depend on: the refresh must not DROP an in-memory entry.
    const conn = new WebFormConnection(SCHEMA)
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Spanish'
    )
    // Storage holds the language change but NO field values.
    SchemaFormStateManager.save(started)
    SchemaFormStateManager.setSelectedLanguage(started, 'Ukrainian')

    // In memory only -- as if a writer had not yet synced.
    ;(conn as any).state = {
      ...started,
      fieldValues: { p1_sex: { value: 'male', confirmed: false } },
    }

    ;(conn as any).send = () => {}
    ;(conn as any).handleConfirmFieldRequest({
      field_id: 'p1_sex', confirmation_method: 'verbal', request_id: 'm1',
    })

    const after = SchemaFormStateManager.load()
    // The in-memory value survived the refresh, so the confirm could take...
    expect(after?.fieldValues.p1_sex?.confirmed).toBe(true)
    // ...and the persisted language change still won.
    expect(after?.selectedLanguage).toBe('Ukrainian')
  })

  it('falls back to the in-memory language when nothing is persisted', () => {
    // The accessor must not turn an empty sessionStorage into a null language:
    // that would silently drop translation on the pre-persist opener turn.
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).state = {
      ...(conn as any).state, selectedLanguage: 'Spanish'
    }
    sessionStorage.clear()

    expect((conn as any).sessionLanguage).toBe('Spanish')
  })

  // The two mechanisms above -- the per-handler state refresh and the
  // read-through accessor -- cover DIFFERENT callers, and each is asserted on
  // its own below so a later refactor cannot drop one silently.
  //
  // They were briefly redundant on the primary hint path (when they were first
  // added, removing either alone left the end-to-end test green, and only
  // removing both turned it red). That is no longer so: the hint handler now
  // passes sessionLanguageFor(true), deliberately short-circuiting the
  // accessor's read-through because the handler already refreshed. So removing
  // the handler refresh alone DOES turn this file red today (final Opus outer
  // review caught the stale claim). The separate pins remain the right shape --
  // the accessor is what keeps the OTHER three hint producers fresh, and
  // nothing else covers those.

  it('the accessor itself reads the language through to storage', () => {
    // Pins the accessor independently of any handler: it is what keeps the
    // OTHER three hint producers (computeNextFieldHintString, the switch_field
    // ack, the stall-recovery hint) fresh, and those are not exercised by the
    // handler test above.
    const conn = new WebFormConnection(SCHEMA)
    ;(conn as any).state = {
      ...(conn as any).state, selectedLanguage: 'Spanish'
    }
    SchemaFormStateManager.save({
      ...(conn as any).state, selectedLanguage: 'Ukrainian'
    })

    expect((conn as any).sessionLanguage).toBe('Ukrainian')
    // The in-memory copy is deliberately left stale -- the accessor reads
    // through rather than repairing it, which is what makes it safe for the
    // section-switch callers that hold freshly-mutated unsaved state.
    expect((conn as any).state.selectedLanguage).toBe('Spanish')
  })

  it('computeNextFieldHintString picks up a language change too', () => {
    // The second hint producer, reached via the public getNextFieldHint()
    // (session restart / reconnect). It formats off the accessor, so a
    // reconnect after a language switch must not re-assert the old labels.
    const conn = new WebFormConnection(SCHEMA)
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Spanish'
    )
    ;(conn as any).state = started
    expect(conn.getNextFieldHint()).toContain('options: [Masculino, Femenino]')

    SchemaFormStateManager.setSelectedLanguage(started, 'Ukrainian')

    const hint = conn.getNextFieldHint()
    expect(hint).toContain('options: [Cholovik, Zhinka]')
    expect(hint).not.toContain('Masculino')
  })

  it('the hint handler refreshes state, not just the language', () => {
    // Pins the handler's own refresh independently of the accessor: a field
    // CONFIRMED in another tab/handler since the last sync must not be
    // re-offered as the next field. The accessor alone would not catch this,
    // because it reads the language and nothing else.
    const conn = new WebFormConnection(SCHEMA)
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Spanish'
    )
    ;(conn as any).state = started

    // Persist a fill + confirm that the in-memory copy never sees.
    const filled = SchemaFormStateManager.updateField(started, 'p1_sex', 'male')
    SchemaFormStateManager.save(
      SchemaFormStateManager.confirmField(filled, 'p1_sex', 'ai_voice')
    )
    expect((conn as any).state.fieldValues.p1_sex).toBeUndefined()

    // The only field is confirmed, so the form is complete -> hint is null.
    // Off the stale copy the handler would re-offer 'Sex' forever.
    expect(hintFrom(conn)).toBeNull()
  })
})
