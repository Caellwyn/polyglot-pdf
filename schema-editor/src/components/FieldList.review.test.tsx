/**
 * Human review status in the field list (bd polyglot-pdf-u8t6).
 *
 * The list icon layers the editor's review sign-off over the automatic status:
 * a real ERROR stays red even when signed off; reviewed_correct turns an
 * auto-amber field green; needs_followup shows a distinct amber flag and keeps
 * the field a "Next to review" target. The tooltip explains the human state.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldList } from './FieldList';
import type { FormSchema, FormField } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

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

function renderList(
  schema: FormSchema,
  opts: {
    onSelectField?: (id: string) => void;
    lintFindingsByField?: Map<string, LintFinding[]>;
  } = {},
) {
  render(
    <FieldList
      schema={schema}
      selectedFieldId={null}
      onSelectField={opts.onSelectField ?? vi.fn()}
      lintFindingsByField={opts.lintFindingsByField}
    />,
  );
}

describe('FieldList review status (bd u8t6)', () => {
  it('reviewed_correct turns an auto-amber field green', () => {
    const amber = completeField('amber', {
      spoken_name: undefined, help: undefined,
      _review: { status: 'reviewed_correct' },
    });
    renderList(schemaWith([amber]));
    const icon = screen.getByTestId('field-status-amber');
    expect(icon.querySelector('svg.text-green-600')).not.toBeNull();
    expect(icon.querySelector('svg.text-yellow-600')).toBeNull();
    expect(icon.getAttribute('title')).toContain('Reviewed - correct');
  });

  it('a real ERROR stays red even when marked reviewed_correct', () => {
    const broken = completeField('broken', {
      pdf_field_name: undefined,
      _review: { status: 'reviewed_correct' },
    });
    renderList(schemaWith([broken]));
    const icon = screen.getByTestId('field-status-broken');
    expect(icon.querySelector('svg.text-red-600')).not.toBeNull();
    expect(icon.querySelector('svg.text-green-600')).toBeNull();
  });

  it('needs_followup shows an amber flag and surfaces the note in the tooltip', () => {
    const flagged = completeField('flagged', {
      _review: { status: 'needs_followup', note: 'check the a-number format' },
    });
    renderList(schemaWith([flagged]));
    const icon = screen.getByTestId('field-status-flagged');
    // The flag icon is amber-600 (distinct from the auto-review yellow clock).
    expect(icon.querySelector('svg.text-amber-600')).not.toBeNull();
    expect(icon.getAttribute('title')).toContain('Needs follow-up: check the a-number format');
  });

  it('"Next to review" skips reviewed_correct and stops on needs_followup', () => {
    const onSelectField = vi.fn();
    const signedOff = completeField('a', {
      spoken_name: undefined, help: undefined,
      _review: { status: 'reviewed_correct' },
    });
    const followup = completeField('b', { _review: { status: 'needs_followup' } });
    renderList(schemaWith([signedOff, followup]), { onSelectField });
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('b');
  });

  it('disables "Next to review" only when EVERY field is signed off (bd g63j)', () => {
    const signedOff = completeField('a', {
      spoken_name: undefined, help: undefined,
      _review: { status: 'reviewed_correct' },
    });
    const alsoSignedOff = completeField('b', {
      _review: { status: 'reviewed_correct' },
    });
    renderList(schemaWith([signedOff, alsoSignedOff]));
    expect(screen.getByText('Next to review').closest('button')).toBeDisabled();
  });

  it('keeps "Next to review" ENABLED while a clean field is un-reviewed (bd g63j)', () => {
    // The machine likes field 'b', but no human has confirmed it -- there is
    // still review work to do, so the button must not read as finished.
    const signedOff = completeField('a', { _review: { status: 'reviewed_correct' } });
    const untouched = completeField('b');
    renderList(schemaWith([signedOff, untouched]));
    expect(screen.getByText('Next to review').closest('button')).toBeEnabled();
  });

  it('shows the AMBER icon on an un-reviewed clean row (bd g63j)', () => {
    // The list surface's own positive pin: without it, a regression mapping
    // the 'review' status back to the green check would pass the whole suite
    // (the other amber assertions here are negative -- fresh-eyes).
    const signedOff = completeField('a', { _review: { status: 'reviewed_correct' } });
    const untouched = completeField('b');
    renderList(schemaWith([signedOff, untouched]));
    const amber = screen.getByTestId('field-status-b');
    expect(amber.querySelector('svg.text-yellow-600')).not.toBeNull();
    expect(amber.querySelector('svg.text-green-600')).toBeNull();
    // ...and the signed-off row is genuinely green, so the two are distinct.
    const green = screen.getByTestId('field-status-a');
    expect(green.querySelector('svg.text-green-600')).not.toBeNull();
  });
});

describe('the guidance staleness gate blocks green in the LIST (bd anim)', () => {
  // THE row-level blocking pin for exit criterion 1: before this block,
  // deleting the needsGuidanceAck argument out of getFieldStatus left the
  // entire suite green (Opus round 4) -- the gate could be dead in the UI
  // with every pure-function test still passing.
  const staleFinding: LintFinding = {
    severity: 'WARNING', rule: 'guidance-identity-stale',
    path: 'fields (id=gated).help[identity:abc123]',
    message: 'guidance may be out of date', field_id: 'gated',
  };

  it('a reviewed_correct field with un-acked drift renders AMBER, not green', () => {
    const gated = completeField('gated', {
      _review: { status: 'reviewed_correct' },
    });
    renderList(schemaWith([gated]), {
      lintFindingsByField: new Map([['gated', [staleFinding]]]),
    });
    const icon = screen.getByTestId('field-status-gated');
    expect(icon.querySelector('svg.text-yellow-600')).not.toBeNull();
    expect(icon.querySelector('svg.text-green-600')).toBeNull();
    // the tooltip's FIRST line explains the amber icon it sits on, ahead of
    // the (superseded-for-now) sign-off line (Opus round 4 finding 3)
    const title = icon.getAttribute('title') ?? '';
    expect(title.startsWith('Guidance changed after this field was reviewed'))
      .toBe(true);
    expect(title).toContain('Reviewed - correct');
  });

  it('the SAME field renders green once the ack pins the current identity', () => {
    const acked = completeField('gated', {
      _review: { status: 'reviewed_correct', guidance_ack_sha1: 'abc123' },
    });
    renderList(schemaWith([acked]), {
      lintFindingsByField: new Map([['gated', [staleFinding]]]),
    });
    const icon = screen.getByTestId('field-status-gated');
    expect(icon.querySelector('svg.text-green-600')).not.toBeNull();
    expect(icon.querySelector('svg.text-yellow-600')).toBeNull();
  });

  it('"Next to review" stops on the gated field', () => {
    const onSelectField = vi.fn();
    const gated = completeField('gated', { _review: { status: 'reviewed_correct' } });
    renderList(schemaWith([gated]), {
      onSelectField,
      lintFindingsByField: new Map([['gated', [staleFinding]]]),
    });
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('gated');
  });
});
