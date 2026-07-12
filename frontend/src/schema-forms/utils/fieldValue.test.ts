/**
 * Unit tests for fieldValue utility functions
 * Tests Bug 1: [object Object] Fix
 */

import { describe, it, expect } from 'vitest';
import {
  isFieldValue,
  unwrapFieldValue,
  unwrapToString,
  unwrapToBoolean,
  readFieldEntryWithAlias,
} from './fieldValue';
import type { FieldValue } from '../types/schema';

describe('fieldValue utilities - Bug 1 Fix', () => {
  describe('isFieldValue', () => {
    it('should identify FieldValue objects', () => {
      const fieldValue: FieldValue = { value: 'test', confirmed: true };
      expect(isFieldValue(fieldValue)).toBe(true);
    });

    it('should reject primitive values', () => {
      expect(isFieldValue('test')).toBe(false);
      expect(isFieldValue(123)).toBe(false);
      expect(isFieldValue(true)).toBe(false);
    });

    it('should reject null and undefined', () => {
      expect(isFieldValue(null)).toBe(false);
      expect(isFieldValue(undefined)).toBe(false);
    });

    it('should reject arrays', () => {
      expect(isFieldValue(['test'])).toBe(false);
    });

    it('should reject plain objects without value property', () => {
      expect(isFieldValue({ foo: 'bar' })).toBe(false);
    });
  });

  describe('unwrapFieldValue', () => {
    it('should unwrap FieldValue objects', () => {
      const fieldValue: FieldValue = { value: 'hello', confirmed: true };
      expect(unwrapFieldValue(fieldValue)).toBe('hello');
    });

    it('should return primitive values unchanged', () => {
      expect(unwrapFieldValue('test')).toBe('test');
      expect(unwrapFieldValue(123)).toBe(123);
      expect(unwrapFieldValue(true)).toBe(true);
    });

    it('should handle null values', () => {
      expect(unwrapFieldValue(null)).toBe(null);
      const fieldValue: FieldValue = { value: null };
      expect(unwrapFieldValue(fieldValue)).toBe(null);
    });

    it('should handle boolean values in FieldValue', () => {
      const fieldValue: FieldValue = { value: true };
      expect(unwrapFieldValue(fieldValue)).toBe(true);
    });
  });

  describe('unwrapToString', () => {
    it('should convert primitive strings', () => {
      expect(unwrapToString('hello')).toBe('hello');
    });

    it('should unwrap and convert FieldValue to string', () => {
      const fieldValue: FieldValue = { value: 'world', confirmed: true };
      expect(unwrapToString(fieldValue)).toBe('world');
    });

    it('should convert null to empty string', () => {
      expect(unwrapToString(null)).toBe('');
      const fieldValue: FieldValue = { value: null };
      expect(unwrapToString(fieldValue)).toBe('');
    });

    it('should convert undefined to empty string', () => {
      expect(unwrapToString(undefined)).toBe('');
    });

    it('should convert boolean to string', () => {
      const fieldValue: FieldValue = { value: true };
      expect(unwrapToString(fieldValue)).toBe('true');
    });

    it('should convert number to string', () => {
      expect(unwrapToString(123)).toBe('123');
    });

    it('should prevent [object Object] display', () => {
      const fieldValue: FieldValue = { value: 'test', confirmed: true, lastModified: Date.now() };
      const result = unwrapToString(fieldValue);

      expect(result).toBe('test');
      expect(result).not.toBe('[object Object]');
      expect(result).not.toContain('object');
    });
  });

  describe('unwrapToBoolean', () => {
    it('should handle primitive booleans', () => {
      expect(unwrapToBoolean(true)).toBe(true);
      expect(unwrapToBoolean(false)).toBe(false);
    });

    it('should unwrap FieldValue with boolean', () => {
      const fieldValue: FieldValue = { value: true };
      expect(unwrapToBoolean(fieldValue)).toBe(true);
    });

    it('should convert string "true" to true', () => {
      expect(unwrapToBoolean('true')).toBe(true);
      const fieldValue: FieldValue = { value: 'true' };
      expect(unwrapToBoolean(fieldValue)).toBe(true);
    });

    it('should convert null/undefined to false', () => {
      expect(unwrapToBoolean(null)).toBe(false);
      expect(unwrapToBoolean(undefined)).toBe(false);
    });

    it('should handle numeric representations', () => {
      expect(unwrapToBoolean('1')).toBe(true);
      expect(unwrapToBoolean(1)).toBe(true);
    });
  });

  describe('Real-world Bug Scenarios', () => {
    it('should handle voice AI filling a text field', () => {
      // AI fills field with FieldValue wrapper
      const aiFilledValue: FieldValue = {
        value: 'John Smith',
        confirmed: true,
        lastModified: 1699564800000,
      };

      // Component should display the actual name, not [object Object]
      const displayValue = unwrapToString(aiFilledValue);
      expect(displayValue).toBe('John Smith');
      expect(displayValue).not.toContain('object');
    });

    it('should handle user manually typing in field', () => {
      // User types directly, value is primitive string
      const userTypedValue = 'Jane Doe';

      // Component should display the value unchanged
      const displayValue = unwrapToString(userTypedValue);
      expect(displayValue).toBe('Jane Doe');
    });

    it('should handle select field with FieldValue', () => {
      const selectedValue: FieldValue = {
        value: 'CA',
        confirmed: true,
      };

      const displayValue = unwrapToString(selectedValue);
      expect(displayValue).toBe('CA');
    });

    it('should handle checkbox with FieldValue', () => {
      const checkedValue: FieldValue = {
        value: true,
        confirmed: true,
      };

      const isChecked = unwrapToBoolean(checkedValue);
      expect(isChecked).toBe(true);
    });

    it('should handle radio button with FieldValue', () => {
      const radioValue: FieldValue = {
        value: 'option_b',
        confirmed: true,
      };

      const currentValue = unwrapToString(radioValue);
      expect(currentValue).toBe('option_b');
    });
  });

  // bd polyglot-pdf-luju nit 2: the `[]`-alias read must prefer a MEANINGFUL
  // entry over a hollow one, so a placeholder under the exact key does not shadow
  // a real confirmed answer under the alias key.
  describe('readFieldEntryWithAlias precedence', () => {
    const bracket = 'p5_checkbox1a[]';
    const bare = 'p5_checkbox1a';

    it('returns the exact-key entry when it carries a value', () => {
      const fv = {
        [bracket]: { value: ['P5_Checkbox1b[0]'] as any, confirmed: true },
      } as any;
      expect(readFieldEntryWithAlias(fv, bracket)?.value).toEqual(['P5_Checkbox1b[0]']);
    });

    it('prefers the exact key when BOTH keys carry a value', () => {
      const fv = {
        [bracket]: { value: ['exact'] as any, confirmed: true },
        [bare]: { value: ['alias'] as any, confirmed: true },
      } as any;
      expect(readFieldEntryWithAlias(fv, bracket)?.value).toEqual(['exact']);
    });

    it('falls back to the alias key when the exact key is absent', () => {
      const fv = {
        [bare]: { value: ['x'] as any, confirmed: true },
      } as any;
      // Query the bracket variant; the value lives under the bare key.
      expect(readFieldEntryWithAlias(fv, bracket)?.value).toEqual(['x']);
    });

    it('does NOT let a hollow exact-key entry shadow a real confirmed alias entry', () => {
      const fv = {
        [bracket]: { value: null, confirmed: false } as any, // hollow placeholder
        [bare]: { value: ['P5_Checkbox1b[0]'] as any, confirmed: true }, // real answer
      } as any;
      const entry = readFieldEntryWithAlias(fv, bracket);
      expect(entry?.value).toEqual(['P5_Checkbox1b[0]']);
      expect(entry?.confirmed).toBe(true);
    });

    it('treats an empty-array exact-key entry as hollow and falls through', () => {
      const fv = {
        [bracket]: { value: [] as any, confirmed: false },
        [bare]: { value: ['real'] as any, confirmed: true },
      } as any;
      expect(readFieldEntryWithAlias(fv, bracket)?.value).toEqual(['real']);
    });

    it('returns the exact-key entry (even if hollow) when neither key has a real answer', () => {
      const fv = {
        [bracket]: { value: null, confirmed: false } as any,
      } as any;
      const entry = readFieldEntryWithAlias(fv, bracket);
      expect(entry).toBeDefined();
      expect(entry?.value).toBeNull();
    });

    it('returns undefined when neither key exists', () => {
      expect(readFieldEntryWithAlias({} as any, bracket)).toBeUndefined();
    });
  });
});
