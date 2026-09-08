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
import { isBlankFieldValue, isConfirmedButBlank } from './fieldValue';
import { validateField } from './validation';
import { SchemaFormStateManager } from '../state/schemaFormState';
import { computeNextField, isFormComplete } from '../../navigation';
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

describe('isConfirmedButBlank -- the NARROWER sibling', () => {
  // The distinction between the two helpers is load-bearing and easy to
  // conflate. "Is it answered?" (isBlankFieldValue) and "has it been SETTLED?"
  // (isConfirmedButBlank) differ on exactly one input: a bare ''. On an OPTIONAL
  // field a confirmed '' is the deliberate "does not apply" answer, so it must
  // still settle -- reaching for the broader helper at a settle-site breaks that
  // path, which is a mistake I made on the first attempt at the validator-window
  // fix.
  it('whitespace is blank under BOTH', () => {
    for (const w of WHITESPACE_FORMS) {
      expect(isBlankFieldValue(w), `isBlankFieldValue(${JSON.stringify(w)})`).toBe(true);
      expect(isConfirmedButBlank(w), `isConfirmedButBlank(${JSON.stringify(w)})`).toBe(true);
    }
  });

  it("they DISAGREE on a bare '' -- and that is the whole point", () => {
    expect(isBlankFieldValue('')).toBe(true);      // not an answer...
    expect(isConfirmedButBlank('')).toBe(false);   // ...but it IS a settled one
  });

  it('neither treats a real answer as blank', () => {
    for (const v of ['a', ' x ', '0']) {
      expect(isBlankFieldValue(v)).toBe(false);
      expect(isConfirmedButBlank(v)).toBe(false);
    }
  });

  it('non-strings are never "confirmed but blank"', () => {
    // A skipped field carries value:null and an empty checkbox group [] -- both
    // are settled by their own rules, not by this predicate.
    for (const v of [null, undefined, [], false, 0]) {
      expect(isConfirmedButBlank(v as unknown)).toBe(false);
    }
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
    // TWO fields, so the two priorities would return DIFFERENT answers and the
    // assertion can tell them apart. With one field they both return it, and the
    // test passes whichever loop matched -- which is how an earlier version of
    // this test let Priority 1's guard be reverted without going red.
    //
    // f1 holds whitespace; f2 is genuinely empty. Priority 1 (filled-but-
    // unconfirmed, to CONFIRM) must NOT claim f1. Priority 2 (empty, to FILL)
    // scans in order and reaches f1 first. So the field is still f1 -- but now
    // only via the loop that asks it as a QUESTION.
    const f1 = textField({ id: 'f1' });
    const f2 = textField({ id: 'f2', name: 'Given Name' });
    const state = {
      schema: {
        source: 'web',
        form_metadata: { title: 'T', version: '1', language: 'en' },
        sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1', 'f2'] }],
        fields: [f1, f2],
      },
      fieldValues: { f1: { value: '   ' }, f2: { value: '' } },
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    expect(computeNextField(state)?.id).toBe('f1');

    // The discriminator: ask with skipConfirmed=false, which SKIPS Priority 1
    // entirely (it is the confirm-sweep loop) and runs only the empty-field
    // scan. If whitespace were still counted as a value by Priority 2, f1 would
    // be passed over and f2 returned instead.
    expect(computeNextField(state, { skipConfirmed: false })?.id).toBe('f1');
  });

  it('P1 does not treat whitespace as a value to CONFIRM (distinguishes the two loops)', () => {
    // f1 whitespace, f2 a REAL unconfirmed value. If Priority 1 wrongly counted
    // f1's spaces as a value, it would return f1 (first in order) as something
    // to confirm. Correct behaviour: P1 skips f1 and returns f2, the genuinely
    // filled-but-unconfirmed field.
    const f1 = textField({ id: 'f1' });
    const f2 = textField({ id: 'f2', name: 'Given Name' });
    const state = {
      schema: {
        source: 'web',
        form_metadata: { title: 'T', version: '1', language: 'en' },
        sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1', 'f2'] }],
        fields: [f1, f2],
      },
      fieldValues: { f1: { value: '   ' }, f2: { value: 'Maria' } },
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    expect(computeNextField(state)?.id).toBe('f2');
  });

  it('a CONFIRMED whitespace field is re-offered, not lost forever', () => {
    // The nastiest shape, and the one a session saved BEFORE this fix can hold:
    // whitespace that was already confirmed. Priority 1 skips it (confirmed),
    // and Priority 2 used to skip it too (confirmed), so the field was invisible
    // to navigation entirely -- never asked again, blank on the PDF. A
    // confirmation of blankness is not a real confirmation, so it is re-offered.
    const field = textField();
    const state = {
      schema: schemaWith(field),
      fieldValues: { f1: { value: '   ', confirmed: true } },
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    expect(computeNextField(state)?.id).toBe('f1');
  });

  it('the re-offered field is ESCAPABLE -- skipping it ends the loop', () => {
    // Re-offering a confirmed-blank field is only safe if there is a way OUT.
    // markFieldSkipped writes value:null + skipped:true, which clears the
    // whitespace, so the field stops being re-offered. Without an escape this
    // arm would be an infinite re-ask, which is worse than the bug it fixes.
    let state = {
      schema: schemaWith(textField()),
      fieldValues: { f1: { value: '   ', confirmed: true } },
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    expect(computeNextField(state)?.id).toBe('f1');

    state = SchemaFormStateManager.markFieldSkipped(state, 'f1');

    expect(computeNextField(state)).toBeNull();
  });

  it('the re-offered field is ESCAPABLE -- a real answer ends the loop', () => {
    let state = {
      schema: schemaWith(textField()),
      fieldValues: { f1: { value: '   ', confirmed: true } },
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    state = SchemaFormStateManager.updateField(state, 'f1', 'Maria', { confirmed: true });

    expect(computeNextField(state)).toBeNull();
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
// The two completion gates must never contradict each other.
// ---------------------------------------------------------------------------

describe('computeNextField and isFormComplete agree', () => {
  // Stated as a PROPERTY, not one example: if navigation is still offering a
  // field, the form is not complete. Adding the confirmed-blank recovery arm to
  // computeNextField alone made these two disagree -- navigation kept asking for
  // a field while isFormComplete said done, which also FIRES THE PAID end-of-form
  // validator over a form that still has a blank field open.
  const cases: Array<[string, any, boolean]> = [
    ['confirmed whitespace (legacy pre-fix session)', { value: '   ', confirmed: true }, true],
    ['unconfirmed whitespace', { value: '   ' }, true],
    ['confirmed real value', { value: 'Maria', confirmed: true }, false],
    ['skipped field', { value: null, skipped: true, confirmed: true }, false],
  ];

  it.each(cases)('%s', (_label, entry, expectStillOffered) => {
    const state = {
      schema: schemaWith(textField()),
      fieldValues: { f1: entry },
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    const offered = computeNextField(state)?.id === 'f1';
    const complete = isFormComplete(state);
    const sectionValid = SchemaFormStateManager.isSectionValid(state, 's1');
    const { filled, total } = SchemaFormStateManager.getProgressCounts(state);

    expect(offered, 'is the field still being offered?').toBe(expectStillOffered);
    // The invariant: never both at once.
    expect(offered && complete, 'offered AND complete is a contradiction').toBe(false);

    // EVERY consumer of "is this field done?" must give the same answer, not
    // just the two gates. The progress bar counted whitespace as done while the
    // gate said otherwise, so the UI showed 100% on an unfinished form.
    expect(
      { sectionValid, progressDone: filled === total },
      'section validity and the progress bar must agree with the gates',
    ).toEqual({ sectionValid: !offered, progressDone: !offered });
  });

  it('an OPTIONAL confirmed empty string still completes the form', () => {
    // The "does not apply" answer must not be caught by the blank rule.
    const state = {
      schema: schemaWith(textField({ validation: { required: false } })),
      fieldValues: { f1: { value: '', confirmed: true } },
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    expect(isFormComplete(state)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// The validator windows: settling on a blank RETIRES a field permanently.
// ---------------------------------------------------------------------------

describe('computeReadyWindows does not settle on a blank', () => {
  function windowState(f1: any) {
    const fields = [
      textField({ id: 'f1', validation: { required: false } }),
      textField({ id: 'f2', name: 'Given Name' }),
    ];
    return {
      schema: {
        source: 'web',
        form_metadata: { title: 'T', version: '1', language: 'en' },
        sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1', 'f2'] }],
        fields,
      },
      fieldValues: { f1, f2: { value: 'Maria', confirmed: true } },
      validationErrors: {},
      currentSectionId: 's1',
      validatedWindowIndices: new Set<number>(),
    } as any;
  }

  const ready = (st: any) =>
    (SchemaFormStateManager as any).computeReadyWindows(st, 2, 2).length;

  it('a confirmed WHITESPACE field holds its window open', () => {
    // The stakes here are higher than at the other gates: a window reported
    // ready is added to validatedWindowIndices, which PERSISTS to
    // sessionStorage. Retiring a window on a whitespace field means that field
    // is never validated again even after a real answer arrives -- a silent,
    // permanent loss, and a direct breach of this function's own promise that
    // "no field is ever permanently starved of validation".
    expect(ready(windowState({ value: '   ', confirmed: true }))).toBe(0);
  });

  it('a confirmed OPTIONAL empty string still settles', () => {
    // The "does not apply" answer. Must NOT be caught by the rule above --
    // isBlankFieldValue treats '' and whitespace alike, so this site needs the
    // narrower whitespace-only test, same as the other confirmedButBlank sites.
    expect(ready(windowState({ value: '', confirmed: true }))).toBe(1);
  });

  it('a SKIPPED field still settles', () => {
    expect(ready(windowState({ value: null, skipped: true, confirmed: true }))).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Overwriting a REAL answer with whitespace (the regression path).
// ---------------------------------------------------------------------------

describe('erasing a confirmed answer with whitespace', () => {
  it('drops the confirmation, blocks completion, and re-queues the field', () => {
    // The end-to-end shape of this bead, and the one a user actually produces:
    // a field the AI filled and confirmed, which the user then selects and
    // types over with spaces. Dropping the confirmation is correct -- the answer
    // is gone -- and the field must come back as a question rather than sitting
    // confirmed-but-blank, which is the state the whole bead exists to prevent.
    const field = textField();
    let state = {
      schema: schemaWith(field),
      fieldValues: {},
      validationErrors: {},
      currentSectionId: 's1',
    } as any;

    state = SchemaFormStateManager.updateField(state, 'f1', 'Maria', {
      confirmed: true,
      confirmationMethod: 'ai_voice',
    });
    expect(SchemaFormStateManager.isSectionValid(state, 's1')).toBe(true);
    expect(computeNextField(state)).toBeNull();

    // The user types over it with spaces (SchemaForm passes confirmed:false for
    // a blank -- see handleFieldChange).
    state = SchemaFormStateManager.updateField(state, 'f1', '   ', {
      confirmed: false,
    });

    expect(state.fieldValues.f1.confirmed).not.toBe(true);
    expect(SchemaFormStateManager.isSectionValid(state, 's1')).toBe(false);
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
