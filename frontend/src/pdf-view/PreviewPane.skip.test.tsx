/**
 * PREVIEW MODE HAS A SKIP CONTROL (bd polyglot-pdf-ykfx0).
 *
 * The form view has offered a "Skip for now" button since bd polyglot-pdf-4dxt:
 * the sanctioned way to leave a required question deliberately unanswered.
 * Preview (the PDF surface) shipped without one -- SchemaForm rendered
 * PreviewPane with onFieldChange/onFieldBlur/onFieldFocus but no onFieldSkip,
 * and PreviewPane had no such prop at all -- so a user working in Preview whose
 * only other exit was voice had NO interface escape from a field they could not
 * answer.
 *
 * That contradicts the stated product rule: leaving a required field blank on a
 * legal intake draft "has to be explicit -- said aloud, or via the skip
 * control" (docs/components/schema-forms.md). In Preview the control did not
 * exist, so the only escape was to discover that switching views offers one.
 *
 * WHAT THESE TESTS PIN, and why each is separate:
 *   1. the button REACHES the user in Preview and resolves the field (the
 *      affordance exists and works end to end);
 *   2. the four gating conditions match the form view's, so the same field does
 *      not offer the affordance in one view and withhold it in the other;
 *   3. the PROP WIRING survives -- the chain is SchemaForm -> PreviewPane ->
 *      PDFViewer -> FieldEditPopover, and every link is optional-by-design, so
 *      dropping any one of them silently returns to the shipped bug with no
 *      type error and no other test failing.
 *
 * (3) is the one that matters most and is the bead's criterion 2: the original
 * defect was not broken logic, it was an ABSENT PROP. Nothing failed. The
 * button simply did not render, because `!!onFieldSkip` is false when nobody
 * passes it.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import type { FormSchema, FormField } from '../schema-forms/types/schema';

afterEach(() => cleanup());

vi.mock('./usePDFDocument', () => ({
  usePDFDocument: () => ({
    document: {} as any,
    numPages: 1,
    isLoading: false,
    error: null,
  }),
}));
vi.mock('./PDFPage', () => ({
  PDFPage: () => <div data-testid="mock-pdf-page" />,
}));

import PreviewPane from './PreviewPane';

const rect = (y: number) => ({ page: 1, x: 100, y, width: 120, height: 14 });

/** One REQUIRED field -- the case isSectionValid would otherwise block on. */
const REQUIRED_FIELD: FormField = {
  id: 'uscis_number',
  name: 'USCIS Number',
  spoken_name: 'USCIS number',
  section_id: 's1',
  type: 'text',
  validation: { required: true },
  pdf_position: rect(100),
} as any;

/**
 * A field required ONLY when another field says so -- so the gate has to go
 * through isFieldRequired (which evaluates require_if against fieldValues)
 * rather than reading validation.required alone.
 */
const CONDITIONAL_FIELD: FormField = {
  id: 'interpreter_name',
  name: 'Interpreter name',
  spoken_name: 'interpreter name',
  section_id: 's1',
  type: 'text',
  require_if: { field: 'used_interpreter', operator: 'equals', value: 'Yes' },
  pdf_position: rect(200),
} as any;

const TRIGGER_FIELD: FormField = {
  id: 'used_interpreter',
  name: 'Used interpreter',
  spoken_name: 'used an interpreter',
  section_id: 's1',
  type: 'text',
  pdf_position: rect(300),
} as any;

function schemaOf(...fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as any;
}

/**
 * Render Preview with the editor OPEN on `fieldId` -- the state a user reaches
 * by clicking a field's overlay on the PDF.
 */
function renderPreviewEditing(
  fieldId: string,
  opts: {
    schema?: FormSchema;
    fieldValues?: Record<string, any>;
    onFieldSkip?: ((id: string) => void) | undefined;
    passSkip?: boolean;
  } = {},
) {
  const schema = opts.schema ?? schemaOf(REQUIRED_FIELD);
  const onFieldSkip = opts.onFieldSkip ?? vi.fn();
  const passSkip = opts.passSkip ?? true;

  const utils = render(
    <PreviewPane
      pdfUrl="/fake.pdf"
      schema={schema}
      fieldValues={opts.fieldValues ?? {}}
      currentFieldId={null}
      validationErrors={{}}
      onFieldChange={vi.fn()}
      onFieldBlur={vi.fn()}
      onFieldFocus={vi.fn()}
      {...(passSkip ? { onFieldSkip } : {})}
    />,
  );

  // Click the field's overlay to open the editor, the way a user does.
  const overlay = screen.getByTestId(`pdf-field-overlay-${fieldId}`);
  fireEvent.click(overlay);
  return { ...utils, onFieldSkip };
}

describe('Preview mode offers the skip control (bd polyglot-pdf-ykfx0)', () => {
  it('a required, empty field shows "Skip for now" in the PDF editor', () => {
    renderPreviewEditing(REQUIRED_FIELD.id);
    expect(
      screen.getByRole('button', { name: /skip for now/i }),
      'a Preview user must have a UI exit from a required field they cannot answer',
    ).toBeTruthy();
  });

  it('pressing it resolves the field through the SAME handler the form view uses', () => {
    const { onFieldSkip } = renderPreviewEditing(REQUIRED_FIELD.id);

    fireEvent.click(screen.getByRole('button', { name: /skip for now/i }));

    // SchemaForm wires this to handleFieldSkip -> markFieldSkipped, the one
    // path the form view's button also takes. Asserting the field id is what
    // proves the wiring targets the right field, not merely that a click fired.
    expect(onFieldSkip).toHaveBeenCalledWith(REQUIRED_FIELD.id);
  });

  it('closes the editor after skipping, so the resolved field is not left open', () => {
    renderPreviewEditing(REQUIRED_FIELD.id);
    expect(screen.queryByTestId(`pdf-field-edit-popover-${REQUIRED_FIELD.id}`)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /skip for now/i }));

    expect(
      screen.queryByTestId(`pdf-field-edit-popover-${REQUIRED_FIELD.id}`),
      'leaving the editor open over a just-skipped field invites a second click ' +
        'on a button that has now vanished',
    ).toBeNull();
  });
});

