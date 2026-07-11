/**
 * Utility functions for handling FieldValue wrappers
 *
 * Bug Fix: Manual Entry Shows [object Object]
 * Root Cause: FieldValue wrapper objects are displayed directly instead of unwrapped
 * Solution: Unwrap FieldValue objects to get primitive values for display
 */

import type { FieldValue } from '../types/schema';

/**
 * Whether a FieldValue entry actually carries an answer (not a hollow
 * placeholder). Empty string, null/undefined value, and an empty array all count
 * as "no answer".
 */
function entryHasValue(entry: FieldValue | undefined): boolean {
  if (!entry) return false;
  const v = entry.value as unknown;
  if (v === null || v === undefined || v === '') return false;
  if (Array.isArray(v) && v.length === 0) return false;
  return true;
}

/**
 * Read a field's FieldValue entry with the checkbox-group `[]`-alias
 * fallback: a group's value may sit under the bracketed OR unbracketed key
 * variant (Gemini drops/adds the bracket, bd polyglot-pdf-5k52), so an
 * exact-key-only read silently misses a real entry. Same convention as the
 * confirm/update/skip/validator paths; use this instead of a bare
 * `fieldValues[fieldId]` wherever a miss would change behavior.
 *
 * Precedence (bd polyglot-pdf-luju nit 2): a MEANINGFUL exact-key entry wins;
 * otherwise a meaningful alias-key entry wins. A plain `??` would stop at a
 * HOLLOW exact-key entry (e.g. `{value: null, confirmed: false}`) and shadow a
 * real confirmed answer sitting under the alias key -- so hollow exact-key
 * entries fall through to the alias. Only when neither key has a real answer do
 * we return the exact-key entry (else the alias) so a caller inspecting flags on
 * an unanswered field still gets a stable entry.
 */
export function readFieldEntryWithAlias(
  fieldValues: Record<string, FieldValue>,
  fieldId: string
): FieldValue | undefined {
  const aliasKey = fieldId.endsWith('[]') ? fieldId.slice(0, -2) : fieldId + '[]';
  const exact = fieldValues[fieldId];
  const alias = fieldValues[aliasKey];
  if (entryHasValue(exact)) return exact;
  if (entryHasValue(alias)) return alias;
  return exact ?? alias;
}

/**
 * Type guard to check if a value is a FieldValue object
 */
export function isFieldValue(value: any): value is FieldValue {
  return (
    value !== null &&
    typeof value === 'object' &&
    'value' in value &&
    !Array.isArray(value)
  );
}

/**
 * Unwrap a FieldValue object to get the primitive value
 *
 * @param value - Primitive value or FieldValue wrapper
 * @returns Primitive value (string, boolean, string[], null)
 *
 * @example
 * unwrapFieldValue('hello') // => 'hello'
 * unwrapFieldValue({ value: 'hello', confirmed: true }) // => 'hello'
 * unwrapFieldValue({ value: ['Male'], confirmed: true }) // => ['Male'] (checkbox group)
 * unwrapFieldValue({ value: null }) // => null
 * unwrapFieldValue(null) // => null
 */
export function unwrapFieldValue(value: any): string | boolean | string[] | null {
  if (isFieldValue(value)) {
    return value.value;
  }
  return value;
}

/**
 * Unwrap and convert to string for text inputs
 * Handles null/undefined by returning empty string
 *
 * @param value - Any value (primitive, FieldValue, null, undefined)
 * @returns String value suitable for text input
 *
 * @example
 * unwrapToString('hello') // => 'hello'
 * unwrapToString({ value: 'world' }) // => 'world'
 * unwrapToString(null) // => ''
 * unwrapToString(undefined) // => ''
 * unwrapToString({ value: true }) // => 'true'
 */
export function unwrapToString(value: any): string {
  const unwrapped = unwrapFieldValue(value);

  if (unwrapped === null || unwrapped === undefined) {
    return '';
  }

  return String(unwrapped);
}

/**
 * Unwrap and convert to boolean for checkbox inputs
 *
 * @param value - Any value (primitive, FieldValue, null, undefined)
 * @returns Boolean value
 *
 * @example
 * unwrapToBoolean(true) // => true
 * unwrapToBoolean({ value: true }) // => true
 * unwrapToBoolean('true') // => true
 * unwrapToBoolean(null) // => false
 */
export function unwrapToBoolean(value: any): boolean {
  const unwrapped = unwrapFieldValue(value);

  if (unwrapped === null || unwrapped === undefined) {
    return false;
  }

  if (typeof unwrapped === 'boolean') {
    return unwrapped;
  }

  // Handle string/number representations. Coerce to string so a numeric 1
  // (which can arrive since the input is `any`) still maps to true, without a
  // `=== 1` comparison the unwrap return type rules out as unreachable.
  if (typeof unwrapped === 'string' || typeof unwrapped === 'number') {
    return String(unwrapped) === 'true' || String(unwrapped) === '1';
  }
  return false;
}
