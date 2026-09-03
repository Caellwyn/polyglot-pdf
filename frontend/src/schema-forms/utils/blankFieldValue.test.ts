/**
 * Whitespace-only input is neither a value nor a skip (bd polyglot-pdf-5ovod).
 *
 * Leaving a field blank on a legal intake draft is a real decision: it has to be
 * said out loud or done with the skip control. Typing spaces is not a decision,
 * and it used to read as one.
 *
 * THE BUG THIS PINS. Five separate predicates each answered "is this field
 * answered?", and every copy tested `=== ''` without trimming. So a field
 * containing only spaces:
 *   - satisfied the section COMPLETION GATE (isSectionValid),
 *   - passed the REQUIRED check (validateField),
 *   - hid its own SKIP affordance (SectionRenderer),
 *   - was CONFIRMABLE (hasUsableValue),
 *   - and was offered to CONFIRM rather than to FILL (computeNextField),
 * while printing blank on the PDF -- and the backend never heard about it at
 * all, because the notify path (fieldManager) DOES trim. Client and backend
 * disagreed about whether the field existed.
 *
 * The first half of this file pins the shared helper's behaviour. The second
 * half pins THE SET: every "is answered" predicate agrees with it. That is the
 * part that matters -- five hand-written copies is exactly how they drifted in
 * the first place, and a sixth would drift the same way (CLAUDE.md scar #8).
 */

import { describe, it, expect } from 'vitest';
import { isBlankFieldValue } from './fieldValue';
import { validateField } from './validation';
import { SchemaFormStateManager } from '../state/schemaFormState';
import { computeNextField } from '../../navigation';
import type { FormField, FormSchema } from '../types/schema';

// ASCII source only (CLAUDE.md scar #6), so the non-breaking space is written as
// an escape. It belongs in this list deliberately: a user pasting from a Word
// document brings U+00A0 with them, and JS String.trim() DOES strip it, so the
// helper must agree -- otherwise a pasted 'blank' would read as an answer.
const WHITESPACE_FORMS = ['   ', '\t', '\n', '\r\n', ' \t\n ', '\u00a0'];

describe('isBlankFieldValue', () => {
  it('treats every shape of whitespace-only string as blank', () => {
    for (const w of WHITESPACE_FORMS) {
      expect(isBlankFieldValue(w), JSON.stringify(w)).toBe(true);
    }
  });

  it('treats the genuinely absent values as blank', () => {
    expect(isBlankFieldValue(null)).toBe(true);
    expect(isBlankFieldValue(undefined)).toBe(true);
    expect(isBlankFieldValue('')).toBe(true);
    expect(isBlankFieldValue([])).toBe(true);
  });

  it('does NOT treat a real answer as blank, including falsy ones', () => {
    // A checkbox answered "no" and a numeric zero are REAL answers. An
    // over-eager truthiness check would erase them, which is a data-loss bug
    // rather than a cosmetic one.
    expect(isBlankFieldValue(false)).toBe(false);
    expect(isBlankFieldValue(0)).toBe(false);
    expect(isBlankFieldValue('0')).toBe(false);
    expect(isBlankFieldValue('a')).toBe(false);
    expect(isBlankFieldValue(' x ')).toBe(false);
    expect(isBlankFieldValue(['a'])).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// THE SET: every "is this field answered?" predicate must agree.
// ---------------------------------------------------------------------------

function textField(over: Partial<FormField> = {}): FormField {
  return {
    id: 'f1',
    name: 'Family Name',
    type: 'text',
    validation: { required: true },
    ...over,
  } as FormField;
}

function schemaWith(field: FormField): FormSchema {
  return {
    source: 'web',
    form_metadata: { title: 'T', version: '1', language: 'en' },
    sections: [{ id: 's1', label: 'S1', order: 1, fields: [field.id] }],
    fields: [field],
  } as unknown as FormSchema;
}

describe('whitespace is not an answer, at every predicate', () => {
  it('the COMPLETION GATE rejects a required field holding only spaces', () => {
    const field = textField();
    const state = {
      schema: schemaWith(field),
      fieldValues: { f1: { value: '   ', confirmed: true } },
      validationErrors: {},
    } as any;

    expect(SchemaFormStateManager.isSectionValid(state, 's1')).toBe(false);
  });

  it('the REQUIRED check rejects a required field holding only spaces', () => {
    expect(validateField(textField(), '   ')).not.toBeNull();
  });

  it('NAVIGATION offers a space-filled field to FILL, not to confirm', () => {
    const field = textField();
    const state = {
      schema: schemaWith(field),
      fieldValues: { f1: { value: '   ' } },
      validationErrors: {},
    } as any;

    // computeNextField returns the FormField itself. The field must still be
    // offered -- a whitespace field is unanswered, so navigation must come back
    // to it rather than treating it as done and moving on.
    expect(computeNextField(state)?.id).toBe('f1');
  });

  it('an OPTIONAL field holding only spaces is still not answered', () => {
    // The optional-field carve-out is for a genuine '' meaning "does not
    // apply". Spaces must not inherit it.
    const field = textField({ validation: { required: false } });
    const state = {
      schema: schemaWith(field),
      fieldValues: { f1: { value: '   ' } },
      validationErrors: {},
    } as any;

    expect(computeNextField(state)?.id).toBe('f1');
  });
});

// ---------------------------------------------------------------------------
// The path that must KEEP working (bd polyglot-pdf-6oe6 / w3ic).
// ---------------------------------------------------------------------------

describe('the deliberate "does not apply" empty value still works', () => {
  it('an OPTIONAL field with a confirmed empty string stays confirmed', () => {
    // '' on an optional field is a REAL verbal answer -- the SI's
    // field-does-not-apply flow stores it and confirms it. If this bead's fix
    // had normalised whitespace to '' (or treated '' as unanswerable), this
    // path would break and the model would re-ask a question the user already
    // answered.
    const field = textField({ validation: { required: false } });
    const state = {
      schema: schemaWith(field),
      fieldValues: { f1: { value: '', confirmed: true } },
      validationErrors: {},
    } as any;

    // Confirmed + optional-empty is DONE: navigation must not re-offer it.
    expect(computeNextField(state)?.id).not.toBe('f1');
  });

  it('an optional empty string does not block the completion gate', () => {
    const field = textField({ validation: { required: false } });
    const state = {
      schema: schemaWith(field),
      fieldValues: { f1: { value: '', confirmed: true } },
      validationErrors: {},
    } as any;

    expect(SchemaFormStateManager.isSectionValid(state, 's1')).toBe(true);
  });
});
