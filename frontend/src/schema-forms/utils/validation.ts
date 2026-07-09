/**
 * Validation utilities for schema-based forms
 *
 * Validates field values against ValidationRules from schema
 */

import type { FormField, ValidationRules } from "../types/schema";
import { unwrapFieldValue } from "./fieldValue";
import {
  normalizeToComposite,
  type AtomicCondition,
  type CompositeCondition,
} from "./normalizeToComposite";

/**
 * Digit-only presets: input is a sequence of digits but is spoken/written with
 * punctuation (an "A" prefix, commas, "$", spaces, dashes). The stored form is
 * bare digits. Keep in sync with the backend _DIGIT_PRESETS in
 * backend/utils/field_validator.py (bd polyglot-pdf-jnjj.40).
 */
const DIGIT_PRESETS = new Set(["a_number", "uscis_account"]);

/**
 * Normalize a raw input value to the field's canonical stored form, keyed on
 * format_preset. Mirrors the backend normalize_value() in
 * backend/utils/field_validator.py so client and server agree on what gets
 * stored (bd polyglot-pdf-0zr).
 *
 * Digit-only presets (a_number, uscis_account): an Alien Registration Number is
 * spoken as "A" + 7-9 digits and a USCIS account number as 12 digits, often with
 * dashes/spaces/commas, but the PDF comb field stores bare digits. Drop a single
 * leading A/a (a_number only) and strip PUNCTUATION; KEEP embedded letters so a
 * wrong value like "ABC1234..." stays invalid instead of being coerced to digits
 * (Codex PR #249). Mirrors the backend normalize_value + _DIGIT_PUNCT_RE. Other
 * presets and non-string values pass through unchanged (bd polyglot-pdf-jnjj.40).
 */
export function normalizeFieldValue(field: FormField, value: any): any {
  const preset = field.validation?.format_preset;
  if (preset && DIGIT_PRESETS.has(preset) && typeof value === "string") {
    let stripped = value.trim();
    // a_number only: a leading letter is its "A" prefix. For uscis_account a
    // leading letter is an error to preserve, not a prefix to drop.
    if (preset === "a_number" && (stripped[0] === "A" || stripped[0] === "a")) {
      stripped = stripped.slice(1);
    }
    // Strip punctuation only (NOT letters), matching the backend _DIGIT_PUNCT_RE.
    return stripped.replace(/[\s,.$-]/g, "");
  }
  return value;
}

/**
 * Validate a field value against its validation rules
 *
 * @param field - The field to validate
 * @param value - The value to validate (may be FieldValue wrapper or primitive)
 * @returns Error message if invalid, null if valid
 */
