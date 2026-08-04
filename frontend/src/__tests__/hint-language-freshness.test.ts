/**
 * State written OUTSIDE WebFormConnection must reach the next-field hint, and
 * must not be clobbered by a handler that saves a stale copy
 * (bd polyglot-pdf-pjws).
 *
 * READ THIS FIRST, because it is not what the bead title says. The spoken
 * language is PINNED for the whole form -- it is set once before the form starts
 * and held for every turn, and the only way to change it is a NEW session
 * ("clear form" -> language modal). Mid-conversation switching is NOT a
 * supported flow (bd polyglot-pdf-87a9, docs/standards/voice-and-vad.md), and
 * the UI paths that once did it have been removed. pjws was originally written
 * up as a mid-session-switch bug; that framing was wrong.
 *
 * What IS real, and what these tests pin: every SchemaFormStateManager mutator
 * builds a NEW state object and save()s it, never touching this object's
 * in-memory `this.state`. So a handler can (a) READ a stale copy and emit a hint
 * that disagrees with what the form holds, or (b) SAVE a stale copy and revert
 * whatever was written outside it. Both are general stale-state defects with
 * nothing to do with language policy.
 *
 * selectedLanguage remains the most legible probe for that class -- it is a
 * single scalar that is easy to write outside this object and easy to assert on
 * -- so the cases below still drive it, and the assertions still read as a
 * language changing. Treat that as a TEST FIXTURE, not a supported user flow.
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

describe('hint reads through to persisted state (bd polyglot-pdf-pjws)', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('picks up a selectedLanguage persisted outside this object', () => {
    const conn = new WebFormConnection(SCHEMA)

    // Session starts in Spanish, exactly as the disclaimer flow leaves it.
    const started = SchemaFormStateManager.acceptDisclaimer(
      (conn as any).state, 'Spanish'
    )
    ;(conn as any).state = started
    expect(hintFrom(conn)).toContain('options: [Masculino, Femenino]')

    // Persist a DIFFERENT selectedLanguage straight through the state manager,
    // deliberately not touching `conn.state` -- the fixture for "written outside
    // this object" (see the file header: this is not a supported user flow, it is
    // the cheapest scalar to probe the stale-read class with).
    SchemaFormStateManager.setSelectedLanguage(started, 'Ukrainian')
    expect((conn as any).state.selectedLanguage).toBe('Spanish')

    const hint = hintFrom(conn)
    expect(hint).toContain('options: [Cholovik, Zhinka]')
    expect(hint).not.toContain('Masculino')
  })

  it('a later confirm_field does not revert persisted state', () => {
    // handleConfirmFieldRequest ends in save(this.state), so running it on a
    // stale copy PERSISTS that copy over whatever was written outside this
    // object since the last sync -- silently reverting it.
    //
    // ORDER MATTERS, and it is the real order: the model fills the field (which
    // updates the in-memory copy), something outside writes to storage, THEN the
    // confirm lands. If the fill were only persisted and never in memory, the handler
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

    // The outside write: persisted ONLY. Nothing in this flow touches
    // `conn.state`, so the in-memory copy still says Spanish -- the fixture for
    // "written outside this object" (see the file header).
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

  it('a later skip_field does not revert persisted state either', async () => {
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

  it('computeNextFieldHintString reads through to storage too', () => {
    // The second hint producer, reached via the public getNextFieldHint()
    // (session restart / reconnect). It formats off the accessor, so it must
    // read persisted state rather than a stale in-memory copy.
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
