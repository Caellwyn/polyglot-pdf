/**
 * Tests for a_number normalization + validation (bd polyglot-pdf-0zr).
 *
 * Mirrors the backend test (backend/tests/unit/test_field_validation_responses.py
 * TestANumberNormalization) so client and server agree: an Alien Registration
 * Number is accepted with or without its "A" prefix / separators and normalized
 * to the canonical bare-digit form (the PDF comb field stores digits).
 */
import { describe, it, expect } from 'vitest';
import { normalizeFieldValue, validateField, shouldShowField } from './validation';
import type { FormField } from '../types/schema';

const aNumberField: FormField = {
  id: 'p1_line1_aliennumber',
  name: 'Alien Registration Number',
  spoken_name: 'alien registration number',
  type: 'text',
  section_id: 'Part 1 - Information About You',
  validation: {
    pattern: '^\\d{7,9}$',
    format_preset: 'a_number',
    max_length: 9,
  },
};

const plainTextField: FormField = {
  id: 'first_name',
  name: 'First Name',
  spoken_name: 'first name',
  type: 'text',
  section_id: 'Part 1 - Information About You',
  validation: { max_length: 50 },
};

describe('normalizeFieldValue (a_number)', () => {
  it.each([
    ['123456789', '123456789'],   // already canonical
    ['A12345678', '12345678'],    // canonical A-prefix form
    ['a12345678', '12345678'],    // lowercase prefix
    ['A-12345678', '12345678'],   // dashed
    ['A 1234 5678', '12345678'],  // spaced
    ['1234567', '1234567'],       // 7 digits, no prefix
  ])('normalizes %s -> %s', (raw, expected) => {
    expect(normalizeFieldValue(aNumberField, raw)).toBe(expected);
  });

  it('leaves non-a_number fields unchanged', () => {
    expect(normalizeFieldValue(plainTextField, 'A-Name')).toBe('A-Name');
  });

  it('passes non-string values through unchanged', () => {
    expect(normalizeFieldValue(aNumberField, 12345678)).toBe(12345678);
  });
});

describe('validateField (a_number)', () => {
  it.each(['A12345678', 'a12345678', 'A-12345678', '123456789', '1234567'])(
    'accepts %s (normalized then validated)',
    (raw) => {
      expect(validateField(aNumberField, raw)).toBeNull();
    }
  );

  it.each(['A1234', '12345', 'A1234567890'])(
    'rejects wrong digit count: %s',
    (raw) => {
      expect(validateField(aNumberField, raw)).not.toBeNull();
    }
  );

  // A non-empty input that normalizes to "" must be rejected, not treated as an
  // unfilled (valid) optional field. bd 0zr / PR #98 fresh-eyes finding.
  it.each(['A', 'A---', 'ABCDEF', 'A-'])(
    'rejects no-digit input that normalizes to empty: %s',
    (raw) => {
      expect(validateField(aNumberField, raw)).not.toBeNull();
    }
  );

  it('treats a genuinely empty optional value as valid (not a format error)', () => {
    expect(validateField(aNumberField, '')).toBeNull();
  });
});

// uscis_account normalization + validation (bd polyglot-pdf-k2ww): FE mirror of
// the backend TestUSCISAccountNormalization suite (jnjj.40). A USCIS online
// account number is exactly 12 digits, but speech-to-text formats the spoken
// digits with a "$" / commas / spaces; normalization strips PUNCTUATION only
// (letters survive so a wrong value stays invalid) and, unlike a_number, does
// NOT drop a leading letter -- uscis_account has no alphabetic prefix.
const uscisAccountField: FormField = {
  id: 'p1_line2_acctidentifier',
  name: 'USCIS Online Account Number',
  spoken_name: 'uscis online account number',
  type: 'text',
  section_id: 'Part 1 - Information About You',
  validation: {
    pattern: '^[0-9]{12}$',
    format_preset: 'uscis_account',
    min_length: 12,
    max_length: 12,
  },
};