export function validateField(field: FormField, value: any): string | null {
  // Bug Fix: Unwrap FieldValue object before validation
  // Normalize to the canonical form first (e.g. strip an A-Number's "A" prefix)
  // so correct-but-differently-formatted input validates (bd polyglot-pdf-0zr).
  const rawValue = unwrapFieldValue(value);
  const actualValue = normalizeFieldValue(field, rawValue);

  // An empty array (a checkbox group with NO selections) counts as empty, same as
  // null/undefined/"" (fresh-eyes PR #145 round 4): otherwise a REQUIRED checkbox
  // group submitted as `[]` would slip past the required check (which gates on
  // normalizedEmpty) AND the enum loop (which is vacuous for `[]`), landing a blank
  // value that confirm_field would then treat as filled.
  const normalizedEmpty =
    actualValue === null ||
    actualValue === undefined ||
    actualValue === "" ||
    (Array.isArray(actualValue) && actualValue.length === 0);

  // Enum / option-membership runs INDEPENDENTLY of field.validation: for a
  // STRING-enum field (select, radio, or a checkbox GROUP), the option set IS the
  // constraint, and such fields often carry no `validation` block at all. A
  // non-empty value MUST be one of the options -- this guards an AI-applied value
  // where the model invents an option that does not exist in the schema (bd
  // polyglot-pdf-wpw.3). Checked before the early `!field.validation` return below
  // so a bad enum is still rejected.
  //
  // CRITICAL SCOPING (Codex PR #145 round 3): a STANDALONE checkbox is a
  // BOOLEAN field -- the backend contract is "For checkbox: boolean"
  // (config.py), so Gemini sends true/false, not an option value. Running the
  // enum check on it would compare "true" against an option and reject every
  // valid fill. The enum gate applies to select/radio and options-bearing
  // checkbox GROUPS (see isStringEnumField) -- EXCEPT a boolean-intent value on a
  // field that is really a boolean toggle. Two cases:
  //   - an ACTUAL boolean value is boolean-intent on any checkbox (a genuine
  //     on/off signal, never an option-slug selection);
  //   - the literal "true"/"false" STRING (the backend tool contract's documented
  //     boolean encoding) is boolean-intent ONLY on a SINGLE-option checkbox (a real
  //     boolean toggle), NOT on a multi-option selection group.
  // This matters because a standalone checkbox that carries a ONE-element
  // `options` array (describing its single PDF widget) trips isStringEnumField's
  // options.length>0 rule (bd polyglot-pdf-5jvn, matching
  // canonicalizeAiCheckboxGroupValue/CheckboxField), which calls it a "group" too;
  // without this carve-out its true/false fill would enum-reject. `isCheckboxGroupField`
  // is ALSO true for such a field (options.length>0), so it cannot distinguish the two;
  // the load-bearing distinction is the OPTION COUNT -- a genuine boolean toggle has
  // at most one option, a selection group has 2+. Scoping the STRING case to
  // single-option checkboxes keeps the carve-out from reopening the 5jvn silent-drop
  // for a real group: an AI "true" on a multi-option group (e.g. p3_race) is NOT a
  // valid option, so it must still enum-reject (Opus fresh-eyes finding). Mirrors
  // canonicalizeAiCheckboxGroupValue's own boolean-intent exclusion.
  const isSingleOptionCheckbox =
    field.type === "checkbox" && (field.options?.length ?? 0) <= 1;
  const isBooleanIntent =
    field.type === "checkbox" &&
    (typeof actualValue === "boolean" ||
      (isSingleOptionCheckbox && /^(true|false)$/i.test(String(actualValue).trim())));
  if (!normalizedEmpty && !isBooleanIntent && field.options && field.options.length > 0 && isStringEnumField(field)) {
    const optionError = validateOptionMembership(field, actualValue);
    if (optionError) return optionError;
  }

  // Build the EFFECTIVE rules by folding the top-level constraint fields
  // (max_length / min / max) into any explicit `validation` block (bd
  // polyglot-pdf-wpw.3 / Codex PR #145). Many generated schemas (e.g.
  // form-kits/i-90: dozens of text fields with a top-level `max_length` and NO
  // `validation` block) carry their constraints at the field level, not under
  // `validation`. Without this merge an over-length AI value would bypass the
  // length check entirely -- exactly the "block too-long strings" goal of this
  // change. An explicit `validation` value wins over the top-level field when
  // both are set. (Top-level min_date/max_date are read directly by
  // validateDateValue from `field.*`, so they need no folding here.)
  const effectiveRules: ValidationRules = {
    ...(field.max_length !== undefined ? { max_length: field.max_length } : {}),
    ...(field.min !== undefined ? { min: field.min } : {}),
    ...(field.max !== undefined ? { max: field.max } : {}),
    ...(field.validation ?? {}),
  };

  // Date fields carry an inherent FORMAT constraint even with no rules: a date
  // field with only `format`/`type:"date"` and no validation block (e.g. i-589's
  // many `type:"date"`, `format:"mm/dd/yyyy"` fields) must still reject a malformed
  // AI-applied date (Codex PR #145 round 3). validateDateValue checks parseability
  // + min/max regardless of rules, so always run it for a non-empty date value
  // rather than letting the empty-effectiveRules early return below skip it.
  if (field.type === "date" && !normalizedEmpty) {
    return validateDateValue(field, String(actualValue), effectiveRules);
  }

  if (Object.keys(effectiveRules).length === 0) {
    return null; // No rules-based constraints (top-level or validation block)
  }

  const rules = effectiveRules;

  const rawHadContent = rawValue !== null && rawValue !== undefined && String(rawValue).trim() !== "";

  // Guard: if a non-empty input normalized down to empty (e.g. an a_number like
  // "A" or "A---" with no digits), it is INVALID, not unfilled -- the empty-skip
  // below would otherwise silently accept it (fresh-eyes finding, PR #98).
  if (rawHadContent && normalizedEmpty) {
    return `${field.name} format is invalid`;
  }

  // Required check
  if (rules.required && normalizedEmpty) {
    return `${field.name} is required`;
  }

  // Skip other checks if value is empty and not required
  if (normalizedEmpty) {
    return null;
  }

  // Type-specific validation
  if (field.type === "text" || field.type === "textarea" || field.type === "email" || field.type === "tel") {
    return validateTextValue(field, String(actualValue), rules);
  }

  if (field.type === "number") {
    return validateNumberValue(field, actualValue, rules);
  }

  // Date fields are handled by the early `field.type === "date"` return above
  // (which runs whether or not there are rules), so they never reach here.

  return null;
}

