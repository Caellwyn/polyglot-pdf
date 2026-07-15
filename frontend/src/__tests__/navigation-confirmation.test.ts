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

// Counter for unique form numbers in tests
let testFormCounter = 0;

// Helper to create minimal schema
function createTestSchema(fields: Partial<FormField>[]): FormSchema {
  testFormCounter++;
  return {
    source: 'web',
    form_metadata: {
      title: 'Test Form',
      form_number: `TEST-${testFormCounter}`, // Unique form number for each test
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

  // bd polyglot-pdf-6oe6: an OPTIONAL field the AI filled with '' (the
  // field-does-not-apply flow: update_form_fields with '' then confirm) but has
  // NOT yet confirmed must be offered as a filled-unconfirmed field to CONFIRM,
  // not re-offered as an empty field to FILL. This mirrors webFormConnection.ts
  // handleConfirmFieldRequest's hasUsableValue, which already treats '' as usable
  // on an optional field -- before this fix, computeNextField's Priority-1
  // has-value check (`value !== ''`) disagreed, so the field fell through to
  // Priority 2 and was offered as empty instead of as a pending confirmation.
  it('should offer an OPTIONAL field holding an unconfirmed "" value for CONFIRM, not re-fill', () => {
    const schema = createTestSchema([
      { id: 'firstName', name: 'First Name' },
      { id: 'middleName', name: 'Middle Name' }, // optional: no validation.required
      { id: 'lastName', name: 'Last Name' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    // firstName: filled and confirmed -- already done, should be skipped.
    let updatedState = SchemaFormStateManager.updateField(state, 'firstName', 'John', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    // middleName: the AI filled '' ("no middle name") but has NOT confirmed yet.
    updatedState = SchemaFormStateManager.updateField(updatedState, 'middleName', '', {
      confirmed: false,
    });

    // lastName: genuinely empty (no value at all).

    const nextField = computeNextField(updatedState);

    // Must return middleName (filled-unconfirmed, Priority 1) -- NOT lastName
    // (which would wrongly imply middleName is being treated as still-empty).
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('middleName');
  });

  // Contrast case: a REQUIRED field's unconfirmed '' must NOT be treated as
  // usable -- it stays a Priority-2 empty-to-fill field, exactly as before the
  // fix. This proves the fix is scoped to optional fields only.
  it('should still treat an unconfirmed "" on a REQUIRED field as empty (Priority 2), not confirmable', () => {
    const schema = createTestSchema([
      {
        id: 'ssn',
        name: 'SSN',
        validation: { required: true },
      },
      { id: 'lastName', name: 'Last Name' },
    ]);

    const state = SchemaFormStateManager.init(schema);

    // ssn: required field holding an unconfirmed '' (should NOT be confirmable).
    const updatedState = SchemaFormStateManager.updateField(state, 'ssn', '', {
      confirmed: false,
    });

    const nextField = computeNextField(updatedState);

    // Priority 1 finds nothing usable (ssn's '' is not usable since it's
    // required); Priority 2 returns the first empty field, which is ssn itself.
    expect(nextField).not.toBeNull();
    expect(nextField?.id).toBe('ssn');
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

describe('checkbox-group []-alias awareness (bd polyglot-pdf-ipw7)', () => {
  // A checkbox group's entry can sit under the bracket key VARIANT (legacy
  // persisted sessions predate the write-path normalization, bd 5k52 class).
  // The main loops, progress, and completion must read through the alias or a
  // confirmed group is re-offered forever / holds the form open.
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('does NOT offer a group confirmed under the unbracketed alias as next', async () => {
    const { isFormComplete } = await import('../navigation');
    const schema = createTestSchema([
      { id: 'race[]', name: 'Race', type: 'checkbox_group' },
      { id: 'email', name: 'Email' },
    ]);
    const state = SchemaFormStateManager.init(schema);
    // Entry lands under the ALIAS key 'race', not the schema id 'race[]'.
    const updatedState = SchemaFormStateManager.updateField(state, 'race', ['x'], {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    const nextField = computeNextField(updatedState);
    // The confirmed-under-alias group is NOT re-offered; the empty field is next.
    expect(nextField?.id).toBe('email');
    expect(isFormComplete(updatedState)).toBe(false);
  });

  it('completes the form and counts progress when a required group is confirmed under the alias', async () => {
    const { isFormComplete, getFormProgress } = await import('../navigation');
    const schema = createTestSchema([
      { id: 'race[]', name: 'Race', type: 'checkbox_group', validation: { required: true } },
    ]);
    const state = SchemaFormStateManager.init(schema);
    const updatedState = SchemaFormStateManager.updateField(state, 'race', ['x'], {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    expect(computeNextField(updatedState)).toBeNull();
    expect(isFormComplete(updatedState)).toBe(true);
    const progress = getFormProgress(updatedState);
    expect(progress.confirmed).toBe(1);
    expect(progress.requiredConfirmed).toBe(1);
  });

  it('handles the reverse split: schema id unbracketed, entry under the bracketed key', async () => {
    const { isFormComplete } = await import('../navigation');
    const schema = createTestSchema([
      { id: 'race', name: 'Race', type: 'checkbox_group' },
      { id: 'email', name: 'Email' },
    ]);
    const state = SchemaFormStateManager.init(schema);
    const updatedState = SchemaFormStateManager.updateField(state, 'race[]', ['x'], {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    expect(computeNextField(updatedState)?.id).toBe('email');
    expect(isFormComplete(updatedState)).toBe(false);
  });
});

describe('required-agnostic completion (bd polyglot-pdf-taw3)', () => {
  // The shipped regression: with the A-Number the ONLY validation.required field
  // on the I-90, confirming it (the first field) reported the whole form complete
  // via isFormComplete's old required-only short-circuit. These pin exit criterion
  // 1 WITHOUT a navigation pin -- the required-agnostic "every shown field" gate is
  // exercised directly, not masked by resolveLivePin.
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('does NOT report complete after the single REQUIRED field is confirmed (rest empty, no pin)', async () => {
    const { isFormComplete } = await import('../navigation');
    const schema = createTestSchema([
      { id: 'a_number', name: 'A-Number', validation: { required: true } },
      { id: 'family_name', name: 'Family Name' }, // optional, still empty
      { id: 'given_name', name: 'Given Name' },   // optional, still empty
    ]);
    const state = SchemaFormStateManager.init(schema);
    const updated = SchemaFormStateManager.updateField(state, 'a_number', 'A123', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });

    // pinnedFieldId defaults to null from init -- no pin confound.
    expect(updated.pinnedFieldId ?? null).toBeNull();
    // The form is NOT complete: two shown optional fields remain unconfirmed.
    expect(isFormComplete(updated)).toBe(false);
    // ...and the next unconfirmed shown field is still offered.
    expect(computeNextField(updated, { skipConfirmed: true })?.id).toBe('family_name');
  });

  it('reports complete only when every shown field is confirmed (a skipped field counts, no pin)', async () => {
    const { isFormComplete } = await import('../navigation');
    const schema = createTestSchema([
      { id: 'a_number', name: 'A-Number', validation: { required: true } },
      { id: 'family_name', name: 'Family Name' },
      { id: 'given_name', name: 'Given Name' },
    ]);
    let state = SchemaFormStateManager.init(schema);
    state = SchemaFormStateManager.updateField(state, 'a_number', 'A123', {
      confirmed: true, confirmationMethod: 'ai_voice',
    });
    state = SchemaFormStateManager.updateField(state, 'family_name', 'Doe', {
      confirmed: true, confirmationMethod: 'ai_voice',
    });
    // The last field is SKIPPED (empty value + confirmed=true, flagged for review).
    state = SchemaFormStateManager.markFieldSkipped(state, 'given_name', 'ai_voice');

    expect(state.pinnedFieldId ?? null).toBeNull();
    expect(isFormComplete(state)).toBe(true);
    expect(computeNextField(state, { skipConfirmed: true })).toBeNull();
  });
});
