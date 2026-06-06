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