describe('normalizeFieldValue (uscis_account)', () => {
  it.each([
    ['123456789012', '123456789012'],           // already canonical
    ['$1,234,567,890,12', '123456789012'],       // the STT-mangled form (jnjj.40)
    ['1,234,567,890,12', '123456789012'],        // commas only
    ['1 2 3 4 5 6 7 8 9 0 1 2', '123456789012'], // spaced digit-by-digit
  ])('normalizes %s -> %s', (raw, expected) => {
    expect(normalizeFieldValue(uscisAccountField, raw)).toBe(expected);
  });

  it('keeps a leading letter (no a_number-style prefix drop)', () => {
    expect(normalizeFieldValue(uscisAccountField, 'A23456789012')).toBe('A23456789012');
  });
});

describe('validateField (uscis_account)', () => {
  it.each(['123456789012', '$1,234,567,890,12'])(
    'accepts a 12-digit value: %s',
    (raw) => {
      expect(validateField(uscisAccountField, raw)).toBeNull();
    }
  );

  it.each(['1234567890', '1234567890123'])(
    'rejects wrong digit count: %s',
    (raw) => {
      expect(validateField(uscisAccountField, raw)).not.toBeNull();
    }
  );

  it('rejects embedded letters (punctuation is stripped, letters are not)', () => {
    expect(validateField(uscisAccountField, 'A23456789012')).not.toBeNull();
  });
});

