import { describe, it, expect } from 'vitest';
import { paintedValueFor, fittedFontSize } from './valuePainting';
import type { FormField } from '../schema-forms/types/schema';

const base = { id: 'f1', name: 'F1', spoken_name: 'f one', section_id: 's1' } as any;

describe('paintedValueFor', () => {
  it('paints nothing for empty values', () => {
    const f: FormField = { ...base, type: 'text' };
    expect(paintedValueFor(f, '')).toEqual({ kind: 'none' });
    expect(paintedValueFor(f, null)).toEqual({ kind: 'none' });
    expect(paintedValueFor(f, undefined)).toEqual({ kind: 'none' });
  });

  it('paints text values verbatim', () => {
    const f: FormField = { ...base, type: 'text' };
    expect(paintedValueFor(f, 'Ramanujan')).toEqual({ kind: 'text', text: 'Ramanujan' });
  });

  it('paints a check for a true boolean checkbox and nothing for false', () => {
    const f: FormField = { ...base, type: 'checkbox' };
    expect(paintedValueFor(f, true)).toEqual({ kind: 'check' });
    expect(paintedValueFor(f, false)).toEqual({ kind: 'none' });
  });

  it('resolves radio/select option values to their labels', () => {
    const f: FormField = {
      ...base,
      type: 'radio',
      options: [
        { value: 'yes_proceed', label: 'Yes' },
        { value: 'no_proceed', label: 'No' },
      ],
    };
    expect(paintedValueFor(f, 'yes_proceed')).toEqual({ kind: 'text', text: 'Yes' });
    // Unknown option value falls back to the raw token.
    expect(paintedValueFor(f, 'mystery')).toEqual({ kind: 'text', text: 'mystery' });
  });

  it('paints an X (never a label) for a single-OPTION checkbox (bd polyglot-pdf-jq17)', () => {
    // The combat-zone box on f1040 is the concrete repro: a single-box
    // checkbox. CheckboxField renders any options-bearing checkbox as a
    // multi-box group and stores the checked state as a 1-element array
    // (['c1_2[0]']), not a boolean. Before the fix, valuePainting routed a
    // 1-element options checkbox to paintSelectedLabels and painted the option
    // LABEL text overflowing the ~8x8pt box. It must paint a check instead.
    //
    // (Schema-v2 now forbids a checkbox with options -- a real group is
    // type=checkbox_group -- so this shape only arises from hand-authored /
    // pre-v2 kits; the fix keeps valuePainting correct for it defensively.)
    const f: FormField = {
      ...base,
      type: 'checkbox',
      options: [{ value: 'c1_2[0]', label: 'Combat zone' }],
    };
    // Checked: CheckboxField's stored shape is a 1-element array.
    expect(paintedValueFor(f, ['c1_2[0]'])).toEqual({ kind: 'check' });
    // Unchecked: an empty array (a cleared group) paints nothing.
    expect(paintedValueFor(f, [])).toEqual({ kind: 'none' });
    // A bare boolean on the same field still reads as a check / none.
    expect(paintedValueFor(f, true)).toEqual({ kind: 'check' });
    expect(paintedValueFor(f, false)).toEqual({ kind: 'none' });
  });

  it('joins checkbox_group selections as labels', () => {
    const f: FormField = {
      ...base,
      type: 'checkbox_group',
      options: [
        { value: 'a', label: 'Alpha' },
        { value: 'b', label: 'Beta' },
      ],
    };
    expect(paintedValueFor(f, ['a', 'b'])).toEqual({ kind: 'text', text: 'Alpha, Beta' });
    // Backcompat comma-string form.
    expect(paintedValueFor(f, 'a, b')).toEqual({ kind: 'text', text: 'Alpha, Beta' });
    expect(paintedValueFor(f, [])).toEqual({ kind: 'none' });
  });
});

describe('fittedFontSize', () => {
  it('sizes off height for short text', () => {
    expect(fittedFontSize('Hi', 200, 20)).toBeCloseTo(12.4, 1);
  });

  it('shrinks for long text in a narrow rect', () => {
    const size = fittedFontSize('a-very-long-value-string-here', 60, 20);
    expect(size).toBeLessThan(12.4);
    expect(size).toBeGreaterThanOrEqual(6);
  });

  it('never goes below the 6px floor', () => {
    expect(fittedFontSize('x'.repeat(500), 30, 20)).toBe(6);
  });
});
