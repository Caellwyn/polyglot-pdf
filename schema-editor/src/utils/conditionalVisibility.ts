// Standalone conditional-visibility evaluator for the editor's interactive
// PREVIEW pane (bd polyglot-pdf-s4dp.4). The preview must exercise REAL show_if
// behavior -- a field hides/shows as its controlling field changes -- WITHOUT
// importing the voice app's runtime (frontend/src/schema-forms is wired to the
// WS/state/connection layer; the bead forbids depending on it). So this is a
// faithful, self-contained port of that runtime's shouldShowField semantics
// (frontend/src/schema-forms/utils/validation.ts), operating on the preview's own
// plain local field-value map.
//
// Value shapes the preview stores (mirroring the runtime):
//   - radio / select        -> the selected option's value (string), or undefined
//   - checkbox group         -> string[] of selected option values (multi-select)
//   - single checkbox        -> boolean
//   - text/number/date/etc.  -> string
// A checkbox-group trigger therefore arrives as string[]; equals/not_equals
// compare by MEMBERSHIP (any selected option matches), matching the runtime
// (which also accepts a comma-joined string from the voice path -- preserved here
// for parity even though the preview only produces arrays).

import type { FormField, ConditionalDisplay } from '../types/schema';

// Resolve the selected-option SET when the trigger value is multi-valued (a
// checkbox group), else null (a plain scalar, for which strict identity is
// correct). Mirrors the runtime's selectedSet logic. The comma-string split is
// gated on the trigger field actually being a checkbox group, so a legitimate
// scalar like "Springfield, IL" is never split (Codex PR #259 parity).
//
// Group detection differs from the runtime by NECESSITY: the runtime keys on
// `group_kind === "checkbox"`, but the EDITOR's FormField type has no group_kind
// field (and no editor form-kit sets one), so we key on the editor's actual shape
// -- a checkbox field carrying options[]. This is the faithful editor-side
// equivalent, not a behavioral regression (fresh-eyes finding 5).
function selectedSetFor(
  triggerValue: unknown,
  triggerField: FormField | undefined,
): string[] | null {
  if (Array.isArray(triggerValue)) {
    return triggerValue.map(v => String(v));
  }
  const isCheckboxGroup = triggerField?.type === 'checkbox' &&
    !!triggerField.options && triggerField.options.length > 0;
  if (isCheckboxGroup && typeof triggerValue === 'string' && triggerValue.includes(',')) {
    return triggerValue.split(',').map(s => s.trim());
  }
  return null;
}

// Evaluate a single show_if condition against the current preview values.
// Returns true when the dependent field should be VISIBLE.
export function evaluateCondition(
  cond: ConditionalDisplay,
  fieldValues: Record<string, unknown>,
  fields: FormField[],
): boolean {
  const triggerValue = fieldValues[cond.field];
  const triggerField = fields.find(f => f.id === cond.field);
  const selectedSet = selectedSetFor(triggerValue, triggerField);

  switch (cond.operator) {
    case 'equals':
      if (selectedSet) return selectedSet.includes(String(cond.value));
      return triggerValue === cond.value;

    case 'not_equals':
      if (selectedSet) return !selectedSet.includes(String(cond.value));
      return triggerValue !== cond.value;

    case 'contains':
      if (Array.isArray(triggerValue)) return triggerValue.includes(String(cond.value));
      return String(triggerValue).includes(String(cond.value));

    case 'greater_than':
      return Number(triggerValue) > Number(cond.value);

    case 'less_than':
      return Number(triggerValue) < Number(cond.value);

    case 'is_checked':
      // Single checkbox (boolean) or a checkbox group (array: any selected).
      if (Array.isArray(triggerValue)) return triggerValue.length > 0;
      return triggerValue === true;

    case 'is_empty':
      // Match the runtime exactly (no array special-case): the runtime treats a
      // checkbox-group array as a plain value, so an empty [] is NOT is_empty
      // (an array is not null/undefined/''). This is arguably a runtime bug, but
      // the preview's job is to show what production ACTUALLY does -- bug-for-bug
      // parity -- not a corrected variant (bd polyglot-pdf-rigd tracks the runtime
      // fix). No real schema uses is_empty/is_not_empty show_if today.
      return triggerValue === null || triggerValue === undefined || triggerValue === '';

    case 'is_not_empty':
      return triggerValue !== null && triggerValue !== undefined && triggerValue !== '';

    case 'in':
      if (Array.isArray(cond.value)) {
        return cond.value.map(String).includes(String(triggerValue));
      }
      return false;

    case 'not_in':
      if (Array.isArray(cond.value)) {
        return !cond.value.map(String).includes(String(triggerValue));
      }
      return false;

    default:
      // Unknown operator: match the runtime, which falls back to the field's
      // static hidden state. evaluateCondition has no field handle, so return
      // true here and let shouldShowField apply !field.hidden for this case.
      return true;
  }
}

// The operators evaluateCondition handles explicitly. An operator outside this
// set hits the default branch, where the runtime falls back to the field's static
// hidden state rather than unconditionally showing.
const KNOWN_OPERATORS = new Set([
  'equals', 'not_equals', 'contains', 'greater_than', 'less_than',
  'is_checked', 'is_empty', 'is_not_empty', 'in', 'not_in',
]);

// Whether a field should be shown given the current preview values. A field with
// no show_if is visible unless explicitly hidden; otherwise its show_if decides.
export function shouldShowField(
  field: FormField,
  fieldValues: Record<string, unknown>,
  fields: FormField[],
): boolean {
  if (!field.show_if) return !field.hidden;
  // Unknown operator: mirror the runtime's default (!field.hidden), not an
  // unconditional show (fresh-eyes finding 2).
  if (!KNOWN_OPERATORS.has(field.show_if.operator)) return !field.hidden;
  return evaluateCondition(field.show_if, fieldValues, fields);
}
