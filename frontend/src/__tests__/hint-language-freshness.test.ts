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
  // read-through accessor -- BOTH fix the primary hint path, so removing
  // either one alone leaves the end-to-end test green (verified by mutation:
  // only removing both turns it red). Redundancy is fine in the product and
  // fatal in the pins, so each is asserted on its own here. Without these, a
  // later refactor could drop one mechanism silently -- and the surviving one
  // does NOT cover the other's callers.

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
