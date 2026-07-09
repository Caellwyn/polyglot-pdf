/**
 * Unit tests for SectionRenderer's 4dxt skip affordance.
 *
 * Pins that the "Skip for now" button and the "Skipped -- needs follow-up" badge
 * render under exactly the right per-field conditions (a shown, currently
 * required, empty, not-yet-skipped field gets the button; a skipped field gets
 * the badge instead), and that clicking the button fires onFieldSkip. The
 * load-bearing gate logic (isSectionValid + markFieldSkipped) is unit-tested in
 * schemaFormState.test.ts; this covers the UI wiring.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { SectionRenderer } from './SectionRenderer';
import type { FormSection, FormField, FieldValue } from '../types/schema';

describe('SectionRenderer: 4dxt skip affordance', () => {
  afterEach(() => cleanup());

  const section: FormSection = { id: 'sec', label: 'Sec', order: 1, fields: ['req', 'opt'] };
  const fields: FormField[] = [
    { id: 'req', name: 'Required field', spoken_name: 'required field', type: 'text',
      section_id: 'sec', validation: { required: true } },
    { id: 'opt', name: 'Optional field', spoken_name: 'optional field', type: 'text',
      section_id: 'sec' },
  ];

  const baseProps = {
    section,
    fields,
    validationErrors: {},
    onFieldChange: vi.fn(),
    onFieldBlur: vi.fn(),
  };

  it('shows a "Skip for now" button for a shown, required, empty field', () => {
    render(<SectionRenderer {...baseProps} fieldValues={{}} onFieldSkip={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Skip for now/i })).toBeTruthy();
  });

  it('does NOT show a skip button for an optional empty field', () => {
    // Render ONLY the optional field (SectionRenderer maps over the `fields`
    // prop, not section.fields).
    const optField = fields.filter((f) => f.id === 'opt');
    const optOnly = { ...section, fields: ['opt'] };
    render(
      <SectionRenderer
        {...baseProps}
        section={optOnly}
        fields={optField}
        fieldValues={{}}
        onFieldSkip={vi.fn()}
      />
    );
    expect(screen.queryByRole('button', { name: /Skip for now/i })).toBeNull();
  });

  it('does NOT show a skip button for a filled required field', () => {
    const values: Record<string, FieldValue> = { req: { value: 'Jane' } };
    render(<SectionRenderer {...baseProps} fieldValues={values} onFieldSkip={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /Skip for now/i })).toBeNull();
  });

  it('fires onFieldSkip with the field id when the button is clicked', () => {
    const onFieldSkip = vi.fn();
    render(<SectionRenderer {...baseProps} fieldValues={{}} onFieldSkip={onFieldSkip} />);
    fireEvent.click(screen.getByRole('button', { name: /Skip for now/i }));
    expect(onFieldSkip).toHaveBeenCalledWith('req');
  });

  it('shows the "Skipped" badge (not the button) for a skipped field', () => {
    const values: Record<string, FieldValue> = { req: { value: null, skipped: true, confirmed: true } };
    render(<SectionRenderer {...baseProps} fieldValues={values} onFieldSkip={vi.fn()} />);
    expect(screen.getByText('Skipped')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Skip for now/i })).toBeNull();
  });

  it('renders no skip button when onFieldSkip is not provided', () => {
    render(<SectionRenderer {...baseProps} fieldValues={{}} />);
    expect(screen.queryByRole('button', { name: /Skip for now/i })).toBeNull();
  });

  it('renders NO wrapper node for a hidden (show_if-unmet) field (no phantom gap)', () => {
    // A field gated on trigger=yes; with trigger unset it is not shown and must
    // produce no .section__field node (matches FieldRenderer returning null).
    const gatedSection: FormSection = { id: 'sec', label: 'Sec', order: 1, fields: ['gated'] };
    const gatedFields: FormField[] = [
      { id: 'gated', name: 'Gated', spoken_name: 'gated', type: 'text', section_id: 'sec',
        validation: { required: true },
        show_if: { field: 'trigger', operator: 'equals', value: 'yes' } },
    ];
    const { container } = render(
      <SectionRenderer
        {...baseProps}
        section={gatedSection}
        fields={gatedFields}
        fieldValues={{}}
        onFieldSkip={vi.fn()}
      />
    );
    // Not shown -> no field wrapper, no skip button.
    expect(container.querySelector('.section__field')).toBeNull();
    expect(screen.queryByRole('button', { name: /Skip for now/i })).toBeNull();
  });
});
