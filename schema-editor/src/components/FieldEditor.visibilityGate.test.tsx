/**
 * The hidden/show_if MUTUAL GATE in the editor UI (bd polyglot-pdf-pfx1).
 *
 * MAINTAINER DECISION 2026-08-04: "A field cannot be hidden and have a
 * condition to be shown. period." A warning was considered and rejected, so
 * this is enforced by making the state unauthorable -- which means the
 * enforcement lives in JSX, and JSX is exactly what a refactor breaks
 * silently. The lint rule and the shouldShowField precedence tests both stay
 * green if this component re-enables the checkbox, because neither of them
 * renders the component (fresh-eyes round 1 coverage gap).
 *
 * Pins BOTH directions plus the effective-visibility badge, since the badge is
 * the maintainer's answer to "how will editors be reminded which hidden is
 * active?" and is equally invisible to every other test.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

const SHOW_IF = { field: 'trigger', operator: 'equals', value: 'yes' };

function field(overrides: Partial<FormField> = {}): FormField {
  return {
    id: 'target', name: 'Target', type: 'text',
    pdf_field_name: 't[0]', read_only: false, spoken_name: 'target',
    ...overrides,
  } as FormField;
}

function schema(f: FormField): FormSchema {
  return {
    form_metadata: { title: 'T', version: '1', form_number: 'T' },
    sections: [],
    fields: [f, { id: 'trigger', name: 'Trigger', type: 'text' }],
  } as unknown as FormSchema;
}

function hiddenCheckbox(): HTMLInputElement {
  // The Hidden control is the checkbox whose label text is exactly "Hidden".
  const label = screen.getByText('Hidden').closest('label');
  return label!.querySelector('input[type="checkbox"]') as HTMLInputElement;
}

afterEach(cleanup);

describe('FieldEditor hidden/show_if mutual gate (bd polyglot-pdf-pfx1)', () => {
  it('Hidden is ENABLED when the field has no condition', () => {
    const f = field();
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    expect(hiddenCheckbox().disabled).toBe(false);
  });

  it('Hidden is DISABLED while a show_if exists', () => {
    const f = field({ show_if: SHOW_IF as any });
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    expect(
      hiddenCheckbox().disabled,
      'a field with a condition must not be markable always-hidden',
    ).toBe(true);
  });

  it('the gate is the DISABLED attribute, not just the dimmed styling', () => {
    // opacity-50 alone would LOOK gated while still authoring the forbidden
    // state, so assert the attribute a browser actually enforces.
    //
    // NOT asserted via fireEvent.click: jsdom dispatches a click straight at
    // the node and does NOT suppress activation behavior on a disabled input
    // the way a real browser does, so the handler runs and the assertion would
    // fail against CORRECT code (measured -- this test failed exactly that way
    // on first run). @testing-library/user-event, which DOES honor the
    // disabled attribute, is not a dependency here. The attribute is the real
    // contract; the dimmed styling
    // is cosmetic, and the tests above/below pin that it tracks the condition.
    const f = field({ show_if: SHOW_IF as any });
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    const box = hiddenCheckbox();
    expect(box.disabled).toBe(true);
    expect(box.hasAttribute('disabled')).toBe(true);
  });

  it('an EMPTY condition object does NOT lock Hidden', () => {
    // Parity with schema_lint's absent-set (None, {}, []). If the editor
    // treated {} as present, the checkbox would be locked over a condition
    // lint says does not exist -- with nothing on screen to delete.
    const f = field({ show_if: {} as any });
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    expect(hiddenCheckbox().disabled).toBe(false);
  });

  it('an EMPTY condition ARRAY does NOT lock Hidden', () => {
    // The shape the first cut of hasCondition got wrong (fresh-eyes round 1).
    const f = field({ show_if: [] as any });
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    expect(hiddenCheckbox().disabled).toBe(false);
  });

  it('the "Shown when" builder is REPLACED while Hidden is ticked', () => {
    // The reverse direction: an always-hidden field cannot GAIN a condition.
    const f = field({ hidden: true });
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    expect(screen.getByText(/Unavailable: this field is marked/)).toBeTruthy();
  });

  it('the "Shown when" builder RENDERS when the field is not hidden', () => {
    const f = field();
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    expect(screen.queryByText(/Unavailable: this field is marked/)).toBeNull();
  });

  it.each([
    ['Always shown', {}],
    ['Always hidden', { hidden: true }],
    ['Shown when a condition matches', { show_if: SHOW_IF }],
    ['Conflict: hidden AND conditional', { hidden: true, show_if: SHOW_IF }],
  ])('effective visibility reads "%s"', (expected, overrides) => {
    // All four combinations, including the CONFLICT state -- unauthorable
    // through this UI, but reachable in a hand-edited or imported kit, and the
    // badge is what tells the author why lint is rejecting their publish.
    const f = field(overrides as Partial<FormField>);
    render(<FieldEditor field={f} schema={schema(f)} onUpdateField={() => {}} />);
    expect(screen.getByText(expected)).toBeTruthy();
  });
});
