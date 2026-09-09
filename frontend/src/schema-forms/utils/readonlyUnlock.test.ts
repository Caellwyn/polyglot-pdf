/**
 * A read_only field that declares flip_readonly_bit is WRITABLE once shown --
 * pinned across every surface that gates a write (bd polyglot-pdf-38p0y).
 *
 * THE BUG THIS PINS. `isFieldReadOnly` returned true for ANY read_only field,
 * with an in-code comment conceding the unlock check was unimplemented. Three
 * other surfaces already honored flip_readonly_bit independently:
 *
 *   FieldRenderer.tsx:82        lifts the UI disable once the field is shown
 *   FieldEditPopover.tsx:96     lets a human type into it in PDF view
 *   pdf_fill_routes.py          clears the widget's read-only bit on fill
 *
 * ...so only the AI-write gate refused. A field that is require_if-gated on the
 * same condition that shows it (the i-90's mail_unit_number, shown+required the
 * moment a mailing unit TYPE is picked) was therefore ASKED FOR and forbidden:
 * the model got "system-managed and cannot be filled; do not attempt to fill it
 * again", the user was left to type it by hand, and the section could not
 * validate. Three surfaces said writable, one said no.
 *
 * WHY SYNTHETIC FIELDS (CLAUDE.md scar #10). No GIT-TRACKED kit contains a
 * single flip_readonly_bit field -- w7 and f1040 both have zero. The i-90 that
 * motivated this bead lives in the bucket, not in git, so a test reading a real
 * kit would run green on a maintainer's disk and SKIP in CI, which is precisely
 * the failure mode that shipped twice on the previous branch. These fixtures
 * encode the SHAPE the i-90 has, so the guard is alive in a clean clone.
 *
 * BOTH KEYS ARE LOAD-BEARING: `conditional_behavior` is canonical and
 * `conditional_logic` is the legacy alias still emitted by generated kits (the
 * i-90 uses it), so dropping either silently re-breaks one kit generation.
 */

import { describe, it, expect } from 'vitest';
import { isFieldReadOnly, declaresShownUnlock } from './validation';
import { checkFieldAccess, evaluateFieldAvailability } from './conditionalFieldCheck';
import type { FormField, FormSchema } from '../types/schema';

function field(overrides: Partial<FormField> = {}): FormField {
  // The VOICE frontend's FormField (name + spoken_name, no `label`) -- passing
  // the schema-editor's shape typechecks under vitest and fails CI's tsc.
  return {
    id: 'target',
    name: 'Target',
    spoken_name: 'target',
    type: 'text',
    section_id: 's1',
    ...overrides,
  } as FormField;
}

const TRIGGER = field({ id: 'trigger', name: 'Trigger', spoken_name: 'trigger' });
const SHOW_IF = { field: 'trigger', operator: 'is_not_empty' } as const;

/** The i-90's mail_unit_number shape: read_only + shown-unlock + show_if. */
function unlockable(overrides: Partial<FormField> = {}): FormField {
  return field({
    read_only: true,
    show_if: SHOW_IF,
    conditional_behavior: { unlock_method: 'flip_readonly_bit' },
    ...overrides,
  } as Partial<FormField>);
}

const SHOWN = { trigger: 'Apt' };
const NOT_SHOWN = { trigger: '' };

function schemaOf(...fields: FormField[]): FormSchema {
  return { fields, sections: [{ id: 's1', fields: fields.map(f => f.id) }] } as unknown as FormSchema;
}

describe('declaresShownUnlock: both key spellings (bd polyglot-pdf-38p0y)', () => {
  it('reads the CANONICAL conditional_behavior key', () => {
    expect(declaresShownUnlock(unlockable())).toBe(true);
  });

  it('reads the LEGACY conditional_logic alias that generated kits emit', () => {
    const f = field({
      read_only: true,
      conditional_logic: { unlock_method: 'flip_readonly_bit' },
    } as Partial<FormField>);
    expect(declaresShownUnlock(f)).toBe(true);
  });

  it('is false for a field declaring no unlock, and for the OTHER unlock_method', () => {
    // set_property is the only other member of the union -- it does NOT clear
    // the read-only bit, so it must not open the AI-write gate.
    expect(declaresShownUnlock(field({ read_only: true }))).toBe(false);
    expect(
      declaresShownUnlock(field({
        read_only: true,
        conditional_behavior: { unlock_method: 'set_property' },
      } as Partial<FormField>)),
    ).toBe(false);
  });
});

