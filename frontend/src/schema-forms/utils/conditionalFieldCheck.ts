/**
 * Conditional field checking and field availability evaluation
 *
 * Determines if a field is available, locked, or hidden based on conditional dependencies.
 * Provides human-readable dependency information for Gemini error responses.
 */

import type {
  ConditionalDisplay,
  FieldAvailability,
  FieldValue,
  FormField,
  FormSchema,
} from "../types/schema";
import { unwrapFieldValue } from "./fieldValue";
import { normalizeToComposite } from "./normalizeToComposite";
import { evaluateAtomicCondition, shouldShowField } from "./validation";

/**
 * Flatten a legacy-or-composite condition to its atomic conditions, tagging
 * each with its POLARITY (bd h76m.8, fresh-eyes round 2): an all_of/any_of
 * atom blocks while UNSATISFIED ("fill X with Y"), a none_of atom blocks
 * while SATISFIED ("X must NOT be Y") -- explaining a none_of atom with the
 * positive wording instructs the user to set exactly the value that is
 * blocking them. [] when the condition is absent or malformed, matching the
 * evaluator's fail-open "treated as visible" behavior for those shapes.
 */
interface PolarAtom {
  atom: ConditionalDisplay;
  negated: boolean;
}

function conditionAtoms(condition: unknown): PolarAtom[] {
  const group = normalizeToComposite(condition);
  if (!group) return [];
  return [
    ...(group.all_of ?? []).map((atom) => ({ atom: atom as ConditionalDisplay, negated: false })),
    ...(group.any_of ?? []).map((atom) => ({ atom: atom as ConditionalDisplay, negated: false })),
    ...(group.none_of ?? []).map((atom) => ({ atom: atom as ConditionalDisplay, negated: true })),
  ];
}

interface ResolvedAtom extends PolarAtom {
  trigger: FormField;
}

/**
 * Resolve each atom's trigger field and order the list so the atoms that are
 * ACTUALLY blocking right now come first: a positive atom that evaluates
 * false, or a negated (none_of) atom that evaluates true. The explanation
 * then names a genuine blocker rather than whichever atom was listed first
 * (which may already be satisfied).
 */
function resolveBlockingAtoms(
  condition: unknown,
  schema: FormSchema,
  fieldValues: Record<string, any>,
): ResolvedAtom[] {
  const resolved = conditionAtoms(condition)
    .map((pa) => ({ ...pa, trigger: schema.fields.find((f) => f.id === pa.atom.field) }))
    .filter((r): r is ResolvedAtom => !!r.trigger);
  const isBlocking = (r: ResolvedAtom): boolean => {
    const holds = evaluateAtomicCondition(r.atom, fieldValues, schema.fields);
    return r.negated ? holds : !holds;
  };
  return [...resolved.filter(isBlocking), ...resolved.filter((r) => !isBlocking(r))];
}

export interface FieldAccessResult {
  /** Whether the field can be accessed/updated */
  accessible: boolean;

  /** Reason if not accessible */
  reason?: "field_hidden" | "field_read_only" | "field_not_found";

  /** Human-readable message */
  message?: string;

  /** Required fields that must be filled (or changed) first */
  required_fields?: Array<{
    field_id: string;
    spoken_name: string;
    required_value?: any;
    /** true when the trigger must NOT hold required_value (a none_of atom) */
    must_not_be?: boolean;
    current_value?: any;
  }>;
}

/**
 * Check if a field can be accessed (for get_field_value or update_form_fields)
 *
 * A field is NOT accessible if:
 * 1. It doesn't exist in the schema (field_not_found)
 * 2. It's conditionally hidden (show_if condition not met)
 * 3. It's read-only due to conditional logic
 *
 * If not accessible, provides information about what fields need to be filled first.
 *
 * @param spokenName - The spoken name Gemini is trying to access
 * @param schema - The full form schema
 * @param fieldValues - Current form field values
 * @returns FieldAccessResult with accessibility info and dependencies
 */