/**
 * Validate text/textarea/email/tel values
 */
function validateTextValue(field: FormField, value: string, rules: ValidationRules): string | null {
  // Min length
  if (rules.min_length !== undefined && value.length < rules.min_length) {
    return `${field.name} must be at least ${rules.min_length} characters`;
  }

  // Max length
  if (rules.max_length !== undefined && value.length > rules.max_length) {
    return `${field.name} must be at most ${rules.max_length} characters`;
  }

  // Digits only (numeric characters 0-9)
  if (rules.digits_only && !/^\d+$/.test(value)) {
    return `${field.name} must contain only numeric digits (0-9)`;
  }

  // Format presets
  if (rules.format_preset) {
    const presetError = validateFormatPreset(field, value, rules.format_preset);
    if (presetError) return presetError;
  }

  // Custom regex pattern
  if (rules.pattern) {
    try {
      const regex = new RegExp(rules.pattern);
      if (!regex.test(value)) {
        return rules.custom_error || `${field.name} format is invalid`;
      }
    } catch (e) {
      console.error(`[Validation] Invalid regex pattern for field ${field.id}:`, e);
    }
  }

  return null;
}

/**
 * Extract the allowed value of an option in EITHER runtime shape: the
 * `{ value, label }` object form (most form-kit schemas) or the plain-string
 * form (e.g. adult_intake_demo_schema.json: `options: ["Agender", ...]`, the
 * shape the backend `List[str]` normalizer also emits). A string option's
 * allowed value is the string itself. bd polyglot-pdf-wpw.3 / Codex PR #145.
 */
function optionValue(opt: any): string | undefined {
  if (typeof opt === "string") return opt;
  if (opt && typeof opt === "object" && opt.value !== undefined) return String(opt.value);
  return undefined;
}

/**
 * Whether a field's value is a STRING drawn from its option set -- i.e. the enum
 * check applies. True for `select`, `radio`, and checkbox GROUPS. FALSE for a
 * STANDALONE checkbox (type "checkbox" with NO options), whose value is a
 * BOOLEAN per the backend contract ("For checkbox: boolean"). Running the enum
 * check on a standalone checkbox would reject every valid true/false fill
 * (Codex PR #145 round 3).
 *
 * A checkbox GROUP is the v2 `checkbox_group` type, OR (legacy shape) a
 * `type:"checkbox"` field carrying an options[] array. The old `group_kind`
 * marker was DELETED at the P6.2 strictness flip (bd h76m.16) -- no shipped kit
 * ever set it, and v2 carries the group-ness in the TYPE.
 */
function isStringEnumField(field: FormField): boolean {
  if (field.type === "select" || field.type === "radio") return true;
  if (field.type === "checkbox_group") return true;
  if (field.type === "checkbox" && isCheckboxGroupField(field)) return true;
  return false;
}