// Enum / option-membership validation (bd polyglot-pdf-wpw.3): an option-backed
// field's value must be one of its declared options. Guards an AI-applied value
// where the model invents an option that does not exist in the schema.
describe('validateField (enum / option membership)', () => {
  const selectField: FormField = {
    id: 'marital_status',
    name: 'Marital Status',
    spoken_name: 'marital status',
    type: 'select',
    section_id: 'Part 1',
    options: [
      { value: 'single', label: 'Single' },
      { value: 'married', label: 'Married' },
      { value: 'divorced', label: 'Divorced' },
    ],
  };

  // No `validation` block at all -- the option set IS the constraint. The check
  // must still fire (it runs before the `!field.validation` early return).
  const radioNoValidation: FormField = {
    id: 'has_children',
    name: 'Has Children',
    spoken_name: 'has children',
    type: 'radio',
    section_id: 'Part 1',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'no', label: 'No' },
    ],
  };

  // A required select: empty is a required-error, a bad option is an enum-error.
  const requiredSelect: FormField = {
    ...selectField,
    id: 'marital_status_required',
    validation: { required: true },
  };

  it.each(['single', 'married', 'divorced'])('accepts a valid option: %s', (v) => {
    expect(validateField(selectField, v)).toBeNull();
  });

  it.each(['widowed', 'Single', 'MARRIED', 'unknown'])(
    'rejects a value outside the option set: %s',
    (v) => {
      expect(validateField(selectField, v)).not.toBeNull();
    }
  );

  it('enforces enum even when the field has no validation block', () => {
    expect(validateField(radioNoValidation, 'yes')).toBeNull();
    expect(validateField(radioNoValidation, 'maybe')).not.toBeNull();
  });

  it('treats an empty value on an optional option-field as valid (not an enum error)', () => {
    expect(validateField(selectField, '')).toBeNull();
    expect(validateField(selectField, null)).toBeNull();
  });

  it('reports required (not enum) for an empty required option-field', () => {
    expect(validateField(requiredSelect, '')).toContain('required');
  });

  it('validates array (checkbox-group) values member-by-member', () => {
    // Arrays are valid ONLY for a checkbox GROUP, not a single-choice select.
    const checkboxGroup: FormField = {
      id: 'tags[]',
      name: 'Tags',
      spoken_name: 'tags',
      type: 'checkbox',
      group_kind: 'checkbox',
      section_id: 'Part 1',
      options: [
        { value: 'single', label: 'Single' },
        { value: 'married', label: 'Married' },
      ],
    };
    expect(validateField(checkboxGroup, ['single', 'married'])).toBeNull();
    expect(validateField(checkboxGroup, ['single', 'widowed'])).not.toBeNull();
  });

  it('rejects a NON-empty array for a single-choice select/radio field', () => {
    // A single-choice field cannot take a multi-value array (Codex PR #145 round 3).
    expect(validateField(selectField, ['single'])).not.toBeNull();
    expect(validateField(selectField, ['single', 'married'])).not.toBeNull();
  });

  it('treats an empty array [] on an OPTIONAL single-choice field as empty (not an error)', () => {
    // [] is "no value" -> empty (fresh-eyes PR #145 round 4 unified empty-handling).
    // For an optional field that means valid/unfilled, NOT a vacuous-pass landing:
    // because it is empty, the enum check is skipped and nothing is stored. (A
    // REQUIRED single-choice field with [] is covered by the required check below.)
    expect(validateField(selectField, [])).toBeNull();
    expect(validateField(radioNoValidation, [])).toBeNull();
  });

  it('never echoes the rejected value in the error message (PII-safe)', () => {
    const err = validateField(selectField, 'sensitive-made-up-value');
    expect(err).not.toBeNull();
    expect(err).not.toContain('sensitive-made-up-value');
  });

  it('treats an empty array [] as empty: optional checkbox group passes, required fails', () => {
    // [] = a checkbox group with no selections -> empty (fresh-eyes PR #145 round 4).
    const optionalGroup: FormField = {
      id: 'tags_opt[]',
      name: 'Optional Tags',
      spoken_name: 'optional tags',
      type: 'checkbox',
      group_kind: 'checkbox',
      section_id: 'Part 1',
      options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
    };
    const requiredGroup: FormField = { ...optionalGroup, id: 'tags_req[]', validation: { required: true } };

    expect(validateField(optionalGroup, [])).toBeNull();            // optional -> ok empty
    expect(validateField(requiredGroup, [])).toContain('required'); // required -> required error, NOT vacuous pass
  });

  // Plain-string options (e.g. adult_intake_demo_schema.json: options: ["Agender",...]),
  // the shape the backend List[str] normalizer also emits. Reading only opt.value
  // would build an all-undefined allowed set and reject every valid value (Codex PR #145).
  const stringOptionField: FormField = {
    id: 'gender_identity',
    name: 'Gender Identity',
    spoken_name: 'gender identity',
    type: 'select',
    section_id: 'Part 1',
    options: ['Agender', 'Cisgender Female', 'Cisgender Male'] as any,
  };

  it('accepts a valid value when options are plain strings', () => {
    expect(validateField(stringOptionField, 'Agender')).toBeNull();
    expect(validateField(stringOptionField, 'Cisgender Male')).toBeNull();
  });

  it('rejects an out-of-set value when options are plain strings', () => {
    expect(validateField(stringOptionField, 'Nonexistent')).not.toBeNull();
  });
});