export function checkFieldAccess(
  spokenName: string,
  schema: FormSchema,
  fieldValues: Record<string, any>
): FieldAccessResult {
  // Find the field by spoken name
  const field = schema.fields.find(f => f.spoken_name === spokenName);

  if (!field) {
    return {
      accessible: false,
      reason: "field_not_found",
      message: `The field '${spokenName}' was not found. Please check the spoken name and try again.`
    };
  }

  // Check if field is conditionally hidden
  if (field.show_if) {
    const isVisible = shouldShowField(field, fieldValues, schema.fields);

    if (!isVisible) {
      // Field is hidden - determine what needs to change first. A v2
      // composite condition contributes one required_fields entry per atom
      // whose trigger resolves; the message names the first ACTUALLY-BLOCKING
      // atom with polarity-correct wording (a none_of atom blocks while
      // satisfied -- "must NOT be", never "fill with") and counts the rest.
      // The one-atom legacy positive wording is unchanged (bd h76m.8).
      const resolved = resolveBlockingAtoms(field.show_if, schema, fieldValues);

      if (resolved.length > 0) {
        const first = resolved[0];
        const firstName = first.trigger.spoken_name || first.trigger.name;
        const moreSuffix =
          resolved.length > 1
            ? ` (this field has ${resolved.length - 1} more condition${resolved.length > 2 ? "s" : ""} on: ${resolved
                .slice(1)
                .map((r) => `'${r.trigger.spoken_name || r.trigger.name}'`)
                .join(", ")})`
            : "";
        const instruction = first.negated
          ? `First, the field '${firstName}' must NOT be '${first.atom.value}' -- ask the user to change it.`
          : `First, you need to fill the field '${firstName}' with the value '${first.atom.value}'.`;

        return {
          accessible: false,
          reason: "field_hidden",
          message: `The field '${spokenName}' is not yet available. ${instruction}${moreSuffix}`,
          required_fields: resolved.map((r) => ({
            field_id: r.atom.field,
            spoken_name: r.trigger.spoken_name || r.trigger.name,
            required_value: r.atom.value,
            // Polarity marker (bd h76m.8): true = the trigger must NOT hold
            // this value (a none_of condition); absent/false = must hold it.
            must_not_be: r.negated || undefined,
            current_value: unwrapFieldValue(fieldValues[r.atom.field]),
          })),
        };
      }

      // Couldn't find trigger field (schema error), but still block access
      return {
        accessible: false,
        reason: "field_hidden",
        message: `The field '${spokenName}' is not currently available. It may depend on other fields being filled first.`
      };
    }
  }

  // Check if field is read-only
  if (field.read_only) {
    return {
      accessible: false,
      reason: "field_read_only",
      message: `The field '${spokenName}' is read-only and cannot be modified.`
    };
  }

  // Field is accessible
  return {
    accessible: true
  };
}

/**
 * Get dependency chain for a field
 *
 * Finds all fields that must be filled before this field becomes accessible.
 * Useful for more complex conditional logic.
 *
 * @param field - The target field
 * @param schema - The full form schema
 * @param fieldValues - Current form values
 * @returns Array of fields that are blocking access
 */
export function getDependencyChain(
  field: FormField,
  schema: FormSchema,
  fieldValues: Record<string, any>,
  seen?: Set<string>
): FormField[] {
  const dependencies: FormField[] = [];
  // Guard against conditional cycles (A shows-if B shows-if A): without the
  // visited set the recursion never terminates. The backend now WARNS on such
  // cycles (validate_all_references, bd h76m.3) but must not crash the client.
  const visited = seen ?? new Set<string>([field.id]);

  // Walk EVERY atom of a legacy-or-composite condition (bd h76m.8) -- a
  // composite-gated field depends on all its trigger fields.
  for (const { atom } of conditionAtoms(field.show_if)) {
    if (visited.has(atom.field)) continue;
    const triggerField = schema.fields.find(f => f.id === atom.field);
    if (!triggerField) continue;

    visited.add(triggerField.id);
    dependencies.push(triggerField);

    // Recursively check if trigger field has dependencies
    const nestedDeps = getDependencyChain(triggerField, schema, fieldValues, visited);
    dependencies.push(...nestedDeps);
  }

  return dependencies;
}

