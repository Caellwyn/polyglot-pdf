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
  if (!field.validation) {
    return null; // No validation rules
  }

  // Bug Fix: Unwrap FieldValue object before validation
  // Normalize to the canonical form first (e.g. strip an A-Number's "A" prefix)
  // so correct-but-differently-formatted input validates (bd polyglot-pdf-0zr).
  const rawValue = unwrapFieldValue(value);
  const actualValue = normalizeFieldValue(field, rawValue);

  const rules = field.validation;

  const rawHadContent = rawValue !== null && rawValue !== undefined && String(rawValue).trim() !== "";
  const normalizedEmpty = actualValue === null || actualValue === undefined || actualValue === "";

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

  if (field.type === "date") {
    return validateDateValue(field, String(actualValue), rules);
  }

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

  // Min date
  if (field.min_date) {
    const minDate = new Date(field.min_date);
    if (dateValue < minDate) {
      return `${field.name} must be on or after ${formatDate(minDate)}`;
    }
  }

  // Max date
  if (field.max_date) {
    const maxDate = new Date(field.max_date);
    if (dateValue > maxDate) {
      return `${field.name} must be on or before ${formatDate(maxDate)}`;
    }
  }

  return null;
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