// Top-level constraint fields (max_length / min / max) live directly on the field
// in many generated schemas (e.g. form-kits/i-90) with NO `validation` block. The
// early `!field.validation` return used to skip them, letting an over-length AI
// value land. bd polyglot-pdf-wpw.3 / Codex PR #145.
describe('validateField (top-level constraint fields, no validation block)', () => {
  const topLevelMaxLen: FormField = {
    id: 'p1_line6b_streetnumbername',
    name: 'Street Number and Name',
    spoken_name: 'street number and name',
    type: 'text',
    section_id: 'Part 1',
    max_length: 25,
    // NOTE: deliberately NO `validation` block -- the constraint is top-level only.
  };

  const topLevelNumberRange: FormField = {
    id: 'age',
    name: 'Age',
    spoken_name: 'age',
    type: 'number',
    section_id: 'Part 1',
    min: 0,
    max: 120,
  };

  it('accepts a value within the top-level max_length', () => {
    expect(validateField(topLevelMaxLen, '123 Main Street')).toBeNull();
  });

  it('rejects a value over the top-level max_length', () => {
    expect(validateField(topLevelMaxLen, 'X'.repeat(26))).not.toBeNull();
  });

  it('enforces top-level min/max for number fields', () => {
    expect(validateField(topLevelNumberRange, '45')).toBeNull();
    expect(validateField(topLevelNumberRange, '200')).not.toBeNull();
    expect(validateField(topLevelNumberRange, '-1')).not.toBeNull();
  });

  it('an explicit validation block value wins over the top-level field', () => {
    // validation.max_length (10) is tighter than top-level max_length (25): the
    // validation block must take precedence.
    const both: FormField = { ...topLevelMaxLen, validation: { max_length: 10 } };
    expect(validateField(both, 'X'.repeat(15))).not.toBeNull(); // 15 > 10 -> invalid
    expect(validateField(both, 'X'.repeat(8))).toBeNull();      // 8 <= 10 -> valid
  });

  it('treats a field with no constraints at all as valid', () => {
    const bare: FormField = {
      id: 'free_text',
      name: 'Free Text',
      spoken_name: 'free text',
      type: 'text',
      section_id: 'Part 1',
    };
    expect(validateField(bare, 'anything goes here')).toBeNull();
  });

  // Date fields carry their bounds as top-level min/max STRING dates in some
  // schemas (e.g. adult_intake `dob`: min "1900-01-01", max "2007-10-13") with no
  // min_date/max_date. validateDateValue must honor the folded-in rules.min/max
  // (Codex PR #145 round 2) or an out-of-range AI DOB slips through.
  // NOTE: the runtime schema puts string dates in `min`/`max`, which the TS type
  // annotates as `number` -- cast through `any` to mirror that real shape.
  const dobField: FormField = {
    id: 'dob',
    name: 'Date of Birth',
    spoken_name: 'date of birth',
    type: 'date',
    section_id: 'Part 1',
    min: '1900-01-01' as any,
    max: '2007-10-13' as any,
  };

  it('accepts a date within the top-level min/max', () => {
    expect(validateField(dobField, '1990-06-15')).toBeNull();
  });

  it('rejects a date before the top-level min', () => {
    expect(validateField(dobField, '1899-12-31')).not.toBeNull();
  });

  it('rejects a date after the top-level max', () => {
    expect(validateField(dobField, '2010-01-01')).not.toBeNull();
  });
});

// Checkbox groups: the backend prompt (config.py) tells the model to send a
// checkbox group as a single comma-separated string ("Multiple checkboxes:
// comma-separated exact values"). validateField must split it before membership
// checking or a backend-blessed multi-checkbox answer is false-rejected.
// bd polyglot-pdf-wpw.3 / Codex PR #145 round 2.
describe('validateField (comma-separated checkbox-group values)', () => {
  const checkboxGroup: FormField = {
    id: 'reason[]',
    name: 'Reason for Visit',
    spoken_name: 'reason for visit',
    type: 'checkbox',
    group_kind: 'checkbox',
    section_id: 'Part 1',
    options: ['Fears/Phobias/Worries', 'Family Concerns', 'Work Difficulties'] as any,
  };

  it('accepts a single valid checkbox value', () => {
    expect(validateField(checkboxGroup, 'Family Concerns')).toBeNull();
  });

  it('accepts a comma-separated list of valid checkbox values', () => {
    expect(validateField(checkboxGroup, 'Fears/Phobias/Worries, Family Concerns')).toBeNull();
  });

  it('accepts comma-separated values without surrounding spaces', () => {
    expect(validateField(checkboxGroup, 'Family Concerns,Work Difficulties')).toBeNull();
  });

  it('rejects a comma-separated list containing an invalid member', () => {
    expect(validateField(checkboxGroup, 'Family Concerns, Made Up Option')).not.toBeNull();
  });

  it('still validates an array-shaped checkbox value member-by-member', () => {
    expect(validateField(checkboxGroup, ['Family Concerns', 'Work Difficulties'])).toBeNull();
    expect(validateField(checkboxGroup, ['Family Concerns', 'Nope'])).not.toBeNull();
  });

  it('does NOT split a comma in a single-select value (only checkbox groups split)', () => {
    // A non-checkbox option field whose option literally contains a comma must be
    // matched whole, not split.
    const selectWithComma: FormField = {
      id: 'city_state',
      name: 'City, State',
      spoken_name: 'city and state',
      type: 'select',
      section_id: 'Part 1',
      options: [{ value: 'Springfield, IL', label: 'Springfield, IL' }],
    };
    expect(validateField(selectWithComma, 'Springfield, IL')).toBeNull();
  });
});

