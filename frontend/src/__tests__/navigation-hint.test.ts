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
