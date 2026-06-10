/**
 * Tests for a_number normalization + validation (bd polyglot-pdf-0zr).
 *
 * Mirrors the backend test (backend/tests/unit/test_field_validation_responses.py
 * TestANumberNormalization) so client and server agree: an Alien Registration
 * Number is accepted with or without its "A" prefix / separators and normalized
 * to the canonical bare-digit form (the PDF comb field stores digits).
 */
import { describe, it, expect } from 'vitest';
import { normalizeFieldValue, validateField } from './validation';
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
    expect(validateField(selectField, ['single', 'married'])).toBeNull();
    expect(validateField(selectField, ['single', 'widowed'])).not.toBeNull();
  });

  it('never echoes the rejected value in the error message (PII-safe)', () => {
    const err = validateField(selectField, 'sensitive-made-up-value');
    expect(err).not.toBeNull();
    expect(err).not.toContain('sensitive-made-up-value');
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