/**
 * Whether a field is a checkbox GROUP -- vs. a standalone boolean checkbox.
 * Shared by isStringEnumField and validateOptionMembership so both agree with
 * canonicalizeAiCheckboxGroupValue (webFormConnection.ts) and the CheckboxField
 * renderer: the v2 `checkbox_group` type, or a `type:"checkbox"` field that
 * carries options[] (the legacy options-bearing group shape).
 */
function isCheckboxGroupField(field: FormField): boolean {
  return field.type === "checkbox_group" || (field.options?.length ?? 0) > 0;
}

/**
 * Validate that a value is a member of an option-backed field's allowed set
 * (enum check). `value` may be a single value (select/radio), an array (checkbox
 * group), OR a comma-separated string for a checkbox group; every element must
 * match a known option. Empty values are already short-circuited by the caller,
 * so this only sees non-empty input. bd polyglot-pdf-wpw.3.
 *
 * Both option shapes are handled (see optionValue): handling only `.value` would
 * build an all-`undefined` allowed set for plain-string schemas and REJECT every
 * valid value (Codex PR #145).
 *
 * Comma-separated checkbox values: the backend prompt
 * (`backend/config.py`: "Multiple checkboxes: comma-separated exact values")
 * tells the model to send a checkbox group as a single comma-joined string, e.g.
 * "Fears/Phobias/Worries, Family Concerns". For a checkbox-group field we split
 * that into members before checking, so a backend-blessed multi-checkbox answer
 * is not rejected as one giant non-matching candidate (Codex PR #145 round 2).
 * Option values in these schemas use "/" as an internal separator, never ",",
 * so comma is an unambiguous delimiter.
 */
function validateOptionMembership(field: FormField, value: any): string | null {
  const allowed = new Set(
    (field.options ?? [])
      .map((opt) => optionValue(opt))
      .filter((v): v is string => v !== undefined)
  );

  const isCheckboxGroup =
    field.type === "checkbox_group" ||
    (field.type === "checkbox" && isCheckboxGroupField(field));

  // A single-choice field (select/radio) cannot take an array. An empty array in
  // particular would make the membership loop below vacuously pass, letting a blank
  // choice land as a non-empty object that handleConfirmFieldRequest then treats as
  // confirmable (Codex PR #145 round 3). Reject any array for a single-choice field.
  if (!isCheckboxGroup && Array.isArray(value)) {
    return `${field.name} must be one of the available options`;
  }

  let values: any[];
  if (Array.isArray(value)) {
    values = value;
  } else if (isCheckboxGroup && typeof value === "string" && value.includes(",")) {
    values = value.split(",").map((s) => s.trim());
  } else {
    values = [value];
  }

  for (const v of values) {
    if (v === null || v === undefined || v === "") {
      continue; // skip empty members of a group; presence is a required-check concern
    }
    if (!allowed.has(String(v))) {
      return `${field.name} must be one of the available options`;
    }
  }

  return null;
}

/**
 * Validate number values
 */
function validateNumberValue(field: FormField, value: any, rules: ValidationRules): string | null {
  const numValue = typeof value === "number" ? value : parseFloat(value);

  if (isNaN(numValue)) {
    return `${field.name} must be a valid number`;
  }

  // Min value
  if (rules.min !== undefined && numValue < rules.min) {
    return `${field.name} must be at least ${rules.min}`;
  }

  // Max value
  if (rules.max !== undefined && numValue > rules.max) {
    return `${field.name} must be at most ${rules.max}`;
  }

  return null;
}

/**
 * Validate date values
 */
