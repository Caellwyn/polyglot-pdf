import { describe, it, expect } from 'vitest';
import { paintedValueFor, fittedFontSize, selectedOptionRects } from './valuePainting';
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

  it('resolves a RADIO option value to its label', () => {
    // Titled "radio/select" until bd polyglot-pdf-jpjcv, but it only ever built
    // a radio -- select is a different rule and now has its own tests below.
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

describe('selectedOptionRects (bd polyglot-pdf-lp5v)', () => {
  const rect = (y: number) => ({ page: 3, x: 344, y, width: 10, height: 10 });

  it('returns one rect per SELECTED option that carries a usable pdf_position', () => {
    const f: FormField = {
      ...base,
      type: 'checkbox_group',
      options: [
        { value: 'a', label: 'Alpha', pdf_position: rect(100) },
        { value: 'b', label: 'Beta', pdf_position: rect(120) },
        { value: 'c', label: 'Gamma', pdf_position: rect(140) },
      ],
    };
    expect(selectedOptionRects(f, ['a', 'c'])).toEqual([
      { value: 'a', position: rect(100) },
      { value: 'c', position: rect(140) },
    ]);
    // Backcompat comma-string form selects the same rects.
    expect(selectedOptionRects(f, 'a, c')).toEqual([
      { value: 'a', position: rect(100) },
      { value: 'c', position: rect(140) },
    ]);
  });

  it('resolves a radio selection to its single option rect', () => {
    const f: FormField = {
      ...base,
      type: 'radio',
      options: [
        { value: 'yes', label: 'Yes', pdf_position: rect(100) },
        { value: 'no', label: 'No', pdf_position: rect(120) },
      ],
    };
    expect(selectedOptionRects(f, 'no')).toEqual([{ value: 'no', position: rect(120) }]);
    expect(selectedOptionRects(f, '')).toEqual([]);
  });

  it('returns [] when options carry no rects (label-at-field-rect fallback)', () => {
    const f: FormField = {
      ...base,
      type: 'radio',
      options: [
        { value: 'yes', label: 'Yes' },
        { value: 'no', label: 'No' },
      ],
    };
    expect(selectedOptionRects(f, 'yes')).toEqual([]);
  });

  it('rejects degenerate (zero-size) option rects', () => {
    const f: FormField = {
      ...base,
      type: 'radio',
      options: [
        { value: 'yes', label: 'Yes', pdf_position: { page: 1, x: 0, y: 0, width: 0, height: 0 } },
      ],
    };
    expect(selectedOptionRects(f, 'yes')).toEqual([]);
  });

  it('never paints option rects for a select (dropdowns have no printed boxes)', () => {
    const f: FormField = {
      ...base,
      type: 'select',
      options: [{ value: '2', label: '2', pdf_position: rect(100) }],
    };
    expect(selectedOptionRects(f, '2')).toEqual([]);
  });

  it('falls back ENTIRELY when any selected value lacks a usable rect (all-or-nothing)', () => {
    // Partial marks would silently hide the uncovered selection; the label
    // fallback shows every selected value instead.
    const f: FormField = {
      ...base,
      type: 'checkbox_group',
      options: [
        { value: 'a', label: 'Alpha', pdf_position: rect(100) },
        { value: 'b', label: 'Beta' }, // no rect
      ],
    };
    expect(selectedOptionRects(f, ['a', 'b'])).toEqual([]);
    // Same for a selected value with no matching option at all.
    expect(selectedOptionRects(f, ['a', 'mystery'])).toEqual([]);
    // A fully-covered selection still paints marks.
    expect(selectedOptionRects(f, ['a'])).toEqual([{ value: 'a', position: rect(100) }]);
  });

  it('falls back when an option rect sits on a DIFFERENT page than the field', () => {
    // PDFViewer buckets overlays into page containers by the FIELD's page; a
    // cross-page option rect would paint at the wrong screen position.
    const f: FormField = {
      ...base,
      type: 'radio',
      pdf_position: { page: 1, x: 10, y: 10, width: 40, height: 12 },
      options: [{ value: 'a', label: 'Alpha', pdf_position: rect(100) }], // page 3
    };
    expect(selectedOptionRects(f, 'a')).toEqual([]);
  });
});

describe('a select paints its VALUE, not its label (bd polyglot-pdf-jpjcv)', () => {
  const state: FormField = {
    id: 'mail_state', name: 'mail_state', spoken_name: 'state',
    type: 'select', section_id: 's',
    options: [
      { value: 'AL', label: 'Alabama (AL)' },
      { value: 'AA', label: 'Armed Forces Americas (AA)' },
    ],
  } as unknown as FormField;

  it('paints the export code, which is what actually prints', () => {
    // For a select the VALUE is what PyMuPDF writes into the combobox, so the
    // overlay showing it means the author sees exactly what will print.
    expect(paintedValueFor(state, 'AL')).toEqual({ kind: 'text', text: 'AL' });
    expect(paintedValueFor(state, 'AA')).toEqual({ kind: 'text', text: 'AA' });
  });

  it('does NOT paint the speakable label, which would not fit', () => {
    // THE REGRESSION THIS PREVENTS. jpjcv made labels speakable for the voice
    // model, so painting the label put "Armed Forces Americas (AA)" -- ~86px at
    // the 6px font floor -- into an i-90 state box 36px wide. The overlay clips,
    // so the author read "Armed For" where "AA" used to sit crisp at 11px.
    const painted = paintedValueFor(state, 'AA');
    expect(painted).not.toEqual({ kind: 'text', text: 'Armed Forces Americas (AA)' });
  });

  it('the label really would have overflowed -- the reason, not just the rule', () => {
    // Pins the GEOMETRY, so this stays honest if the font floor is ever tuned.
    const W = 36, H = 18;                       // the real i-90 state rect
    const fits = (t: string) => t.length * 0.55 * fittedFontSize(t, W, H) <= W;
    expect(fits('AA')).toBe(true);
    expect(fits('Armed Forces Americas (AA)')).toBe(false);
  });

  it('falls back to the raw token for an unknown value', () => {
    expect(paintedValueFor(state, 'ZZ')).toEqual({ kind: 'text', text: 'ZZ' });
  });
});
