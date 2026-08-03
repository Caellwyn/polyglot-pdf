/**
 * formatNextFieldHint -- the per-turn steering channel to the voice AI.
 *
 * bd polyglot-pdf-bo4m: a field's fine print (help.instructions) must ride the
 * next-field hint, because the hint (initiating message / confirm_field
 * response / manual-update hint) is what the model acts on per turn -- a
 * "Note:" line buried in the SI's bulk field dump was not salient enough for
 * the model to convey the qualifying context when asking.
 */

import { describe, it, expect } from 'vitest'
import { formatNextFieldHint } from '../navigation'
import type { FormField } from '../schema-forms/types/schema'

const baseField = (overrides: Partial<FormField> = {}): FormField => ({
  id: 'p1_checkbox4',
  name: 'Has Your Name Legally Changed?',
  spoken_name: 'has your name legally changed',
  type: 'radio',
  section_id: 'section-1',
  ...overrides
} as FormField)

describe('formatNextFieldHint', () => {
  it('appends help.instructions as context to convey when present', () => {
    const field = baseField({
      help: {
        instructions: 'Indicate if your name has legally changed since your ' +
          'Permanent Resident Card was issued.'
      }
    })

    const hint = formatNextFieldHint(field, 4)

    expect(hint).toContain("'Has Your Name Legally Changed?'")
    expect(hint).toContain("field_id: 'p1_checkbox4'")
    expect(hint).toContain('Context to briefly convey when asking: ' +
      'Indicate if your name has legally changed since your ' +
      'Permanent Resident Card was issued.')
  })

  it('emits no context suffix when the field has no help.instructions', () => {
    const hint = formatNextFieldHint(baseField(), 4)

    expect(hint).toBe(
      "Next field to fill is #4: 'Has Your Name Legally Changed?' " +
      "(field_id: 'p1_checkbox4', type: radio)"
    )
  })

  it('emits no context suffix when help exists but instructions is absent', () => {
    const field = baseField({ help: { format_hint: 'Yes / No' } })

    const hint = formatNextFieldHint(field, 1)

    expect(hint).not.toContain('Context to briefly convey')
  })

  it('NEVER carries help.details -- the hint stays short (bd wsao.1)', () => {
    // The spoken ask-hint carries only the short instructions; the verbatim
    // official-booklet excerpts (help.details) reach the model via the
    // guidance block + secretary catalog, never the spoken channel. A details
    // leak here would have the model "briefly convey" pages of IRS prose.
    const field = baseField({
      help: {
        instructions: 'Check the one box that best explains your reason.',
        details: 'a. Nonresident alien required to get an ITIN to claim a ' +
          'tax treaty benefit. If you check this box you must also check box h.'
      }
    })

    const hint = formatNextFieldHint(field, 2)

    expect(hint).toContain('Context to briefly convey when asking: ' +
      'Check the one box that best explains your reason.')
    expect(hint).not.toContain('tax treaty benefit')
    expect(hint).not.toContain('box h')
  })

  it('keeps options and required-ness alongside the context suffix', () => {
    const field = baseField({
      validation: { required: true },
      options: [
        { value: 'yes', label: 'Yes' },
        { value: 'no', label: 'No' },
        { value: 'na', label: 'N/A' }
      ],
      help: { instructions: 'Changed since your green card was issued?' }
    })

    const hint = formatNextFieldHint(field, 4)

    expect(hint).toContain(', required')
    expect(hint).toContain('options: [Yes, No, N/A]')
    // Context rides AFTER the parenthetical so the structural hint stays parseable.
    expect(hint).toMatch(/\)\. Context to briefly convey when asking: /)
  })
})

describe('formatNextFieldHint option-label translation (bd polyglot-pdf-0rm1)', () => {
  const optionsField = () => baseField({
    options: [
      { value: 'yes', label: 'Yes', label_translations: { spanish: 'Si', ukrainian: 'Tak' } },
      { value: 'no', label: 'No', label_translations: { spanish: 'No' } },
    ]
  } as Partial<FormField>)

  it('resolves option labels through label_translations for the session language', () => {
    const hint = formatNextFieldHint(optionsField(), 2, 'Spanish')
    expect(hint).toContain('options: [Si, No]')
  })

  it('falls back to the English label on a per-option translation miss', () => {
    // 'no' has no ukrainian entry -- only that option falls back.
    const hint = formatNextFieldHint(optionsField(), 2, 'Ukrainian')
    expect(hint).toContain('options: [Tak, No]')
  })

  it('renders English labels for English, absent, and unknown languages', () => {
    for (const lang of ['English', undefined, null, 'Klingon']) {
      const hint = formatNextFieldHint(optionsField(), 2, lang as string | null | undefined)
      expect(hint).toContain('options: [Yes, No]')
    }
  })

  it('leaves the quoted field name and field_id in English regardless of language', () => {
    // The backend's hint translation substitutes the NAME (bd tupu.2); the
    // frontend must not pre-translate it, or the backend's quoted-name match
    // would miss.
    const hint = formatNextFieldHint(optionsField(), 2, 'Spanish')
    expect(hint).toContain("'Has Your Name Legally Changed?'")
    expect(hint).toContain("field_id: 'p1_checkbox4'")
  })
})