function validateDateValue(field: FormField, value: string, rules: ValidationRules): string | null {
  // Basic date format check
  const dateValue = new Date(value);
  if (isNaN(dateValue.getTime())) {
    return `${field.name} must be a valid date`;
  }

  // Date constraints
  if (rules.date_constraint) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    switch (rules.date_constraint) {
      case "past_only":
        if (dateValue > today) {
          return `${field.name} must be in the past`;
        }
        break;

      case "future_only":
        if (dateValue < today) {
          return `${field.name} must be in the future`;
        }
        break;

      case "within_5_years":
        const fiveYearsAgo = new Date(today);
        fiveYearsAgo.setFullYear(today.getFullYear() - 5);
        const fiveYearsFromNow = new Date(today);
        fiveYearsFromNow.setFullYear(today.getFullYear() + 5);

        if (dateValue < fiveYearsAgo || dateValue > fiveYearsFromNow) {
          return `${field.name} must be within 5 years of today`;
        }
        break;
    }
  }

  // Min date. Prefer the canonical field.min_date; fall back to a top-level
  // min folded into the rules (Codex PR #145 round 2): some date fields carry
  // their bounds as top-level min/max string dates (e.g. adult_intake `dob`:
  // min "1900-01-01", max "2007-10-13") with NO min_date/max_date, so without
  // this an out-of-range AI-applied DOB would pass. rules.min/max may be a
  // number (numeric fields) -- guard to strings/date-likes only.
  const minDateSource = field.min_date ?? asDateBound(rules.min);
  if (minDateSource) {
    const minDate = new Date(minDateSource);
    if (!isNaN(minDate.getTime()) && dateValue < minDate) {
      return `${field.name} must be on or after ${formatDate(minDate)}`;
    }
  }

  // Max date (same fallback to a top-level max).
  const maxDateSource = field.max_date ?? asDateBound(rules.max);
  if (maxDateSource) {
    const maxDate = new Date(maxDateSource);
    if (!isNaN(maxDate.getTime()) && dateValue > maxDate) {
      return `${field.name} must be on or before ${formatDate(maxDate)}`;
    }
  }

  return null;
}

/**
 * Coerce a rules.min/max bound to a date-parseable value for date fields. A
 * date field's bound is a string like "1900-01-01"; a numeric field's min/max is
 * a number (and would never reach validateDateValue). Returns undefined for a
 * non-string so a stray numeric bound is ignored rather than mis-parsed.
 */
function asDateBound(bound: number | string | undefined): string | undefined {
  return typeof bound === "string" ? bound : undefined;
}

/**
 * Validate common format presets
 */
function validateFormatPreset(
  field: FormField,
  value: string,
  preset: "ssn" | "a_number" | "phone" | "email" | "zip" | "uscis_account"
): string | null {
  switch (preset) {
    case "ssn":
      // SSN: XXX-XX-XXXX or XXXXXXXXX
      if (!/^\d{3}-?\d{2}-?\d{4}$/.test(value)) {
        return `${field.name} must be a valid SSN (XXX-XX-XXXX)`;
      }
      break;

    case "a_number":
      // A-Number canonical stored form is bare digits (7-9); the "A" prefix and
      // any separators are stripped by normalizeFieldValue before we get here, so
      // validate the digits (matches backend pattern ^\d{7,9}$). bd 0zr.
      if (!/^\d{7,9}$/.test(value)) {
        return `${field.name} must be a valid A-Number (7-9 digits)`;
      }
      break;

    case "uscis_account":
      // USCIS online account number is exactly 12 digits; punctuation (commas/"$"
      // from speech-to-text) is stripped by normalizeFieldValue before we get here
      // (bd polyglot-pdf-jnjj.40).
      if (!/^\d{12}$/.test(value)) {
        return `${field.name} must be a 12-digit USCIS online account number`;
      }
      break;

    case "phone":
      // Phone: Various formats allowed
      const digitsOnly = value.replace(/\D/g, "");
      if (digitsOnly.length < 10 || digitsOnly.length > 11) {
        return `${field.name} must be a valid phone number`;
      }
      break;

    case "email":
      // Email: Basic validation
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
        return `${field.name} must be a valid email address`;
      }
      break;

    case "zip":
      // ZIP: XXXXX or XXXXX-XXXX
      if (!/^\d{5}(-\d{4})?$/.test(value)) {
        return `${field.name} must be a valid ZIP code (XXXXX or XXXXX-XXXX)`;
      }
      break;
  }

  return null;
}

/**
 * Format date for display
 */
