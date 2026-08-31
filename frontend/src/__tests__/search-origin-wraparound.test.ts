/**
 * Next-field search resumes from the user's last-acted field and WRAPS
 * (bd polyglot-pdf-a08po).
 *
 * Before this, computeNextField always scanned from index 0, so every manual
 * edit re-targeted the model at the FIRST unconfirmed field while the user was
 * working far below it -- the "the voice agent can't keep up" failure for a
 * mostly-manual user.
 *
 * The search origin is NOT a pin: it only moves where the scan STARTS. The
 * rotation places the origin according to the GESTURE that set it: a manual
 * EDIT answers the field, so the scan resumes after it (and only returns to it
 * last, if it is somehow still unconfirmed); a CLICK points at the field, so it
 * is offered next. Because the scan wraps, fields the user skipped PAST are swept up
 * on the way around -- which is why there is no separate end-of-form
 * "go back for missed fields" phase, and why completion is unchanged (an empty
 * result still means every shown field is confirmed).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { SchemaFormState } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
import { computeNextField, isFormComplete } from '../navigation'

describe('next-field search origin + wrap-around (bd a08po)', () => {
  let sessionStorageMock: { [key: string]: string }

  beforeEach(() => {
    sessionStorageMock = {}
    global.sessionStorage = {
      getItem: vi.fn((key: string) => sessionStorageMock[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStorageMock[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete sessionStorageMock[key]
      }),
      clear: vi.fn(() => {
        sessionStorageMock = {}
      }),
      length: 0,
      key: vi.fn(() => null),
    } as any
  })

  // One section, five fields, continuous mode -- the shipped configuration, so
  // the search spans the whole form rather than stopping at a section edge.
  const schema: FormSchema = {
    source: 'pdf',
    form_metadata: {
      title: 'Test Form', version: '1', language: 'en',
      form_number: 'T-1', edition_date: '01/01/25', page_count: 1,
    },
    sections: [{ id: 'sec1', label: 'One', order: 1, fields: ['a', 'b', 'c', 'd', 'e'] }],
    fields: [
      { id: 'a', name: 'Field A', type: 'text', section_id: 'sec1' },
      { id: 'b', name: 'Field B', type: 'text', section_id: 'sec1' },
      { id: 'c', name: 'Field C', type: 'text', section_id: 'sec1' },
      { id: 'd', name: 'Field D', type: 'text', section_id: 'sec1' },
      { id: 'e', name: 'Field E', type: 'text', section_id: 'sec1' },
    ],
  } as unknown as FormSchema

  const baseState = (): SchemaFormState => {
    const s = SchemaFormStateManager.init(schema)
    return { ...s, continuousSessionEnabled: true, currentSectionId: 'sec1' }
  }

  const confirmed = (value: string) => ({
    value, confirmed: true, confirmationMethod: 'manual_edit' as const,
  })

  it('with no origin set, the scan still starts at the top (unchanged behavior)', () => {
    const state = baseState()
    expect(state.searchOriginFieldId).toBeNull()
    expect(computeNextField(state)?.id).toBe('a')
  })

  it('resumes AFTER the origin instead of restarting at the top', () => {
    // The user jumped ahead and filled 'd'. 'a' and 'b' are still empty and sit
    // ABOVE it -- the pre-a08po behavior returned 'a' here, yanking the model
    // back to the top of the form.
    let state = baseState()
    state = { ...state, fieldValues: { d: confirmed('filled') } }
    state = SchemaFormStateManager.setSearchOrigin(state, 'd')

    expect(computeNextField(state)?.id).toBe('e')
  })

  it('wraps past the end to sweep up fields the user skipped over', () => {
    // Origin MID-form ('c') with everything AFTER it confirmed and 'a'/'b' --
    // which sit BEFORE the origin -- still open. Reaching them requires the
    // scan to run off the end and come back around.
    //
    // The wrap is only OBSERVABLE when a field before the origin AND a field
    // after it are both open: the rotation must serve the LATER one first and
    // only come back to the earlier one afterwards. (Arrangements where every
    // field after the origin is confirmed cannot distinguish a rotation from
    // plain schema order -- both return the earliest open field -- and they
    // survive a rotation-removed mutant.)
    let state = baseState()
    state = {
      ...state,
      // Origin 'b'. 'a' is open BEFORE it; 'd' is open AFTER it.
      fieldValues: { b: confirmed('x'), c: confirmed('x'), e: confirmed('x') },
    }
    state = SchemaFormStateManager.setSearchOrigin(state, 'b')

    // Rotation order is c,d,e,a -- so 'd' comes first, NOT 'a'.
    expect(computeNextField(state)?.id).toBe('d')

    // ...and once 'd' is answered, the scan wraps around to pick up 'a'.
    const afterD = {
      ...state,
      fieldValues: { ...state.fieldValues, d: confirmed('x') },
    }
    expect(computeNextField(afterD)?.id).toBe('a')
  })

  it('after an EDIT, visits the origin field LAST, not first', () => {
    // 'c' was ANSWERED (no includesSelf), and is itself still unconfirmed. The
    // next thing to offer is what comes after it; 'c' is only returned once
    // nothing else qualifies. (The CLICK case is the opposite -- see below.)
    let state = baseState()
    state = {
      ...state,
      fieldValues: {
        a: confirmed('x'), b: confirmed('x'), d: confirmed('x'), e: confirmed('x'),
      },
    }
    state = SchemaFormStateManager.setSearchOrigin(state, 'c')

    // Everything except 'c' is confirmed, so the rotation comes back to it.
    expect(computeNextField(state)?.id).toBe('c')

    // But with a later field open, that one wins -- 'c' is not re-offered first.
    const withOpenTail = {
      ...state,
      fieldValues: { a: confirmed('x'), b: confirmed('x'), d: confirmed('x') },
    }
    expect(computeNextField(withOpenTail)?.id).toBe('e')
  })

  it('a filled-but-unconfirmed field still outranks an empty one (priority order survives the rotation)', () => {
    // PRIORITY 1 (filled, unconfirmed) must still beat PRIORITY 2 (empty) --
    // the rotation changes WHERE the scan starts, not the priority rules. 'e'
    // is filled-unconfirmed and sits after the origin; 'b' is merely empty.
    let state = baseState()
    state = {
      ...state,
      fieldValues: {
        c: confirmed('x'),
        e: { value: 'typed but not confirmed', confirmed: false },
      },
    }
    state = SchemaFormStateManager.setSearchOrigin(state, 'c')

    expect(computeNextField(state)?.id).toBe('e')
  })

  it('a stale origin (field no longer in the schema) falls back to the top', () => {
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'ghost-field')

    expect(computeNextField(state)?.id).toBe('a')
  })

  it('completion is unchanged: the wrap does not let an unconfirmed field pass', () => {
    // 'a' (before the origin) and 'd' (after it) are both open, so the rotation
    // is observable here too: 'd' is served first, then the scan wraps to 'a'.
    // Neither may be lost -- an unanswered field must never look finished.
    let state = baseState()
    state = {
      ...state,
      fieldValues: { b: confirmed('x'), c: confirmed('x'), e: confirmed('x') },
    }
    state = SchemaFormStateManager.setSearchOrigin(state, 'b')

    expect(isFormComplete(state)).toBe(false)
    expect(computeNextField(state)?.id).toBe('d')

    const afterD = {
      ...state,
      fieldValues: { ...state.fieldValues, d: confirmed('x') },
    }
    expect(isFormComplete(afterD)).toBe(false)
    expect(computeNextField(afterD)?.id).toBe('a')

    // Once everything is confirmed, the search is empty and the form is done,
    // regardless of where the origin sits.
    const all = {
      ...state,
      fieldValues: {
        a: confirmed('x'), b: confirmed('x'), c: confirmed('x'),
        d: confirmed('x'), e: confirmed('x'),
      },
    }
    expect(computeNextField(all)).toBeNull()
    expect(isFormComplete(all)).toBe(true)
  })

  // --- the two gestures are opposite intents on the same field ------------
  // (fresh-eyes gap: a CLICK points AT a field, a manual EDIT answers it and
  // moves on. Treating both as "resume after" sent the model to the clicked
  // field's NEIGHBOUR -- the wrong-field failure this bead exists to fix.)

  it('a CLICK makes that field itself the next field (includesSelf)', () => {
    // Every field empty. Clicking 'c' must offer 'c', not 'd'.
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'c', { includesSelf: true })

    expect(computeNextField(state)?.id).toBe('c')
  })

  it('a click on an already-CONFIRMED field still moves on (no dead end)', () => {
    // includesSelf must not resurrect a finished field: 'c' is confirmed, so the
    // rotation starts at it, skips it, and offers the next open one.
    let state = baseState()
    state = { ...state, fieldValues: { c: confirmed('x') } }
    state = SchemaFormStateManager.setSearchOrigin(state, 'c', { includesSelf: true })

    expect(computeNextField(state)?.id).toBe('d')
  })

  it('an EDIT resumes AFTER the field (default: not includesSelf)', () => {
    // The complement of the click case, on the same field, from the same state.
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'c')

    expect(computeNextField(state)?.id).toBe('d')
  })

  it('re-setting the same field with the OTHER intent persists (click, then type)', () => {
    // The early-return guard must compare BOTH halves: clicking a field then
    // typing in it is a real sequence, and the second call changes the meaning.
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'c', { includesSelf: true })
    expect(computeNextField(state)?.id).toBe('c')

    state = SchemaFormStateManager.setSearchOrigin(state, 'c')
    expect(state.searchOriginIncludesSelf).toBe(false)
    expect(computeNextField(state)?.id).toBe('d')
  })

  it('confirming a field advances the origin, so a voice jump does not snap backward', () => {
    // fresh-eyes gap 2: switch_to_field pins 'd'; answering it releases the pin.
    // Without advancing the origin the scan fell back to a STALE origin ('a'
    // here) instead of continuing from the field just answered.
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'a')
    state = SchemaFormStateManager.pinField(state, 'd')
    state = SchemaFormStateManager.updateField(state, 'd', 'answer')
    state = SchemaFormStateManager.confirmField(state, 'd', 'ai_voice')

    expect(state.pinnedFieldId).toBeNull()
    expect(state.searchOriginFieldId).toBe('d')
    expect(computeNextField(state)?.id).toBe('e')
  })

  it('skipping a field advances the origin the same way a confirm does', () => {
    // The pin-releasing pair must stay in step -- an origin left stale by only
    // one of them would strand the scan where the other path fixed it.
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'a')
    state = SchemaFormStateManager.pinField(state, 'd')
    state = SchemaFormStateManager.markFieldSkipped(state, 'd', 'manual_edit')

    expect(state.pinnedFieldId).toBeNull()
    expect(state.searchOriginFieldId).toBe('d')
    expect(computeNextField(state)?.id).toBe('e')
  })

  it('the live pin still outranks the search origin', () => {
    // switch_to_field (a verbal redirect) is the most recent explicit signal in
    // this scenario, so it must win over an older origin.
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'd')
    state = SchemaFormStateManager.pinField(state, 'b')

    expect(computeNextField(state)?.id).toBe('b')
  })

  it('setSearchOrigin persists and survives a reload', () => {
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'c')

    const reloaded = SchemaFormStateManager.load()
    expect(reloaded?.searchOriginFieldId).toBe('c')
  })

  it('a session persisted before this field existed loads with a null origin', () => {
    // Migration: no origin means "start at the top", i.e. the old behavior.
    // Build the stored blob the way save() does (Sets -> arrays), then strip the
    // key, so this exercises the real pre-a08po on-disk shape rather than a
    // JSON.stringify of a live state object (whose Sets serialize as {}).
    let state = baseState()
    state = SchemaFormStateManager.setSearchOrigin(state, 'c')
    const stored = JSON.parse(sessionStorageMock['schema_form_state'])
    expect(stored.searchOriginFieldId).toBe('c') // the writer really persists it
    delete stored.searchOriginFieldId
    sessionStorageMock['schema_form_state'] = JSON.stringify(stored)

    const loaded = SchemaFormStateManager.load()
    expect(loaded?.searchOriginFieldId).toBeNull()
    // And a migrated session behaves like the old code: scan from the top.
    expect(computeNextField(loaded as SchemaFormState)?.id).toBe('a')
  })
})
