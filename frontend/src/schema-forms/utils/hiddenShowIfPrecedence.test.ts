/**
 * shouldShowField's hidden/show_if precedence, pinned in all four combinations
 * (bd polyglot-pdf-pfx1).
 *
 * The precedence today is ACCIDENTAL -- it falls out of the branch order:
 *
 *   if (!group) return !field.hidden;                  // no condition -> hidden wins
 *   if (conditionHasUnknownOperator(group)) return !field.hidden;
 *   return evaluateConditionGroup(group, ...);         // condition -> hidden IGNORED
 *
 * So a valid show_if silently discards `hidden`, and the contradiction resolves
 * in the RISKIER direction: a field an author marked "never show" APPEARS to
 * the applicant once its condition matches. On a legal form that can mean an
 * acceptance-agent-only field shown to the person filing.
 *
 * The MAINTAINER DECISION (2026-08-04) is to make that state unauthorable --
 * the editor gates it and lint rejects it (`hidden-with-show-if`) -- rather
 * than to change the precedence. Changing it would be a silent behavior swap
 * for any kit that already relied on the current reading, and bd
 * polyglot-pdf-ubam measured ZERO fields setting both across f1040/i-90/w7, so
 * there is nothing to migrate and no reason to take that risk.
 *
 * These tests therefore pin the CURRENT behavior as the documented contract,
 * including the both-set case. If a future change flips the precedence, that
 * must be a deliberate decision with a migration -- not a silent drift, which
 * is exactly what this file exists to prevent.
 */

import { describe, it, expect } from 'vitest';
import { shouldShowField } from './validation';
import type { FormField } from '../types/schema';

function field(overrides: Partial<FormField> = {}): FormField {
  // NOTE the shape: this is the VOICE frontend's FormField
  // (frontend/src/schema-forms/types/schema.ts), which has `name` +
  // `spoken_name` and NO `label` -- `label` belongs to the schema-EDITOR's
  // separate FormField type. Passing one to the other typechecks locally under
  // vitest (which does not type-check) and fails CI's `tsc -p tsconfig.json`.
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
const SHOW_IF = { field: 'trigger', operator: 'equals', value: 'yes' } as const;

describe('shouldShowField: hidden x show_if (bd polyglot-pdf-pfx1)', () => {
  it('NEITHER hidden nor conditional -> always shown', () => {
    const f = field();
    expect(shouldShowField(f, {}, [f, TRIGGER])).toBe(true);
    expect(shouldShowField(f, { trigger: 'no' }, [f, TRIGGER])).toBe(true);
  });

  it('HIDDEN only -> never shown, whatever the values are', () => {
    const f = field({ hidden: true });
    expect(shouldShowField(f, {}, [f, TRIGGER])).toBe(false);
    expect(shouldShowField(f, { trigger: 'yes' }, [f, TRIGGER])).toBe(false);
  });

  it('CONDITION only -> shown exactly when the condition matches', () => {
    const f = field({ show_if: SHOW_IF as any });
    expect(shouldShowField(f, { trigger: 'yes' }, [f, TRIGGER])).toBe(true);
    expect(shouldShowField(f, { trigger: 'no' }, [f, TRIGGER])).toBe(false);
    expect(shouldShowField(f, {}, [f, TRIGGER])).toBe(false);
  });

  it('BOTH -> the CONDITION wins and `hidden` is ignored (the risky reading)', () => {
    // THE DOCUMENTED CONTRADICTION. This is why the state is gated in the
    // editor and rejected by lint rather than left to resolve here: a field
    // marked never-show becomes visible. Pinned so the reading cannot drift
    // silently in either direction.
    const f = field({ hidden: true, show_if: SHOW_IF as any });
    expect(
      shouldShowField(f, { trigger: 'yes' }, [f, TRIGGER]),
      'hidden=true + condition MET currently yields VISIBLE -- the reason bd '
      + 'pfx1 gates this state instead of allowing it to be authored',
    ).toBe(true);
    expect(shouldShowField(f, { trigger: 'no' }, [f, TRIGGER])).toBe(false);
  });

  it('an UNKNOWN operator falls back to `hidden`, not to the condition', () => {
    // The third branch, easy to lose in a refactor: a condition the evaluator
    // cannot understand must NOT be treated as "shown". With hidden set the
    // field stays hidden; without it the field stays visible (fail-open on a
    // malformed condition, so a typo never strands a field the user needs).
    const bad = { field: 'trigger', operator: 'sorta_equals', value: 'yes' };
    expect(shouldShowField(field({ show_if: bad as any }), { trigger: 'yes' },
      [TRIGGER])).toBe(true);
    expect(shouldShowField(field({ hidden: true, show_if: bad as any }),
      { trigger: 'yes' }, [TRIGGER])).toBe(false);
  });

  it('an EMPTY condition object reads as absent, so `hidden` governs', () => {
    // A hand-edited schema can carry show_if: {}. normalizeToComposite yields
    // no group, so the first branch runs and `hidden` decides. The editor's
    // gate treats {} as absent for the same reason -- otherwise an empty
    // object would lock the Hidden checkbox with nothing to delete.
    expect(shouldShowField(field({ show_if: {} as any }), {}, [TRIGGER])).toBe(true);
    expect(shouldShowField(field({ hidden: true, show_if: {} as any }), {},
      [TRIGGER])).toBe(false);
  });
});