/**
 * Evaluate field availability state
 *
 * Determines if a field is available, locked, or hidden based on current form values.
 * Returns availability state and human-readable reason if locked.
 *
 * @param field - The field to evaluate
 * @param fieldValues - Current form field values
 * @param schema - Full form schema (for dependency lookup)
 * @returns Object with availability state and optional locked reason
 */
export function evaluateFieldAvailability(
  field: FormField,
  fieldValues: Record<string, FieldValue>,
  schema: FormSchema
): { availability: FieldAvailability; lockedReason?: string } {
  // Field explicitly hidden in schema
  if (field.hidden) {
    return { availability: 'hidden' };
  }

  // Field is read-only (treat as locked since user can't modify it). The reason
  // is a name-FREE clause: the sole consumer (webFormConnection composes
  // "Cannot update '<name>': <reason>") already names the field, so restating it
  // here produced "Cannot update 'X': The field 'X' is read-only..." -- the field
  // name twice (bd polyglot-pdf-34wc, mirroring the z6xs hidden-field fix).
  if (field.read_only) {
    return {
      availability: 'locked',
      lockedReason: 'it is read-only and cannot be modified.'
    };
  }

  // Check conditional visibility (show_if logic)
  if (field.show_if) {
    const isVisible = shouldShowField(field, fieldValues, schema.fields);

    if (!isVisible) {
      // Field is conditionally hidden - find the blocking field(s). For a v2
      // composite the reason names the first ACTUALLY-BLOCKING atom with
      // polarity-correct wording (a none_of atom blocks while satisfied --
      // telling the user to "select" that value would instruct them to cause
      // the very block; fresh-eyes round 2) and counts the remaining
      // conditions. The one-atom legacy positive wording is unchanged.
      const resolved = resolveBlockingAtoms(field.show_if, schema, fieldValues);

      if (resolved.length > 0) {
        const { atom, trigger, negated } = resolved[0];
        const triggerName = trigger.spoken_name || trigger.name;
        const requiredValue = atom.value;
        const operator = atom.operator || 'equals';

        // Build human-readable reason. 'includes' (v2 membership) reads the
        // same as equals: pick that option on the trigger field.
        let reason: string;
        if (negated) {
          if (operator === 'is_checked') {
            reason = `Uncheck the '${triggerName}' checkbox first.`;
          } else if (operator === 'equals' || operator === 'includes') {
            reason = `Change the '${triggerName}' field first: it must NOT be '${requiredValue}'.`;
          } else {
            reason = `Change the '${triggerName}' field first.`;
          }
        } else if (operator === 'equals' || operator === 'includes') {
          reason = `Complete the '${triggerName}' field first and select '${requiredValue}'.`;
        } else if (operator === 'not_equals') {
          reason = `Complete the '${triggerName}' field first. It must NOT be '${requiredValue}'.`;
        } else if (operator === 'is_checked') {
          reason = `Check the '${triggerName}' checkbox first.`;
        } else {
          reason = `Complete the '${triggerName}' field first.`;
        }
        if (resolved.length > 1) {
          reason += ` (${resolved.length - 1} more condition${resolved.length > 2 ? 's' : ''} on: ${resolved
            .slice(1)
            .map((r) => `'${r.trigger.spoken_name || r.trigger.name}'`)
            .join(', ')})`;
        }

        return {
          availability: 'locked',
          lockedReason: reason
        };
      }

      // Couldn't find trigger field (schema error)
      return {
        availability: 'locked',
        lockedReason: `This field depends on other fields being filled first.`
      };
    }
  }

  // Field is available
  return { availability: 'available' };
}
