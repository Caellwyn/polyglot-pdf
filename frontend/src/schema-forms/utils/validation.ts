/**
 * Validation utilities for schema-based forms
 *
 * Validates field values against ValidationRules from schema
 */

import type { FormField, ValidationRules } from "../types/schema";
import { unwrapFieldValue } from "./fieldValue";

/**
 * Normalize a raw input value to the field's canonical stored form, keyed on
 * format_preset. Mirrors the backend normalize_value() in
 * backend/utils/field_validator.py so client and server agree on what gets
 * stored (bd polyglot-pdf-0zr).
 *
 * a_number: an Alien Registration Number is spoken/written as "A" + 7-9 digits
 * (often with dashes/spaces), but the PDF comb field stores bare digits. Strip a
 * leading A/a and all non-digits. Non-a_number fields and non-string values pass
 * through unchanged.
 */
export function normalizeFieldValue(field: FormField, value: any): any {
  const preset = field.validation?.format_preset;
  if (preset === "a_number" && typeof value === "string") {
    let stripped = value.trim();
    if (stripped[0] === "A" || stripped[0] === "a") {
      stripped = stripped.slice(1);
    }
    return stripped.replace(/\D/g, "");
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
  // CRITICAL SCOPING (Codex PR #145 round 3): a STANDALONE checkbox (type
  // "checkbox" WITHOUT group_kind "checkbox") is a BOOLEAN field -- the backend
  // contract is "For checkbox: boolean" (config.py). Its `options` array describes
  // the single PDF widget, not an enum of allowed values, so Gemini sends
  // true/false, NOT an option value. Running the enum check on it would compare
  // "true" against an option like "P2_checkbox3[0]" and reject every valid fill.
  // So the enum gate applies ONLY to select/radio and checkbox GROUPS; a standalone
  // checkbox skips it (its boolean is validated structurally, nothing to enum).
  if (!normalizedEmpty && field.options && field.options.length > 0 && isStringEnumField(field)) {
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
 * check applies. True for `select`, `radio`, and checkbox GROUPS (group_kind
 * "checkbox"). FALSE for a STANDALONE checkbox (type "checkbox" without a group),
 * whose value is a BOOLEAN per the backend contract ("For checkbox: boolean"),
 * even though it carries an `options` array describing its single widget. Running
 * the enum check on a standalone checkbox would reject every valid true/false fill
 * (Codex PR #145 round 3).
 */
function isStringEnumField(field: FormField): boolean {
  if (field.type === "select" || field.type === "radio") return true;
  if (field.type === "checkbox" && field.group_kind === "checkbox") return true;
  return false;
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

  const isCheckboxGroup = field.group_kind === "checkbox";

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
  preset: "ssn" | "a_number" | "phone" | "email" | "zip"
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

/**
 * Check if a field should be shown based on conditional logic
 *
 * @param field - The field to check
 * @param fieldValues - Current form values (may contain FieldValue wrappers)
 * @returns true if field should be shown
 */
export function shouldShowField(field: FormField, fieldValues: Record<string, any>): boolean {
  if (!field.show_if) {
    return !field.hidden; // No conditional logic, use default hidden state
  }

  // Bug Fix: Unwrap FieldValue object before comparing
  const triggerValue = unwrapFieldValue(fieldValues[field.show_if.field]);

  switch (field.show_if.operator) {
    case "equals":
      return triggerValue === field.show_if.value;

    case "not_equals":
      return triggerValue !== field.show_if.value;

    case "contains":
      // Handle checkbox groups (arrays) - check if specific option is selected
      if (Array.isArray(triggerValue)) {
        return triggerValue.includes(field.show_if.value);
      }
      // Handle text fields - substring matching
      return String(triggerValue).includes(String(field.show_if.value));

    case "greater_than":
      return Number(triggerValue) > Number(field.show_if.value);

    case "less_than":
      return Number(triggerValue) < Number(field.show_if.value);

    case "is_checked":
      // Handle both single checkboxes (boolean) and checkbox groups (arrays)
      if (Array.isArray(triggerValue)) {
        return triggerValue.length > 0; // Any option selected
      }
      return triggerValue === true;

    case "is_empty":
      return triggerValue === null || triggerValue === undefined || triggerValue === "";

    case "is_not_empty":
      return triggerValue !== null && triggerValue !== undefined && triggerValue !== "";

    case "in":
      if (Array.isArray(field.show_if.value)) {
        return field.show_if.value.includes(triggerValue);
      }
      return false;

    case "not_in":
      if (Array.isArray(field.show_if.value)) {
        return !field.show_if.value.includes(triggerValue);
      }
      return false;

    default:
      return !field.hidden;
  }
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