// Standalone checkbox fields (type "checkbox" WITHOUT group_kind "checkbox") are
// BOOLEAN per the backend contract ("For checkbox: boolean"), even though they
// carry an `options` array describing their single PDF widget. The enum gate must
// NOT run on them or every valid true/false fill is rejected. Codex PR #145 round 3.
describe('validateField (standalone boolean checkbox)', () => {
  const standaloneCheckbox: FormField = {
    id: 'p2_checkbox3',
    name: 'Previous card never received',
    spoken_name: 'previous card never received',
    type: 'checkbox',
    section_id: 'Part 2',
    // group_kind is NOT "checkbox" -> standalone boolean, not an enum group.
    options: [{ value: 'P2_checkbox3[0]', label: 'My previous card was issued but never received' }],
  };

  it('accepts a boolean true fill (does not enum-check against the option value)', () => {
    expect(validateField(standaloneCheckbox, true)).toBeNull();
  });

  it('accepts a boolean false fill', () => {
    expect(validateField(standaloneCheckbox, false)).toBeNull();
  });

  it('does not reject true even though it is not equal to the option value', () => {
    // Regression: the option value is "P2_checkbox3[0]"; String(true) != that, so
    // an enum check would have rejected it.
    expect(validateField(standaloneCheckbox, 'true')).toBeNull();
  });
});

// Bare date fields (type "date" with only a format, no validation/min/max) must
// still have their FORMAT validated -- a malformed AI date should not land.
// Codex PR #145 round 3.
describe('validateField (bare date field, format-only)', () => {
  const bareDate: FormField = {
    id: 'part_a_ii_spouse_dob',
    name: "Spouse's Date of Birth",
    spoken_name: 'spouse date of birth',
    type: 'date',
    section_id: 'Part A',
    format: 'mm/dd/yyyy' as any,
    // NO validation block, NO min/max/min_date/max_date.
  };

  it('accepts a parseable date', () => {
    expect(validateField(bareDate, '1990-06-15')).toBeNull();
    expect(validateField(bareDate, '06/15/1990')).toBeNull();
  });

  it('rejects a malformed date', () => {
    expect(validateField(bareDate, 'not-a-date')).not.toBeNull();
    expect(validateField(bareDate, 'the fifteenth')).not.toBeNull();
  });

  it('treats an empty optional bare date as valid (not a format error)', () => {
    expect(validateField(bareDate, '')).toBeNull();
  });
});

