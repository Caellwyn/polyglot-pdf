/**
 * Value painting -- how a field's client-side value displays inside its PDF
 * rect in Preview mode (bd polyglot-pdf-ogrt).
 *
 * This is a CLIENT-SIDE approximation for live feedback; the authoritative
 * fill is always PyMuPDF via /api/fill-pdf (the FilledPreviewModal / download
 * path). When a selected radio/checkbox/checkbox_group option carries its own
 * pdf_position (backfilled per-option rects, bd polyglot-pdf-5f41), a mark
 * paints at that option's printed box (selectedOptionRects, bd
 * polyglot-pdf-lp5v); options without rects fall back to selected LABELS at
 * the field-level rect.
 */

import type { FormField, PDFPosition } from '../schema-forms/types/schema';
import { hasValidCoordinates } from './pdfCoordinates';

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
    case 'select': {
      // A select paints its VALUE, not its label -- because for a select the
      // value IS what PyMuPDF writes into the combobox (bd polyglot-pdf-hmkas),
      // so painting it makes the overlay show exactly what will print.
      //
      // It is also the only thing that FITS. Labels became speakable names for
      // the voice model (bd polyglot-pdf-jpjcv): "Armed Forces Americas (AA)"
      // needs ~86px at the 6px font floor, in an i-90 state box 36px wide, and
      // .pdf-field-overlay clips -- so the author would read "Armed For" where
      // "AA" used to sit crisp at 11px. Same class as the jq17 checkbox bug
      // above: a label sized for reading aloud overflowing a widget rect.
      if (typeof raw !== 'string' || raw === '') return { kind: 'none' };
      return { kind: 'text', text: raw };
    }
    case 'radio': {
      // A radio keeps painting its LABEL: its value is an internal slug
      // ('apply_new_itin') that never prints -- widget identity lives in
      // pdf_on_value -- so the value would be meaningless on the page.
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

/** The selected values of an option-bearing field, as slugs. */
function selectedValues(field: FormField, raw: unknown): string[] {
  switch (field.type) {
    case 'radio':
      return typeof raw === 'string' && raw !== '' ? [raw] : [];
    case 'checkbox':
    case 'checkbox_group': {
      if (Array.isArray(raw)) return raw.map(String);
      if (typeof raw === 'string') {
        // Backcompat: comma-separated multi-select string.
        return raw.split(',').map((s) => s.trim()).filter(Boolean);
      }
      return [];
    }
    default:
      // Selects are dropdowns: one shared widget, options are choice VALUES
      // with no printed box of their own -- never option-rect painted.
      return [];
  }
}

export interface SelectedOptionRect {
  value: string;
  position: PDFPosition;
}

/**
 * The rects to paint selection marks at: one per SELECTED option (bd
 * polyglot-pdf-lp5v). ALL-OR-NOTHING: if ANY selected value lacks a usable
 * rect (unknown slug, missing/degenerate pdf_position, or a rect on a
 * different page than the field's -- PDFViewer buckets overlays into page
 * containers by the FIELD's page, so a cross-page rect would paint at the
 * wrong screen position), the whole selection returns [] and callers fall
 * back to paintedValueFor's label-at-field-rect, which shows every selected
 * value. Partial marks would silently hide the uncovered selections.
 */
export function selectedOptionRects(field: FormField, raw: unknown): SelectedOptionRect[] {
  if (!field.options || field.options.length === 0) return [];
  const values = selectedValues(field, raw);
  if (values.length === 0) return [];
  const rects: SelectedOptionRect[] = [];
  for (const value of values) {
    const opt = field.options.find((o) => o.value === value);
    if (!opt || !hasValidCoordinates(opt.pdf_position)) return [];
    if (field.pdf_position && opt.pdf_position.page !== field.pdf_position.page) return [];
    rects.push({ value, position: opt.pdf_position });
  }
  return rects;
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
