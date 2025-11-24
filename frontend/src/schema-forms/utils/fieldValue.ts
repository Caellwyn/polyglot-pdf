/**
 * Utility functions for handling FieldValue wrappers
 *
 * Bug Fix: Manual Entry Shows [object Object]
 * Root Cause: FieldValue wrapper objects are displayed directly instead of unwrapped
 * Solution: Unwrap FieldValue objects to get primitive values for display
 */

import type { FieldValue } from '../types/schema';

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

  // Handle string representations
  return unwrapped === 'true' || unwrapped === '1' || unwrapped === 1;
}
