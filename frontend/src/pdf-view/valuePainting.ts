/**
 * Value painting -- how a field's client-side value displays inside its PDF
 * rect in Preview mode (bd polyglot-pdf-ogrt).
 *
 * This is a CLIENT-SIDE approximation for live feedback; the authoritative
 * fill is always PyMuPDF via /api/fill-pdf (the FilledPreviewModal / download
 * path). Radio and checkbox_group options have no per-option rects yet
 * (phase-2 backfill), so their selected LABELS paint at the field-level rect.
 */

import type { FormField } from '../schema-forms/types/schema';

export type PaintedValue =
  | { kind: 'none' }
  | { kind: 'check' }
  | { kind: 'text'; text: string };

/** Resolve an option value (slug) to its human label. */
function optionLabel(field: FormField, value: string): string {
  const opt = field.options?.find((o) => o.value === value);
  return opt?.label ?? value;
}

/**
 * What to paint for a field's UNWRAPPED raw value. Empty-ish values paint
 * nothing.
 */
export function paintedValueFor(field: FormField, raw: unknown): PaintedValue {
  if (raw === null || raw === undefined || raw === '') return { kind: 'none' };

  switch (field.type) {
    case 'checkbox': {
      // A single-box checkbox paints an X, never a label. This covers both the
      // plain boolean checkbox (no options) and a legacy single-OPTION checkbox
      // -- the widget (CheckboxField) renders any options-bearing checkbox as a
      // multi-box group and stores the checked state as a 1-element array like
      // ['c1_2[0]'], so a 1-element rect would otherwise paint the option's
      // label text overflowing an ~8x8pt box instead of a check (bd
      // polyglot-pdf-jq17). Schema-v2 forbids a checkbox with options outright
      // (a real group is type=checkbox_group, handled below), so this is a
      // defensive path for hand-authored / pre-v2 shapes; a TRUE multi-option
      // group still paints joined labels.
      if (!field.options || field.options.length <= 1) {
        return isCheckboxChecked(raw) ? { kind: 'check' } : { kind: 'none' };
      }
      return paintSelectedLabels(field, raw);
    }
    case 'checkbox_group':
      return paintSelectedLabels(field, raw);
    case 'radio':
    case 'select': {
      if (typeof raw !== 'string' || raw === '') return { kind: 'none' };
      return { kind: 'text', text: optionLabel(field, raw) };
    }
    default: {
      if (typeof raw === 'boolean') return raw ? { kind: 'check' } : { kind: 'none' };
      const text = String(raw);
      return text === '' ? { kind: 'none' } : { kind: 'text', text };
    }
  }
}

/**
 * Is a single-box checkbox checked? Accepts the plain boolean form (true /
 * 'true') AND the array form CheckboxField stores for an options-bearing
 * checkbox: a non-empty array (e.g. ['c1_2[0]']) means checked, [] means
 * unchecked. Any other value is treated as unchecked.
 */
function isCheckboxChecked(raw: unknown): boolean {
  if (raw === true || raw === 'true') return true;
  if (Array.isArray(raw)) return raw.length > 0;
  return false;
}

function paintSelectedLabels(field: FormField, raw: unknown): PaintedValue {
  let values: string[];
  if (Array.isArray(raw)) {
    values = raw.map(String);
  } else if (typeof raw === 'string') {
    // Backcompat: comma-separated multi-select string.
    values = raw.split(',').map((s) => s.trim()).filter(Boolean);
  } else if (raw === true) {
    return { kind: 'check' };
  } else {
    return { kind: 'none' };
  }
  if (values.length === 0) return { kind: 'none' };
  return { kind: 'text', text: values.map((v) => optionLabel(field, v)).join(', ') };
}

/**
 * A font size (px) that fits `text` into a scaled rect: sized off the rect
 * height, shrunk when the text would overflow the width, floored at
 * legibility.
 */
export function fittedFontSize(
  text: string,
  rectWidthPx: number,
  rectHeightPx: number
): number {
  const byHeight = rectHeightPx * 0.62;
  // Approximate average glyph width as 0.55em.
  const byWidth = text.length > 0 ? rectWidthPx / (text.length * 0.55) : byHeight;
  return Math.max(6, Math.min(byHeight, byWidth, 22));
}
