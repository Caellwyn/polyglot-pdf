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

  it('an UNPARSEABLE identity fails open in the banner too (row parity)', () => {
    // needsGuidanceAck and the ack checkbox both fail open when the finding
    // carries no parseable identity: nothing can be pinned, so the row stays
    // green and no control renders. The banner must agree -- otherwise it
    // alone shows an amber warning beside a green row with no way to act on
    // it, which is the cross-surface contradiction this bead removes, on the
    // very surface it removes it from (Opus outer review, pass 2).
    const unparseable: LintFinding = {
      ...staleFinding, path: 'fields (id=phone).help',   // no [identity:...]
    };
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[unparseable]} />,
    );
    // no gate control...
    expect(screen.queryByTestId('guidance-ack-checkbox')).toBeNull();
    // ...and no banner line demanding one.
    expect(banner()?.textContent ?? '').not.toContain(unparseable.message);
  });

  it('THIS field\'s ack does not suppress ANOTHER field\'s staleness', () => {
    // The suppression is scoped by field_id, so a whole-schema findings list
    // cannot let one field's ack silence another field's warning. (The title
    // used to state the inverse direction of what is asserted below.)
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

// --- the OTHER way out of the gate (bd polyglot-pdf-cpiw) ------------------- //
//
// The gate offers "acknowledge it still reads correctly" (free) or "re-author
// it" (costly). Only the free half existed, so re-authoring meant hand-copying
// prose out of the IRS/USCIS instructions booklet. These pin the button that
// closes that gap.

describe('FieldEditor guidance regeneration (bd polyglot-pdf-cpiw)', () => {
  it('offers the rewrite button inside the staleness banner', () => {
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]}
        onRegenerateGuidance={vi.fn().mockResolvedValue(true)} />,
    );
    expect(screen.getByTestId('regenerate-guidance')).toBeInTheDocument();
  });

  it('calls back with THIS field id and shows progress while it runs', async () => {
    let release: (v: boolean) => void = () => {};
    const pending = new Promise<boolean>((res) => { release = res; });
    const onRegenerate = vi.fn().mockReturnValue(pending);
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]}
        onRegenerateGuidance={onRegenerate} />,
    );
    const btn = screen.getByTestId('regenerate-guidance');
    fireEvent.click(btn);
    expect(onRegenerate).toHaveBeenCalledWith('phone');
    // Disabled + progress copy while in flight, so a slow model call cannot be
    // double-submitted into two paid rewrites.
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    expect(btn.textContent).toMatch(/Rewriting/);
    release(true);
    await screen.findByText(/Or rewrite it from the instructions booklet/);
    expect((screen.getByTestId('regenerate-guidance') as HTMLButtonElement).disabled)
      .toBe(false);
  });

  it('shows the failure inline instead of losing it', async () => {
    const onRegenerate = vi.fn().mockRejectedValue(
      new Error('This form has no instructions booklet in its kit folder'));
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]}
        onRegenerateGuidance={onRegenerate} />,
    );
    fireEvent.click(screen.getByTestId('regenerate-guidance'));
    expect(await screen.findByText(/no instructions booklet/)).toBeInTheDocument();
    // and the button is usable again after the failure
    expect((screen.getByTestId('regenerate-guidance') as HTMLButtonElement).disabled)
      .toBe(false);
  });

  it('is absent without the callback (no backend / editor tier)', () => {
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]} />,
    );
    expect(screen.queryByTestId('regenerate-guidance')).toBeNull();
    // ...but the free half of the gate still stands.
    expect(screen.getByTestId('guidance-ack-checkbox')).toBeInTheDocument();
  });

  it('is absent when the field has NOT drifted (no banner to host it)', () => {
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[]}
        onRegenerateGuidance={vi.fn()} />,
    );
    expect(screen.queryByTestId('regenerate-guidance')).toBeNull();
  });

  it('says so when the rewrite changed NOTHING (not just on an error)', async () => {
    // A no-op resolves normally: the judge was unavailable, the guidance was
    // hand-edited (never clobbered), or the booklet had nothing for this
    // field. Without this the button just returns to idle and the amber banner
    // is still there -- the silent success-shaped no-op this bead exists to
    // remove (bd polyglot-pdf-cpiw).
    render(
      <FieldEditor field={FIELD} schema={makeSchema(FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[staleFinding]}
        onRegenerateGuidance={vi.fn().mockResolvedValue(false)} />,
    );
    fireEvent.click(screen.getByTestId('regenerate-guidance'));
    expect(await screen.findByText(/Nothing was rewritten/)).toBeInTheDocument();
  });
});
