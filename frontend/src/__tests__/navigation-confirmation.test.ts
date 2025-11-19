/**
 * Unit tests for computeNextField with confirmation prioritization
 *
 * Tests that the navigation logic correctly prioritizes:
 * 1. Filled but UNCONFIRMED fields (must confirm before moving on)
 * 2. Empty fields
 * 3. Skips confirmed fields
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { computeNextField } from '../navigation';
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState';
import type { FormSchema, FormField } from '../schema-forms/types/schema';

// Helper to create minimal schema
function createTestSchema(fields: Partial<FormField>[]): FormSchema {
  return {
    source: 'web',
    form_metadata: {
      title: 'Test Form',
      version: '1.0.0',
      language: 'en',
    },
    sections: [
      {
        id: 'section1',
        label: 'Section 1',
        order: 1,
        fields: fields.map(f => f.id || ''),
      },
    ],
    fields: fields.map((f, idx) => ({
      id: f.id || `field${idx}`,
      name: f.name || `Field ${idx}`,
      spoken_name: f.spoken_name || f.name || `Field ${idx}`,
      type: f.type || 'text',
      section_id: 'section1',
      validation: f.validation || {},
      ...f,
    })) as FormField[],
  };
}

describe('computeNextField with confirmation prioritization', () => {
  beforeEach(() => {
    // Clear sessionStorage before each test to prevent state leakage
    sessionStorage.clear();
  });

  it('should prioritize filled but UNCONFIRMED field over empty fields', () => {
    // Setup: field1 = confirmed, field2 = filled but unconfirmed, field3 = empty
    const schema = createTestSchema([
      { id: 'firstName', name: 'First Name' },
      { id: 'lastName', name: 'Last Name' },
      { id: 'email', name: 'Email' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    // field1: filled and confirmed
    let updatedState = SchemaFormStateManager.updateField(state, 'firstName', 'John', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    // field2: filled but NOT confirmed
    updatedState = SchemaFormStateManager.updateField(updatedState, 'lastName', 'Doe', {
      confirmed: false,
    });

    // field3: empty (no value)

    const nextField = computeNextField(updatedState);

    // Should return field2 (filled but unconfirmed) NOT field3 (empty)
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('lastName');
  });

  it('should return empty field when all filled fields are confirmed', () => {
    // Setup: field1 = confirmed, field2 = confirmed, field3 = empty
    const schema = createTestSchema([
      { id: 'firstName', name: 'First Name' },
      { id: 'lastName', name: 'Last Name' },
      { id: 'email', name: 'Email' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    // field1: filled and confirmed
    let updatedState = SchemaFormStateManager.updateField(state, 'firstName', 'John', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    // field2: filled and confirmed
    updatedState = SchemaFormStateManager.updateField(updatedState, 'lastName', 'Doe', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    // field3: empty

    const nextField = computeNextField(updatedState);

    // Should return field3 (empty)
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('email');
  });

  it('should return null when all fields are confirmed', () => {
    const schema = createTestSchema([
      { id: 'firstName', name: 'First Name' },
      { id: 'lastName', name: 'Last Name' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    let updatedState = SchemaFormStateManager.updateField(state, 'firstName', 'John', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    updatedState = SchemaFormStateManager.updateField(updatedState, 'lastName', 'Doe', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    const nextField = computeNextField(updatedState);

    // All fields confirmed - should return null
    expect(nextField).toBeNull();
  });

  it('should skip confirmed fields when returning empty field', () => {
    // Setup: field1 = confirmed, field2 = empty but confirmed (edge case), field3 = empty
    const schema = createTestSchema([
      { id: 'firstName', name: 'First Name' },
      { id: 'middleName', name: 'Middle Name' },
      { id: 'lastName', name: 'Last Name' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    // field1: filled and confirmed
    let updatedState = SchemaFormStateManager.updateField(state, 'firstName', 'John', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    // field2: Set to empty string and mark confirmed (optional field scenario)
    updatedState = SchemaFormStateManager.updateField(updatedState, 'middleName', '', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    // field3: empty

    const nextField = computeNextField(updatedState);

    // Should return field3 (lastName), skipping confirmed fields (firstName and middleName)
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('lastName');
  });

  it('should return first unconfirmed field when multiple fields are unconfirmed', () => {
    const schema = createTestSchema([
      { id: 'field1', name: 'Field 1' },
      { id: 'field2', name: 'Field 2' },
      { id: 'field3', name: 'Field 3' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    // field1: filled but NOT confirmed
    let updatedState = SchemaFormStateManager.updateField(state, 'field1', 'value1', {
      confirmed: false,
    });

    // field2: filled but NOT confirmed
    updatedState = SchemaFormStateManager.updateField(updatedState, 'field2', 'value2', {
      confirmed: false,
    });

    // field3: empty

    const nextField = computeNextField(updatedState);

    // Should return field1 (first unconfirmed)
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('field1');
  });

  it('should respect skipConfirmed=false option', () => {
    const schema = createTestSchema([
      { id: 'firstName', name: 'First Name' },
      { id: 'lastName', name: 'Last Name' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    let updatedState = SchemaFormStateManager.updateField(state, 'firstName', 'John', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    const nextField = computeNextField(updatedState, { skipConfirmed: false });

    // With skipConfirmed=false, should return firstName even though it's confirmed
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('firstName');
  });

  it('should work with manual_edit confirmation method', () => {
    const schema = createTestSchema([
      { id: 'firstName', name: 'First Name' },
      { id: 'lastName', name: 'Last Name' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    // Manual edit (user typed)
    const updatedState = SchemaFormStateManager.updateField(state, 'firstName', 'John', {
      confirmed: true,
      confirmationMethod: 'manual_edit',
    });

    const nextField = computeNextField(updatedState);

    // Should skip firstName (manually confirmed) and return lastName
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('lastName');
  });
});
