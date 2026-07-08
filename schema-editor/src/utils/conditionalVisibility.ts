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
// A checkbox-group trigger therefore arrives as string[]; membership operators
// (includes/not_includes) test that array, and equals/not_equals are PURE scalar
// comparisons (never membership) -- matching the runtime after the P6.2
// strictness flip (bd h76m.16).

import type { FormField, ConditionalDisplay } from '../types/schema';
import {
  normalizeToComposite,
  type AtomicCondition,
  type CompositeCondition,
} from './normalizeToComposite';

// Resolve the selected-option SET when the trigger value is multi-valued (a
// checkbox group), else null (a plain scalar, for which strict identity is
// correct). Mirrors the runtime's selectedSet logic. A v2 checkbox_group value
// is ALWAYS a string[] by the time it reaches the evaluator: the voice-AI
// comma-joined string is converted to an array at the single ingress boundary
// BEFORE storage, so the evaluator never sees a comma-string for a group. The
// comma-split + isCheckboxGroup-comma branch were DELETED at the P6.2 strictness
// flip (bd h76m.16), matching the runtime's selectedSet.
function selectedSetFor(triggerValue: unknown): string[] | null {
  if (Array.isArray(triggerValue)) {
    return triggerValue.map(v => String(v));
  }
  return null;
}

// Evaluate a single ATOMIC condition against the current preview values (the
// leaf evaluator the composite buckets and the legacy one-atom path share
// since bd h76m.8). Returns true when the condition holds. Accepts the
// structural atom shape normalizeToComposite emits; the legacy
// ConditionalDisplay satisfies it.
export function evaluateCondition(
  cond: AtomicCondition | ConditionalDisplay,
  fieldValues: Record<string, unknown>,
  _fields: FormField[],
): boolean {
  const triggerValue = fieldValues[cond.field];
  const selectedSet = selectedSetFor(triggerValue);

  // v2 membership: is the named option slug in the group's selected set? A
  // single selection may arrive as a bare scalar -- compare by string
  // identity there; an empty/absent selection includes nothing. Mirrors the
  // runtime evaluator (frontend validation.ts, bd h76m.8).
  const membershipIncludes = (): boolean => {
    if (selectedSet) return selectedSet.includes(String(cond.value));
    if (triggerValue === null || triggerValue === undefined || triggerValue === '') {
      return false;
    }
    return String(triggerValue) === String(cond.value);
  };

  switch (cond.operator) {
    case 'equals':
      // Pure scalar comparison. The vq4m equals-means-membership hack was
      // DELETED at the P6.2 strictness flip (bd h76m.16): v2 expresses
      // membership with includes/not_includes, and the backend rejects
      // equals-on-a-checkbox_group at parse. Mirrors the runtime evaluator.
      return triggerValue === cond.value;

    case 'not_equals':
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
      // Match the runtime (bd polyglot-pdf-rigd): a checkbox-group value is an
      // array, and an empty selection ([]) IS empty -- mirroring the is_checked
      // array branch above. Scalars keep the null/undefined/'' check.
      if (Array.isArray(triggerValue)) return triggerValue.length === 0;
      return triggerValue === null || triggerValue === undefined || triggerValue === '';

    case 'is_not_empty':
      if (Array.isArray(triggerValue)) return triggerValue.length > 0;
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

    case 'includes':
      return membershipIncludes();

    case 'not_includes':
      return !membershipIncludes();

    default:
      // Unknown operator: match the runtime, which falls back to the field's
      // static hidden state. evaluateCondition has no field handle, so return
      // true here and let shouldShowField apply !field.hidden for this case.
      return true;
  }
}

// The operators evaluateCondition handles explicitly. An operator outside this
// set ANYWHERE in a condition makes the whole condition unintelligible and the
// caller falls back to the field's static hidden state rather than
// unconditionally showing (mirrors the runtime, bd h76m.8).
const KNOWN_OPERATORS = new Set([
  'equals', 'not_equals', 'contains', 'greater_than', 'less_than',
  'is_checked', 'is_empty', 'is_not_empty', 'in', 'not_in',
  'includes', 'not_includes',
]);

function conditionHasUnknownOperator(group: CompositeCondition): boolean {
  return [group.all_of, group.any_of, group.none_of].some(
    (bucket) => bucket?.some((atom) => !KNOWN_OPERATORS.has(atom.operator)),
  );
}

// Evaluate a canonical composite condition (bd h76m.8): ALL of all_of hold,
// AND at least one of any_of holds (when present), AND none of none_of hold.
// An omitted bucket is vacuously satisfied. Mirrors the runtime evaluator.
function evaluateConditionGroup(
  group: CompositeCondition,
  fieldValues: Record<string, unknown>,
  fields: FormField[],
): boolean {
  if (group.all_of && !group.all_of.every(c => evaluateCondition(c, fieldValues, fields))) {
    return false;
  }
  if (
    group.any_of &&
    group.any_of.length > 0 &&
    !group.any_of.some(c => evaluateCondition(c, fieldValues, fields))
  ) {
    return false;
  }
  if (group.none_of && group.none_of.some(c => evaluateCondition(c, fieldValues, fields))) {
    return false;
  }
  return true;
}

// Whether a field should be shown given the current preview values. Since bd
// h76m.8 the condition is consumed through normalizeToComposite, so a legacy
// single condition and a v2 {all_of/any_of/none_of} group evaluate through
// ONE path. Absent/malformed conditions and conditions carrying an unknown
// operator fall back to the field's static hidden state (fail-open).
export function shouldShowField(
  field: FormField,
  fieldValues: Record<string, unknown>,
  fields: FormField[],
): boolean {
  const group = normalizeToComposite(field.show_if);
  if (!group) return !field.hidden;
  if (conditionHasUnknownOperator(group)) return !field.hidden;
  return evaluateConditionGroup(group, fieldValues, fields);
}

// Whether a field is REQUIRED right now (bd h76m.8): statically required, or
// dynamically via a satisfied require_if (same legacy-or-composite shape as
// show_if). Fail-open means NOT required. Mirrors the runtime's
// isFieldRequired; the editor's FormField carries `required` as a plain
// boolean rather than validation.required.
export function isFieldRequired(
  field: FormField,
  fieldValues: Record<string, unknown>,
  fields: FormField[],
): boolean {
  if (field.required) return true;
  const group = normalizeToComposite(field.require_if);
  if (!group || conditionHasUnknownOperator(group)) return false;
  return evaluateConditionGroup(group, fieldValues, fields);
}