function formatDate(date: Date): string {
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

// The operators evaluateAtomicCondition handles. An operator outside this set
// anywhere in a condition makes the WHOLE condition unintelligible, and
// shouldShowField/isFieldRequired fall back to the field's static state --
// preserving the pre-composite behavior where a single unknown operator fell
// through to `!field.hidden` (fail-open; mirrors the editor evaluator).
const KNOWN_OPERATORS = new Set([
  "equals", "not_equals", "contains", "greater_than", "less_than",
  "is_checked", "is_empty", "is_not_empty", "in", "not_in",
  "includes", "not_includes",
]);

function conditionHasUnknownOperator(group: CompositeCondition): boolean {
  return [group.all_of, group.any_of, group.none_of].some(
    (bucket) => bucket?.some((atom) => !KNOWN_OPERATORS.has(atom.operator)),
  );
}

/**
 * Evaluate ONE atomic condition against the current values (bd h76m.8: the
 * leaf evaluator the composite buckets AND the legacy one-atom path share).
 * The semantics of every pre-composite operator are byte-identical to the old
 * single-condition shouldShowField switch -- pinned by the v0 vectors in
 * shared/conditional-vectors.json. Exported for conditionalFieldCheck, which
 * must identify WHICH atom of a composite is actually blocking a field to
 * phrase the voice explanation correctly (fresh-eyes round 2).
 */
export function evaluateAtomicCondition(
  condition: AtomicCondition,
  fieldValues: Record<string, any>,
  fields?: FormField[],
): boolean {
  // Bug Fix: Unwrap FieldValue object before comparing
  const triggerValue = unwrapFieldValue(fieldValues[condition.field]);

  // A v2 checkbox_group's selected set is ALWAYS a string[] by the time it
  // reaches the evaluator: the voice-AI comma-string is converted to an array at
  // the single ingress boundary (applyAiValueWithValidation) BEFORE storage, so
  // the evaluator never sees a comma-joined group value. Membership operators
  // (includes/not_includes) test that array. A plain scalar (radio/select/text)
  // is not a set -> null.
  //
  // The vq4m equals-means-membership hack + the comma-split + the group_kind
  // gate were DELETED at the P6.2 strictness flip (bd h76m.16): v2 expresses
  // membership with includes/not_includes, and equals/not_equals are pure scalar
  // comparisons (the backend rejects equals-on-a-checkbox_group at parse).
  const selectedSet = Array.isArray(triggerValue)
    ? triggerValue.map((v) => String(v))
    : null;

  // v2 membership: is the named option slug in the group's selected set? A
  // single selection may arrive as a bare scalar (voice path, one box) --
  // compare by string identity there; an empty/absent selection includes
  // nothing.
  const membershipIncludes = (): boolean => {
    if (selectedSet) {
      return selectedSet.includes(String(condition.value));
    }
    if (triggerValue === null || triggerValue === undefined || triggerValue === "") {
      return false;
    }
    return String(triggerValue) === String(condition.value);
  };

  switch (condition.operator) {
    case "equals":
      return triggerValue === condition.value;

    case "not_equals":
      return triggerValue !== condition.value;

    case "contains":
      // Handle checkbox groups (arrays) - check if specific option is selected.
      // Compare as strings: the array is string[] and show_if.value is a
      // string|number|boolean union, so coerce the needle to string to match.
      if (Array.isArray(triggerValue)) {
        return triggerValue.includes(String(condition.value));
      }
      // Handle text fields - substring matching
      return String(triggerValue).includes(String(condition.value));

    case "greater_than":
      return Number(triggerValue) > Number(condition.value);

    case "less_than":
      return Number(triggerValue) < Number(condition.value);

    case "is_checked":
      // Handle both single checkboxes (boolean) and checkbox groups (arrays)
      if (Array.isArray(triggerValue)) {
        return triggerValue.length > 0; // Any option selected
      }
      return triggerValue === true;

    case "is_empty":
      // A checkbox-group value is an array: an empty selection ([]) IS empty.
      // Without this branch an [] fell through to the scalar checks (an array is
      // not null/undefined/""), inverting the semantics (bd polyglot-pdf-rigd).
      if (Array.isArray(triggerValue)) {
        return triggerValue.length === 0;
      }
      return triggerValue === null || triggerValue === undefined || triggerValue === "";

    case "is_not_empty":
      if (Array.isArray(triggerValue)) {
        return triggerValue.length > 0;
      }
      return triggerValue !== null && triggerValue !== undefined && triggerValue !== "";

    case "in":
      // Membership compared as strings: the value list is a mixed
      // string|number|boolean array and triggerValue is a different union, so
      // normalize both sides to string for a stable comparison.
      if (Array.isArray(condition.value)) {
        return condition.value.map(String).includes(String(triggerValue));
      }
      return false;

    case "not_in":
      if (Array.isArray(condition.value)) {
        return !condition.value.map(String).includes(String(triggerValue));
      }
      return false;

    case "includes":
      return membershipIncludes();

    case "not_includes":
      return !membershipIncludes();

    default:
      // Unreachable: callers gate on KNOWN_OPERATORS first. Fail open.
      return true;
  }
}

/**
 * Evaluate a canonical composite condition (bd h76m.8): ALL of all_of hold,
 * AND at least one of any_of holds (when present), AND none of none_of hold.
 * An omitted bucket is vacuously satisfied.
 */
function evaluateConditionGroup(
  group: CompositeCondition,
  fieldValues: Record<string, any>,
  fields?: FormField[],
): boolean {
  if (
    group.all_of &&
    !group.all_of.every((c) => evaluateAtomicCondition(c, fieldValues, fields))
  ) {
    return false;
  }
  if (
    group.any_of &&
    group.any_of.length > 0 &&
    !group.any_of.some((c) => evaluateAtomicCondition(c, fieldValues, fields))
  ) {
    return false;
  }
  if (
    group.none_of &&
    group.none_of.some((c) => evaluateAtomicCondition(c, fieldValues, fields))
  ) {
    return false;
  }
  return true;
}

/**
 * Check if a field should be shown based on conditional logic
 *
 * Since bd h76m.8 the condition is consumed through normalizeToComposite, so
 * a legacy single condition and a v2 {all_of/any_of/none_of} group evaluate
 * through ONE path. Absent/malformed conditions and conditions carrying an
 * unknown operator fall back to the field's static hidden state (fail-open,
 * unchanged from the pre-composite behavior).
 *
 * @param field - The field to check
 * @param fieldValues - Current form values (may contain FieldValue wrappers)
 * @returns true if field should be shown
 */
export function shouldShowField(
  field: FormField,
  fieldValues: Record<string, any>,
  fields?: FormField[],
): boolean {
  const group = normalizeToComposite(field.show_if);
  if (!group) {
    return !field.hidden; // No (or malformed) conditional logic
  }
  if (conditionHasUnknownOperator(group)) {
    return !field.hidden;
  }
  return evaluateConditionGroup(group, fieldValues, fields);
}

/**
 * Whether a field is REQUIRED right now (bd h76m.8): statically required via
 * validation.required, or dynamically via a satisfied require_if condition
 * (same legacy-or-composite shape as show_if). Fail-open here means NOT
 * required -- a malformed/unknown-operator require_if never blocks the user.
 */
export function isFieldRequired(
  field: FormField,
  fieldValues: Record<string, any>,
  fields?: FormField[],
): boolean {
  if (field.validation?.required) {
    return true;
  }
  const group = normalizeToComposite(field.require_if);
  if (!group || conditionHasUnknownOperator(group)) {
    return false;
  }
  return evaluateConditionGroup(group, fieldValues, fields);
}

/**
 * Check if a field should be read-only based on conditional logic
 *
 * @param field - The field to check
 * @param fieldValues - Current form values
 * @returns true if field should be read-only
 */
export function isFieldReadOnly(field: FormField, fieldValues: Record<string, any>): boolean {
  // Check default read_only state
  if (field.read_only) {
    // Check if any conditional control unlocks this field
    // (This would require checking all fields with controls_fields)
    // For now, just return the default state
    return true;
  }

  return false;
}