// shouldShowField conditional visibility, focused on the checkbox-group trigger
// bug (bd polyglot-pdf-vq4m): a multi-option checkbox emits a string[] of selected
// option values, so `equals`/`not_equals` must compare by membership, not strict
// scalar identity (which is always false/true against an array). The I-90's
// p5_line1b_language is gated `equals P5_Checkbox1b[0]` on the p5_checkbox1a
// checkbox group; before the fix it was unreachable in the renderer.
describe('shouldShowField (checkbox-group equals/not_equals trigger)', () => {
  // A dependent gated on a single option of a checkbox-group trigger.
  const gatedEquals: FormField = {
    id: 'p5_line1b_language',
    name: 'Interpreter language',
    type: 'text',
    section_id: 'Part 5',
    show_if: { field: 'p5_checkbox1a', operator: 'equals', value: 'P5_Checkbox1b[0]' },
  } as FormField;

  const gatedNotEquals: FormField = {
    ...gatedEquals,
    id: 'p5_other',
    show_if: { field: 'p5_checkbox1a', operator: 'not_equals', value: 'P5_Checkbox1b[0]' },
  } as FormField;

  // The trigger field, a checkbox GROUP. Passed as the `fields` arg so the
  // comma-separated AI-fill string can be recognized + split (a comma-string is
  // only split when the trigger is a known checkbox group -- Codex PR #259).
  const triggerCheckboxGroup: FormField = {
    id: 'p5_checkbox1a',
    name: 'How the form was completed',
    type: 'checkbox',
    group_kind: 'checkbox',
    section_id: 'Part 5',
  } as FormField;
  const fields = [gatedEquals, gatedNotEquals, triggerCheckboxGroup];

  it('SHOWS an equals-gated dependent when the checkbox group includes the option', () => {
    expect(shouldShowField(gatedEquals, { p5_checkbox1a: ['P5_Checkbox1b[0]'] })).toBe(true);
  });

  it('HIDES an equals-gated dependent when the group has a different option selected', () => {
    expect(shouldShowField(gatedEquals, { p5_checkbox1a: ['P5_Checkbox1a[0]'] })).toBe(false);
  });

  it('HIDES an equals-gated dependent when the group is empty', () => {
    expect(shouldShowField(gatedEquals, { p5_checkbox1a: [] })).toBe(false);
  });

  it('SHOWS the option when it is one of several selected in the group', () => {
    expect(
      shouldShowField(gatedEquals, { p5_checkbox1a: ['P5_Checkbox1a[0]', 'P5_Checkbox1b[0]'] })
    ).toBe(true);
  });

  it('still works for a plain SCALAR trigger (radio/select) under equals', () => {
    const scalarGated = {
      ...gatedEquals,
      show_if: { field: 'mode', operator: 'equals', value: 'yes' },
    } as FormField;
    expect(shouldShowField(scalarGated, { mode: 'yes' })).toBe(true);
    expect(shouldShowField(scalarGated, { mode: 'no' })).toBe(false);
  });

  it('not_equals: HIDES when the group includes the option, SHOWS otherwise', () => {
    expect(shouldShowField(gatedNotEquals, { p5_checkbox1a: ['P5_Checkbox1b[0]'] })).toBe(false);
    expect(shouldShowField(gatedNotEquals, { p5_checkbox1a: ['P5_Checkbox1a[0]'] })).toBe(true);
    expect(shouldShowField(gatedNotEquals, { p5_checkbox1a: [] })).toBe(true);
  });

  // The voice-AI fill path stores a checkbox group as a COMMA-SEPARATED STRING
  // ("Multiple checkboxes: comma-separated exact values", backend/config.py),
  // un-split -- not a string[]. equals/not_equals must compare by membership for
  // that shape too, else the AI path stays broken (Codex PR #259).
  it('SHOWS an equals-gated dependent when the AI comma-separated string includes the option', () => {
    expect(
      shouldShowField(gatedEquals, { p5_checkbox1a: 'P5_Checkbox1b[0], P5_Checkbox2[0]' }, fields)
    ).toBe(true);
  });

  it('HIDES an equals-gated dependent when the comma-separated string omits the option', () => {
    expect(
      shouldShowField(gatedEquals, { p5_checkbox1a: 'P5_Checkbox1a[0], P5_Checkbox2[0]' }, fields)
    ).toBe(false);
  });

  it('handles a single-selection comma-free string (scalar path, exact match)', () => {
    expect(shouldShowField(gatedEquals, { p5_checkbox1a: 'P5_Checkbox1b[0]' }, fields)).toBe(true);
    expect(shouldShowField(gatedEquals, { p5_checkbox1a: 'P5_Checkbox1a[0]' }, fields)).toBe(false);
  });

  it('not_equals: comma-separated string membership (hidden when present, shown when absent)', () => {
    expect(
      shouldShowField(gatedNotEquals, { p5_checkbox1a: 'P5_Checkbox1b[0], P5_Checkbox2[0]' }, fields)
    ).toBe(false);
    expect(
      shouldShowField(gatedNotEquals, { p5_checkbox1a: 'P5_Checkbox1a[0], P5_Checkbox2[0]' }, fields)
    ).toBe(true);
  });

  it('does NOT split a comma-bearing SCALAR trigger value (text/select, not a checkbox group)', () => {
    // A scalar trigger whose value legitimately contains a comma must compare
    // strictly, not be split into members (Codex PR #259).
    const cityTrigger: FormField = {
      id: 'city', name: 'City', type: 'text', section_id: 'Part 5',
    } as FormField; // no group_kind -> scalar
    const gatedOnCity = {
      ...gatedEquals,
      show_if: { field: 'city', operator: 'equals', value: 'Springfield, IL' },
    } as FormField;
    const withCity = [gatedOnCity, cityTrigger];
    // exact comma-bearing match -> shown; the partial "Springfield" must NOT match.
    expect(shouldShowField(gatedOnCity, { city: 'Springfield, IL' }, withCity)).toBe(true);
    const gatedOnPartial = {
      ...gatedEquals,
      show_if: { field: 'city', operator: 'equals', value: 'Springfield' },
    } as FormField;
    expect(shouldShowField(gatedOnPartial, { city: 'Springfield, IL' }, [gatedOnPartial, cityTrigger])).toBe(false);
  });

  it('falls back to strict compare for a comma string when the trigger field is unknown (no fields arg)', () => {
    // Without the fields list we cannot confirm a checkbox group, so a comma
    // string is NOT split -- safer than guessing.
    expect(shouldShowField(gatedEquals, { p5_checkbox1a: 'P5_Checkbox1b[0], P5_Checkbox2[0]' })).toBe(false);
  });
});

