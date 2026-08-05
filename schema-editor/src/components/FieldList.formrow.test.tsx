/**
 * The pinned Form row + the review filter (sprint-18 C1, bd polyglot-pdf-o7y9).
 *
 * Schema-level findings (no field anchor) render on ONE pinned row at the top
 * of the field list -- the only place a standalone dismiss exists (WARNINGs
 * only; ERRORs cannot be waved away). The strip count's secondary action
 * narrows the list to review targets; per-field findings flag their rows with
 * a visible count chip.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { FieldList } from './FieldList';
import type { FormSchema, FormField } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

afterEach(cleanup);

function completeField(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: `pdf.${id}`,
    spoken_name: `spoken ${id}`, section_id: 'sec-1', read_only: false,
    help: { instructions: 'All set.' },
    ...extra,
  } as unknown as FormField;
}

function schemaWith(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T', total_widgets: fields.length,
      total_fields: fields.length, version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 'sec-1', label: 'Section 1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

const coverageWarning: LintFinding = {
  severity: 'WARNING', rule: 'help-instructions-missing',
  path: '$.fields', message: '12 fields have no spoken guidance yet',
  field_id: null,
};
const multiclaimError: LintFinding = {
  severity: 'ERROR', rule: 'dump-widget-multiclaim',
  path: "widget 'form1[0].y[0]'",
  message: 'this PDF box is claimed by more than one field',
  field_id: null,
};

describe('the pinned Form row (s18 C1, decision 1)', () => {
  it('renders form-level findings once, at the top, with label + remedy', () => {
    render(
      <FieldList schema={schemaWith([completeField('a')])}
        selectedFieldId={null} onSelectField={vi.fn()}
        formFindings={[coverageWarning]} />,
    );
    const row = screen.getByTestId('form-findings-row');
    expect(row).toHaveTextContent('Form');
    expect(row).toHaveTextContent('1 notice');
    // Expand -> the finding renders with its friendly label, message, remedy.
    fireEvent.click(screen.getByRole('button', { name: /Form/ }));
    expect(row).toHaveTextContent('No spoken guidance yet');
    expect(row).toHaveTextContent('12 fields have no spoken guidance yet');
    expect(row).toHaveTextContent('Write spoken instructions for this field.');
  });

  it('auto-expands when an ERROR-severity form finding appears', () => {
    render(
      <FieldList schema={schemaWith([completeField('a')])}
        selectedFieldId={null} onSelectField={vi.fn()}
        formFindings={[multiclaimError]} />,
    );
    const row = screen.getByTestId('form-findings-row');
    expect(row).toHaveTextContent('1 to fix');
    // No click needed -- the ERROR body is already visible.
    expect(row).toHaveTextContent('claimed by more than one field');
  });

  it('offers Dismiss for a WARNING but never for an ERROR', () => {
    const onDismissFormFinding = vi.fn();
    render(
      <FieldList schema={schemaWith([completeField('a')])}
        selectedFieldId={null} onSelectField={vi.fn()}
        formFindings={[multiclaimError, coverageWarning]}
        onDismissFormFinding={onDismissFormFinding} />,
    );
    // Auto-expanded by the ERROR. Finding 0 = the ERROR (no dismiss),
    // finding 1 = the WARNING (dismissable).
    expect(screen.queryByTestId('dismiss-form-finding-0')).toBeNull();
    fireEvent.click(screen.getByTestId('dismiss-form-finding-1'));
    expect(onDismissFormFinding).toHaveBeenCalledWith(coverageWarning);
  });

  it('a section-anchored blocking ERROR has the Form row as its home (Opus round 2)', () => {
    // to-review-pending carries a SECTION id in field_id, so no field row can
    // show it; the host routes it here via visibleFormFindings' resolves-to-
    // no-field rule. Under the removed pane it was listed; rendering it
    // nowhere would re-create the confident-strip-then-409.
    const sectionError: LintFinding = {
      severity: 'ERROR', rule: 'to-review-pending',
      path: 'sections[0] (id=sec_to_review_misc)',
      message: 'these fields still need re-filing into a real section',
      field_id: 'sec_to_review_misc',
    };
    render(
      <FieldList schema={schemaWith([completeField('a')])}
        selectedFieldId={null} onSelectField={vi.fn()}
        formFindings={[sectionError]} />,
    );
    const row = screen.getByTestId('form-findings-row');
    expect(row).toHaveTextContent('1 to fix');
    expect(row).toHaveTextContent('still need re-filing');
  });

  it('renders no row at all when there are no form-level findings', () => {
    render(
      <FieldList schema={schemaWith([completeField('a')])}
        selectedFieldId={null} onSelectField={vi.fn()} formFindings={[]} />,
    );
    expect(screen.queryByTestId('form-findings-row')).toBeNull();
  });
});

describe('per-row finding flags (s18 C1)', () => {
  it('flags a row with its finding count, red when any ERROR', () => {
    const fields = [completeField('a'), completeField('b')];
    const byField = new Map<string, LintFinding[]>([
      ['a', [
        { severity: 'ERROR', rule: 'field-unbacked',
          path: 'fields[0] (id=a)', message: 'no PDF box', field_id: 'a' },
        { severity: 'WARNING', rule: 'help-instructions-too-long',
          path: 'fields[0] (id=a).help.instructions', message: 'long',
          field_id: 'a' },
      ]],
    ]);
    render(
      <FieldList schema={schemaWith(fields)} selectedFieldId={null}
        onSelectField={vi.fn()} lintFindingsByField={byField} />,
    );
    const flag = screen.getByTestId('field-flag-a');
    expect(flag).toHaveTextContent('2');
    expect(flag.className).toContain('bg-red-100');
    expect(screen.queryByTestId('field-flag-b')).toBeNull();
  });

  it('excludes the staleness rule from the badge, matching the editor chip (Opus round 2)', () => {
    // The staleness finding's rendering is the ack-gate box + the amber
    // status icon; counting it in the row badge while the FieldEditor chip
    // omits it made the two surfaces disagree about the same field.
    const byField = new Map<string, LintFinding[]>([
      ['a', [{
        severity: 'WARNING', rule: 'guidance-identity-stale',
        path: 'fields (id=a).help[identity:abc123]',
        message: 'guidance may be out of date', field_id: 'a',
      }]],
    ]);
    render(
      <FieldList schema={schemaWith([completeField('a')])} selectedFieldId={null}
        onSelectField={vi.fn()} lintFindingsByField={byField} />,
    );
    expect(screen.queryByTestId('field-flag-a')).toBeNull();
  });
});

describe('the review filter (the strip count secondary action, s18 C1)', () => {
  it('narrows the list to review targets and says so, with a way back', () => {
    const reviewed = completeField('done', {
      _review: { status: 'reviewed_correct', seen_fingerprints: [] },
    });
    const pending = completeField('todo');
    const onClearReviewFilter = vi.fn();
    render(
      <FieldList schema={schemaWith([reviewed, pending])}
        selectedFieldId={null} onSelectField={vi.fn()}
        reviewFilterActive onClearReviewFilter={onClearReviewFilter} />,
    );
    expect(screen.getByTestId('review-filter-note')).toBeInTheDocument();
    // The reviewed field's row is filtered out; the pending one stays.
    expect(screen.queryByText('done')).toBeNull();
    expect(screen.getByText('todo')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(onClearReviewFilter).toHaveBeenCalled();
  });

  it('renders every field (and no note) when the filter is off', () => {
    const reviewed = completeField('done', {
      _review: { status: 'reviewed_correct', seen_fingerprints: [] },
    });
    render(
      <FieldList schema={schemaWith([reviewed, completeField('todo')])}
        selectedFieldId={null} onSelectField={vi.fn()} />,
    );
    expect(screen.queryByTestId('review-filter-note')).toBeNull();
    expect(screen.getByText('done')).toBeInTheDocument();
    expect(screen.getByText('todo')).toBeInTheDocument();
  });
});
