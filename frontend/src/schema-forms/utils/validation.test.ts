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
});
