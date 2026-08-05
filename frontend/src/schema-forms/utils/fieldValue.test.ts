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
  reconcileFieldValues,
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

  describe('reconcileFieldValues (bd polyglot-pdf-uw3w / 3irc / qim7)', () => {
    const bare = 'p1_grp';
    const bracket = 'p1_grp[]';

    it('the NEWER lastModified wins, in both directions', () => {
      expect(
        reconcileFieldValues(
          { f: { value: 'persisted-new', lastModified: 200 } } as any,
          { f: { value: 'memory-old', lastModified: 100 } } as any
        ).f.value
      ).toBe('persisted-new');

      expect(
        reconcileFieldValues(
          { f: { value: 'persisted-old', lastModified: 100 } } as any,
          { f: { value: 'memory-new', lastModified: 200 } } as any
        ).f.value
      ).toBe('memory-new');
    });

    it('keeps an entry that exists on only ONE side (the in-memory-only case)', () => {
      const out = reconcileFieldValues(
        { a: { value: 'only-persisted' } } as any,
        { b: { value: 'only-memory' } } as any
      );
      expect(out.a.value).toBe('only-persisted');
      expect(out.b.value).toBe('only-memory');
    });

    it('a dated entry beats an undated one', () => {
      expect(
        reconcileFieldValues(
          { f: { value: 'dated', lastModified: 5 } } as any,
          { f: { value: 'undated' } } as any
        ).f.value
      ).toBe('dated');
    });

    it('with NEITHER side dated, in-memory wins (conservative pre-existing direction)', () => {
      expect(
        reconcileFieldValues(
          { f: { value: 'persisted' } } as any,
          { f: { value: 'memory' } } as any
        ).f.value
      ).toBe('memory');
    });

    it('on a same-millisecond TIE the PERSISTED side wins, in BOTH directions', () => {
      // Date.now() is coarser than the AI-write -> on-screen-edit gap, so this
      // tie is a real production case, and BOTH directions are unsafe if the
      // stale in-memory side wins.

      // Direction 1: a typed answer must not be blanked by a same-ms empty.
      expect(
        reconcileFieldValues(
          { f: { value: 'Real Answer', lastModified: 500 } } as any,
          { f: { value: '', lastModified: 500 } } as any
        ).f.value
      ).toBe('Real Answer');

      // Direction 2 (bd polyglot-pdf-uw3w case 1): a value the user CLEARED must
      // not be revived by a stale in-memory value at a tie. A "meaningful entry
      // wins" tie-break would get this one WRONG -- 'WRONG' is the meaningful
      // side here, and it is the stale one.
      expect(
        reconcileFieldValues(
          { f: { value: '', lastModified: 500 } } as any,
          { f: { value: 'WRONG', lastModified: 500 } } as any
        ).f.value
      ).toBe('');
    });

    it('a both-meaningful tie takes the persisted side (same-write case)', () => {
      // Documents the ONE case the persisted-wins tie-break resolves
      // arbitrarily: both sides meaningful with an identical stamp. It is safe
      // because it is not reachable with DIFFERENT values through any call
      // site -- every connection write goes through
      // SchemaFormStateManager.updateField, which stamps lastModified AND
      // save()s in the same step, so an identical stamp means the two sides
      // hold the SAME write. There is no code path that mutates
      // this.state.fieldValues without persisting it. If one is ever added,
      // this rule needs revisiting and this test is where to start.
      expect(
        reconcileFieldValues(
          { f: { value: 'same-write', lastModified: 700 } } as any,
          { f: { value: 'same-write', lastModified: 700 } } as any
        ).f.value
      ).toBe('same-write');
    });

    it('collapses to ONE entry even when a side holds BOTH key variants', () => {
      // A single side illegally holding both variants must still resolve to one
      // entry, and the entry that actually carries the answer must be the one
      // that survives -- not the hollow exact-key one.
      const out = reconcileFieldValues(
        {
          [bare]: { value: null, lastModified: 100 },
          [bracket]: { value: ['real'], confirmed: true, lastModified: 300 },
        } as any,
        {} as any
      );
      const keys = Object.keys(out).filter(k => k.startsWith('p1_grp'));
      expect(keys).toHaveLength(1);
      expect(out[keys[0]].value).toEqual(['real']);
      expect(out[keys[0]].confirmed).toBe(true);
    });

    it('collapses an []-alias pair to exactly ONE entry (got6 invariant)', () => {
      // The persisted side migrated the value to the bare key (updateField
      // deleted the bracketed variant); a key union would resurrect it.
      const out = reconcileFieldValues(
        { [bare]: { value: ['b'], lastModified: 200 } } as any,
        { [bracket]: { value: ['a'], lastModified: 100 } } as any
      );
      const keys = Object.keys(out).filter(k => k.startsWith('p1_grp'));
      expect(keys).toHaveLength(1);
      expect(out[keys[0]].value).toEqual(['b']);
    });

    it('re-keys the winner under the variant the WINNING side used', () => {
      const out = reconcileFieldValues(
        { [bare]: { value: ['old'], lastModified: 100 } } as any,
        { [bracket]: { value: ['new'], lastModified: 200 } } as any
      );
      expect(Object.keys(out).filter(k => k.startsWith('p1_grp'))).toEqual([bracket]);
      expect(out[bracket].value).toEqual(['new']);
    });

    it('returns an empty map when both sides are empty', () => {
      expect(reconcileFieldValues({} as any, {} as any)).toEqual({});
    });
  });
});
