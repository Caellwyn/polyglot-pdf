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

describe('formatNextFieldHint resolver mirrors the backend (bd polyglot-pdf-thun)', () => {
  // The hint and the backend-rendered guidance block reach the model on the
  // SAME turn, so any key form the backend resolves and this does not shows up
  // as the two-languages-at-once condition bd 0rm1 set out to fix. The backend
  // (option_translation.py _kit_translation_keys / _kit_translation) accepts
  // the lowercase NAME, the BCP-47 code, and its stem, lowercases the dict's
  // own keys, and treats a blank value as a miss.

  const fieldKeyedBy = (key: string) => baseField({
    options: [{ value: 'yes', label: 'Yes', label_translations: { [key]: 'Si' } }]
  } as Partial<FormField>)

  it.each([
    ['canonical lowercase name', 'spanish'],
    ['full BCP-47 code', 'es-US'],
    ['BCP-47 stem', 'es'],
    ['capitalized name', 'Spanish'],
    ['uppercase code', 'ES-US'],
  ])('resolves a label keyed by %s', (_label, key) => {
    const hint = formatNextFieldHint(fieldKeyedBy(key), 2, 'Spanish')
    expect(hint).toContain('options: [Si]')
  })

  it('does NOT resolve an ISO-639-1 code that differs from the BCP-47 stem', () => {
    // Backend parity, stated explicitly so the tolerance cannot drift wider
    // than the backend's: Chinese bakes under "chinese"/"cmn-CN"/"cmn", so a
    // kit keyed "zh" falls back to English on BOTH sides -- consistent, which
    // is the property that matters, rather than silently divergent.
    const field = baseField({
      options: [{ value: 'y', label: 'Yes', label_translations: { zh: 'Shi' } }]
    } as Partial<FormField>)
    expect(formatNextFieldHint(field, 2, 'Chinese')).toContain('options: [Yes]')
  })

  it.each([
    ['empty string', ''],
    ['a single space', ' '],
    ['tabs and newlines', '\t\n  '],
  ])('treats a %s translation as a miss and falls back to English', (_label, value) => {
    // A whitespace-only value would otherwise render as a BLANK inside the
    // spoken options list -- worse than the English label, because the model
    // reads an option with no text at all.
    const field = baseField({
      options: [{ value: 'yes', label: 'Yes', label_translations: { spanish: value } }]
    } as Partial<FormField>)
    const hint = formatNextFieldHint(field, 2, 'Spanish')
    expect(hint).toContain('options: [Yes]')
  })

  it('keeps the hint English for a kit with no label_translations at all', () => {
    // bd polyglot-pdf-thun criterion 2, recorded as behavior: the backend's
    // rung-2 secretary overrides are built server-side and never sent to the
    // client, so an UNBAKED kit's hint stays English by design. The resolver
    // comment states this; the test pins that it degrades to English rather
    // than to a blank or 'undefined'.
    const field = baseField({
      options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }]
    } as Partial<FormField>)
    const hint = formatNextFieldHint(field, 2, 'Spanish')
    expect(hint).toContain('options: [Yes, No]')
    expect(hint).not.toContain('undefined')
  })
})

describe('formatNextFieldHint option shapes (bd polyglot-pdf-5419)', () => {
  it('renders a legacy bare-string option array as the strings themselves', () => {
    // `options: ["A", "B"]` is a supported shape (schema_lint checks it,
    // manifest_service._sanitize_options passes it through, validation.ts
    // optionValue() handles it). Mapping it through `o.label` handed the voice
    // model a literal 'undefined' as the option text.
    const field = baseField({ options: ['A', 'B'] as any })
    const hint = formatNextFieldHint(field, 2)
    expect(hint).toContain('options: [A, B]')
    expect(hint).not.toContain('undefined')
  })

  it('falls back to the value when a dict option has no label', () => {
    const field = baseField({
      options: [{ value: 'yes' }, { value: 'no', label: '' }] as any
    })
    const hint = formatNextFieldHint(field, 2)
    expect(hint).toContain('options: [yes, no]')
    expect(hint).not.toContain('undefined')
  })

  it('never emits undefined for bare strings in a translated session', () => {
    // The bare-string path has no label_translations to consult; it must not
    // fall through the translation branch into an undefined read.
    const field = baseField({ options: ['A', 'B'] as any })
    const hint = formatNextFieldHint(field, 2, 'Spanish')
    expect(hint).toContain('options: [A, B]')
    expect(hint).not.toContain('undefined')
  })
})
