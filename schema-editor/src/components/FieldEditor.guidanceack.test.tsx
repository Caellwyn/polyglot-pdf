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

  it('a finding with an UNPARSEABLE identity renders no dead checkbox (Opus round)', () => {
    // Without a parseable identity the checkbox could record nothing
    // (withGuidanceAck without an identity is a no-op), leaving a control
    // that never ticks on a permanently amber field. Fail open instead,
    // matching needsGuidanceAck.
    const unparseable: LintFinding = {
      ...staleFinding, path: 'fields (id=phone).help',
    };
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[unparseable]} />,
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

describe('the DISPLAY pins to current identity too (round-3 regression)', () => {
  it('a stale ack from an EARLIER drift renders UNCHECKED, not already-confirmed', () => {
    // acked at H2, then edited again -- the backend now reports H3. A naive
    // "some ack exists" check rendered this ticked, telling the reviewer they
    // had already confirmed content they have never seen.
    const ackedAtOldIdentity = {
      ...FIELD, _review: { status: 'unreviewed', guidance_ack_sha1: 'OLD-H2' },
    } as FormField;
    render(
      <FieldEditor field={ackedAtOldIdentity} schema={makeSchema(ackedAtOldIdentity)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    const box = screen.getByTestId('guidance-ack-checkbox') as HTMLInputElement;
    expect(box.checked).toBe(false);                       // must re-ask
    const ta = screen.getByPlaceholderText(/Instructions for filling out this field/);
    expect(ta.className).toMatch(/ring-2/);                // and stay highlighted
    expect(screen.getByText(/Required before this field can be marked/))
      .toBeInTheDocument();
  });

  it('an ack for the CURRENT identity renders checked', () => {
    const ackedNow = {
      ...FIELD, _review: { status: 'unreviewed', guidance_ack_sha1: IDENTITY },
    } as FormField;
    render(
      <FieldEditor field={ackedNow} schema={makeSchema(ackedNow)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    expect((screen.getByTestId('guidance-ack-checkbox') as HTMLInputElement).checked)
      .toBe(true);
  });
});

describe('the flagged-reasons banner respects the ack (bd polyglot-pdf-hii0)', () => {
  // Post-ack, every other surface agreed the field was clear -- green row,
  // no amber ring, counted complete -- while the banner two inches above the
  // checkbox kept repeating the instruction the human had just carried out.
  // The reviewer could not tell whether their click registered.
  const banner = () => screen.queryByTestId('field-problems');

  it('drops the staleness line once the ack pins the CURRENT identity', () => {
    const acked = {
      ...FIELD, _review: { status: 'unreviewed', guidance_ack_sha1: IDENTITY },
    } as FormField;
    render(
      <FieldEditor field={acked} schema={makeSchema(acked)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    expect(banner()?.textContent ?? '').not.toContain(staleFinding.message);
  });

  it('still shows it when there is NO ack at all', () => {
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    expect(banner()?.textContent ?? '').toContain(staleFinding.message);
  });

  it('still shows it when the ack pins a SUPERSEDED identity', () => {
    // The whole point of pinning: an ack for older content is not a waiver
    // for the current content, so the banner must nag again.
    const staleAck = {
      ...FIELD, _review: { status: 'unreviewed', guidance_ack_sha1: 'OLD-H2' },
    } as FormField;
    render(
      <FieldEditor field={staleAck} schema={makeSchema(staleAck)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    expect(banner()?.textContent ?? '').toContain(staleFinding.message);
  });

  it('suppresses ONLY the staleness rule -- unrelated findings still render', () => {
    // Criterion 2: no other finding's banner behavior changes. This field
    // carries an ack AND an unrelated WARNING and ERROR; only the staleness
    // line may disappear.
    const acked = {
      ...FIELD, _review: { status: 'unreviewed', guidance_ack_sha1: IDENTITY },
    } as FormField;
    const otherWarning: LintFinding = {
      severity: 'WARNING', rule: 'help-details-oversize',
      path: 'fields (id=phone).help', message: 'details are oversize',
      field_id: 'phone',
    };
    const anError: LintFinding = {
      severity: 'ERROR', rule: 'field-unbacked',
      path: 'fields (id=phone)', message: 'no backing widget',
      field_id: 'phone',
    };
    render(
      <FieldEditor field={acked} schema={makeSchema(acked)}
        onUpdateField={vi.fn()} authorTier
        lintFindings={[staleFinding, otherWarning, anError]} />,
    );
    const text = banner()?.textContent ?? '';
    expect(text).not.toContain(staleFinding.message);
    expect(text).toContain('details are oversize');
    expect(text).toContain('no backing widget');
  });

  it('another field\'s acked staleness does not suppress THIS field\'s', () => {
    // The suppression is scoped by field_id, so a whole-schema findings list
    // cannot let one field's ack silence another field's warning.
    const otherFieldFinding: LintFinding = {
      severity: 'WARNING', rule: 'guidance-identity-stale',
      path: `fields (id=zip).help[identity:${IDENTITY}]`,
      message: 'zip changed since its guidance was written', field_id: 'zip',
    };
    const acked = {
      ...FIELD, _review: { status: 'unreviewed', guidance_ack_sha1: IDENTITY },
    } as FormField;
    render(
      <FieldEditor field={acked} schema={makeSchema(acked)}
        onUpdateField={vi.fn()} authorTier
        lintFindings={[staleFinding, otherFieldFinding]} />,
    );
    const text = banner()?.textContent ?? '';
    expect(text).not.toContain(staleFinding.message);
    expect(text).toContain('zip changed since its guidance was written');
  });
});