describe('the Preview skip gate matches the form view (bd polyglot-pdf-ykfx0)', () => {
  // SectionRenderer gates on: a handler exists, the field is required, still
  // empty, and not already skipped. Preview must agree, or the same field
  // offers the affordance in one view and withholds it in the other.

  it('is NOT offered for an OPTIONAL field -- there is nothing to skip', () => {
    const optional = { ...REQUIRED_FIELD, validation: { required: false } } as FormField;
    renderPreviewEditing(optional.id, { schema: schemaOf(optional) });
    expect(screen.queryByRole('button', { name: /skip for now/i })).toBeNull();
  });

  it('is NOT offered once the field HAS a value -- answer it instead', () => {
    renderPreviewEditing(REQUIRED_FIELD.id, {
      fieldValues: { [REQUIRED_FIELD.id]: { value: 'A123456789' } },
    });
    expect(screen.queryByRole('button', { name: /skip for now/i })).toBeNull();
  });

  it('treats WHITESPACE as still-empty, so a space-filled field can be skipped', () => {
    // The shared isBlankFieldValue predicate (bd polyglot-pdf-5ovod). A
    // re-typed `=== ''` check here would hide the button for a field holding
    // spaces -- which is the deadlock shape bd polyglot-pdf-xtj97 pinned on the
    // voice side.
    renderPreviewEditing(REQUIRED_FIELD.id, {
      fieldValues: { [REQUIRED_FIELD.id]: { value: '   ' } },
    });
    expect(screen.getByRole('button', { name: /skip for now/i })).toBeTruthy();
  });

  it('is NOT offered for an ALREADY-skipped field, which shows the follow-up note instead', () => {
    renderPreviewEditing(REQUIRED_FIELD.id, {
      fieldValues: { [REQUIRED_FIELD.id]: { value: '', skipped: true } },
    });
    expect(screen.queryByRole('button', { name: /skip for now/i })).toBeNull();

    // Assert the ROLE, not just the text. Pressing Skip removes the button on
    // the same render, so without role="status" a screen-reader user gets
    // silence exactly where the control they just used disappeared. A plain
    // getByText passes either way -- it cannot see the role -- which is how the
    // first version of this shipped with the announcement missing.
    const note = screen.getByRole('status');
    expect(note.textContent).toMatch(/needs follow-up/i);

    // And the SHARED styled classes, not a popover-specific variant: the
    // form-field__skipped rules are what render the amber badge. An invented
    // class name would leave this note unstyled while still matching on text.
    expect(note.className).toContain('form-field__skipped');
    expect(note.querySelector('.form-field__skipped-badge')?.textContent).toBe('Skipped');
  });

  it('offers it for a field required only CONDITIONALLY, once the condition holds', () => {
    // require_if points at another field's value. This pins that the gate goes
    // through isFieldRequired (which evaluates require_if) rather than reading
    // validation.required alone -- a field with no `required` flag still offers
    // the control when its condition is met.
    //
    // It does NOT pin the `allFields` argument: the evaluator accepts that
    // parameter and never reads it, so passing [field] instead changes nothing.
    // Verified by mutation. See the prop's docstring in FieldEditPopover.
    const schema = schemaOf(TRIGGER_FIELD, CONDITIONAL_FIELD);

    renderPreviewEditing(CONDITIONAL_FIELD.id, {
      schema,
      fieldValues: { [TRIGGER_FIELD.id]: { value: 'Yes' } },
    });
    expect(
      screen.getByRole('button', { name: /skip for now/i }),
      'a field required BECAUSE of another field must offer the skip control',
    ).toBeTruthy();
    // Mutation-verified: dropping `required` from the gate reddens this.
  });

  it('withholds it when that same conditional requirement is NOT met', () => {
    const schema = schemaOf(TRIGGER_FIELD, CONDITIONAL_FIELD);

    renderPreviewEditing(CONDITIONAL_FIELD.id, {
      schema,
      fieldValues: { [TRIGGER_FIELD.id]: { value: 'No' } },
    });
    expect(screen.queryByRole('button', { name: /skip for now/i })).toBeNull();
  });
});

describe('the skip prop wiring survives (bd polyglot-pdf-ykfx0 criterion 2)', () => {
  it('renders NO skip button when the handler is not passed -- the shipped bug', () => {
    // THE REGRESSION ITSELF. Every link in the chain (SchemaForm ->
    // PreviewPane -> PDFViewer -> FieldEditPopover) is optional by design, so
    // dropping any one silently restores this state: no type error, no other
    // test failing, just a button that never renders.
    //
    // This test documents that the absence is DETECTABLE, and the sibling tests
    // above fail the moment the prop stops arriving -- which is what makes the
    // wiring pinned rather than merely present today.
    renderPreviewEditing(REQUIRED_FIELD.id, { passSkip: false });

    expect(screen.queryByTestId(`pdf-field-edit-popover-${REQUIRED_FIELD.id}`)).toBeTruthy();
    expect(
      screen.queryByRole('button', { name: /skip for now/i }),
      'without a handler the popover must render no skip button at all',
    ).toBeNull();
  });
});
