/**
 * The guidance staleness gate, end to end in the COMPONENT (bd anim exit
 * criterion 1): a drifted field highlights Instructions and shows the
 * acknowledgment checkbox; ticking it records an ack pinned to the CURRENT
 * identity; a field with no drift shows neither.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import { needsGuidanceAck, staleFieldIds, currentIdentity } from '../utils/guidanceStaleness';
import { effectiveStatus } from '../utils/reviewStatus';
import type { FormSchema, FormField } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

const IDENTITY = 'a1b2c3d4';

const FIELD: FormField = {
  id: 'phone', name: 'Phone', spoken_name: 'phone number', type: 'text',
  section_id: 's1', pdf_field_name: 'P[0]',
  help: { instructions: 'Enter the phone number on your application.' },
} as unknown as FormField;

function makeSchema(f: FormField): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
    parts: [], sections: [{ id: 's1', label: 'S1', order: 1, fields: [f.id] }],
    fields: [f],
  } as unknown as FormSchema;
}

const staleFinding: LintFinding = {
  severity: 'WARNING', rule: 'guidance-identity-stale',
  path: `fields (id=phone).help[identity:${IDENTITY}]`,
  message: 'this field changed since its guidance was written',
  field_id: 'phone',
};

describe('FieldEditor guidance staleness gate (bd anim criterion 1)', () => {
  it('a DRIFTED field highlights Instructions and offers the ack checkbox', () => {
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    const box = screen.getByTestId('guidance-ack-checkbox') as HTMLInputElement;
    expect(box).toBeInTheDocument();
    expect(box.checked).toBe(false);
    // the Instructions textarea carries the highlight ring
    const ta = screen.getByPlaceholderText(/Instructions for filling out this field/);
    expect(ta.className).toMatch(/ring-2/);
  });

  it('shows NEITHER for a field with no drift (criterion 2)', () => {
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[]} />,
    );
    expect(screen.queryByTestId('guidance-ack-checkbox')).toBeNull();
    const ta = screen.getByPlaceholderText(/Instructions for filling out this field/);
    expect(ta.className).not.toMatch(/ring-2/);
  });

  it('ticking the box records an ack pinned to the CURRENT identity', () => {
    const onUpdateField = vi.fn();
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={onUpdateField} authorTier lintFindings={[staleFinding]} />,
    );
    fireEvent.click(screen.getByTestId('guidance-ack-checkbox'));
    const updated = onUpdateField.mock.calls[0][0] as FormField;
    expect(updated._review?.guidance_ack_sha1).toBe(IDENTITY);
  });

  it('the gate blocks green until acked, then releases (criterion 1 end to end)', () => {
    const reviewed = { ...FIELD, _review: { status: 'reviewed_correct' } } as FormField;
    const ids = staleFieldIds([staleFinding]);
    const cur = currentIdentity([staleFinding], 'phone');
    // drifted + un-acked: reviewed_correct is DEMOTED to amber
    expect(needsGuidanceAck(reviewed, ids, cur)).toBe(true);
    expect(effectiveStatus(reviewed, false, undefined, true)).toBe('review');
    // after the ack the gate releases and green returns
    const acked = { ...reviewed,
      _review: { status: 'reviewed_correct', guidance_ack_sha1: IDENTITY } } as FormField;
    expect(needsGuidanceAck(acked, ids, cur)).toBe(false);
    expect(effectiveStatus(acked, false, undefined, false)).toBe('complete');
  });

  it('does not leak the identity hash into any text a human reads', () => {
    const { container } = render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    expect(container.textContent ?? '').not.toContain(IDENTITY);
    expect(container.textContent ?? '').not.toContain('[identity:');
  });
});