// is_empty / is_not_empty on a checkbox-group ARRAY trigger (bd polyglot-pdf-rigd):
// an empty selection ([]) IS empty, mirroring the is_checked array branch. The old
// scalar-only checks treated [] as "not empty" (an array is not null/undefined/""),
// inverting the semantics -- a dependent gated on "controller is_empty" would HIDE
// when nothing was selected and SHOW once any option was picked. Latent (no current
// schema uses is_empty/is_not_empty show_if), pinned here so it stays fixed.
describe('shouldShowField (is_empty / is_not_empty with a checkbox-group array)', () => {
  const gatedIsEmpty: FormField = {
    id: 'dep_empty',
    name: 'Shown when nothing is selected',
    type: 'text',
    section_id: 'Part 5',
    show_if: { field: 'cbg', operator: 'is_empty' },
  } as FormField;

  const gatedIsNotEmpty: FormField = {
    ...gatedIsEmpty,
    id: 'dep_not_empty',
    show_if: { field: 'cbg', operator: 'is_not_empty' },
  } as FormField;

  it('is_empty: SHOWS on an empty selection ([]), HIDES once an option is picked', () => {
    expect(shouldShowField(gatedIsEmpty, { cbg: [] })).toBe(true);
    expect(shouldShowField(gatedIsEmpty, { cbg: ['x'] })).toBe(false);
  });

  it('is_not_empty: HIDES on an empty selection ([]), SHOWS once an option is picked', () => {
    expect(shouldShowField(gatedIsNotEmpty, { cbg: [] })).toBe(false);
    expect(shouldShowField(gatedIsNotEmpty, { cbg: ['x'] })).toBe(true);
  });

  it('scalar triggers keep the null/undefined/"" semantics', () => {
    expect(shouldShowField(gatedIsEmpty, { cbg: '' })).toBe(true);
    expect(shouldShowField(gatedIsEmpty, {})).toBe(true);
    expect(shouldShowField(gatedIsEmpty, { cbg: 'hi' })).toBe(false);
    expect(shouldShowField(gatedIsNotEmpty, { cbg: 'hi' })).toBe(true);
  });
});