describe('isFieldReadOnly: unlock requires BEING SHOWN (bd polyglot-pdf-38p0y)', () => {
  it('THE BUG: an unlockable field, once shown, is writable', () => {
    const f = unlockable();
    expect(isFieldReadOnly(f, SHOWN, [f, TRIGGER])).toBe(false);
  });

  it('...but stays read-only while its show_if is NOT satisfied', () => {
    // Visibility is genuinely part of the condition. FieldRenderer can assume
    // "shown" because it only runs on rendered fields; this helper cannot.
    const f = unlockable();
    expect(isFieldReadOnly(f, NOT_SHOWN, [f, TRIGGER])).toBe(true);
  });

  it('a read_only field with NO unlock stays read-only however it is shown', () => {
    const f = field({ read_only: true, show_if: SHOW_IF });
    expect(isFieldReadOnly(f, SHOWN, [f, TRIGGER])).toBe(true);
    expect(isFieldReadOnly(f, NOT_SHOWN, [f, TRIGGER])).toBe(true);
  });

  it('a field that is not read_only at all is never read-only', () => {
    const f = field();
    expect(isFieldReadOnly(f, SHOWN, [f, TRIGGER])).toBe(false);
  });

  it('an unlockable field with NO show_if is unlocked (nothing gates it)', () => {
    // shouldShowField returns !hidden when there is no condition, so an
    // unconditional unlockable field reads as shown -- and the PDF filler
    // unlocks its widget unconditionally too, so the surfaces agree.
    const f = field({
      read_only: true,
      conditional_behavior: { unlock_method: 'flip_readonly_bit' },
    } as Partial<FormField>);
    expect(isFieldReadOnly(f, {}, [f])).toBe(false);
  });

  it('a HIDDEN unlockable field is still read-only', () => {
    const f = unlockable({ hidden: true, show_if: undefined } as Partial<FormField>);
    expect(isFieldReadOnly(f, SHOWN, [f, TRIGGER])).toBe(true);
  });

  it('accepts wrapped FieldValue shapes, not just raw values', () => {
    // evaluateFieldAvailability passes Record<string, FieldValue>; the
    // condition evaluator unwraps, and this pins that the two callers agree.
    const f = unlockable();
    const wrapped = { trigger: { value: 'Apt', confirmed: true } } as any;
    expect(isFieldReadOnly(f, wrapped, [f, TRIGGER])).toBe(false);
  });
});

describe('the OTHER field the bead names: a checkbox-gated textarea', () => {
  // accommodation_other_detail is the second field exit criterion 1 names, and
  // it is a genuinely different shape from mail_unit_number: the trigger is a
  // CHECKBOX read with is_checked (not a text field read with is_not_empty), and
  // the target is a textarea. Testing only the text/is_not_empty pair would leave
  // the operator this field depends on unexercised.
  const detail = field({
    id: 'accommodation_other_detail',
    name: 'Accommodation Other Detail',
    spoken_name: 'accommodation detail',
    type: 'textarea',
    read_only: true,
    show_if: { field: 'accommodation_other', operator: 'is_checked' },
    conditional_behavior: { unlock_method: 'flip_readonly_bit' },
  } as Partial<FormField>);
  const box = field({
    id: 'accommodation_other',
    name: 'Accommodation Other',
    spoken_name: 'other accommodation',
    type: 'checkbox',
  });

  it('is writable once the box is CHECKED', () => {
    expect(isFieldReadOnly(detail, { accommodation_other: true }, [detail, box])).toBe(false);
  });

  it('stays read-only while the box is unchecked', () => {
    expect(isFieldReadOnly(detail, { accommodation_other: false }, [detail, box])).toBe(true);
    // ...and when the trigger has no value at all.
    expect(isFieldReadOnly(detail, {}, [detail, box])).toBe(true);
  });

  it('the write gates agree with it', () => {
    const schema = schemaOf(detail, box);
    expect(checkFieldAccess('accommodation detail', schema, { accommodation_other: true }).accessible).toBe(true);
    expect(checkFieldAccess('accommodation detail', schema, { accommodation_other: false }).accessible).toBe(false);
  });
});

describe('the AI-write gates honor the unlock (bd polyglot-pdf-38p0y)', () => {
  it('checkFieldAccess ACCEPTS a shown unlockable field', () => {
    const f = unlockable();
    const result = checkFieldAccess('target', schemaOf(f, TRIGGER), SHOWN);
    expect(result.accessible).toBe(true);
  });

  it('checkFieldAccess still refuses it while NOT shown', () => {
    const f = unlockable();
    const result = checkFieldAccess('target', schemaOf(f, TRIGGER), NOT_SHOWN);
    expect(result.accessible).toBe(false);
  });

  it('checkFieldAccess still refuses a read_only field with no unlock', () => {
    const f = field({ read_only: true });
    const result = checkFieldAccess('target', schemaOf(f, TRIGGER), SHOWN);
    expect(result.accessible).toBe(false);
    expect(result.reason).toBe('field_read_only');
  });

  it('evaluateFieldAvailability reports a shown unlockable field as available', () => {
    const f = unlockable();
    const { availability } = evaluateFieldAvailability(f, SHOWN as any, schemaOf(f, TRIGGER));
    expect(availability).not.toBe('locked');
  });

  it('evaluateFieldAvailability still locks it while NOT shown', () => {
    const f = unlockable();
    const { availability } = evaluateFieldAvailability(f, NOT_SHOWN as any, schemaOf(f, TRIGGER));
    expect(availability).toBe('locked');
  });

  it('evaluateFieldAvailability still locks a read_only field with no unlock', () => {
    const f = field({ read_only: true });
    const { availability, lockedReason } = evaluateFieldAvailability(
      f, SHOWN as any, schemaOf(f, TRIGGER),
    );
    expect(availability).toBe('locked');
    expect(lockedReason).toContain('read-only');
  });
});
