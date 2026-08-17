/**
 * The retire suggestion is a SUGGESTION (bd polyglot-pdf-bdedm).
 *
 * Maintainer decision, 2026-08-07: the system finds candidates, a human makes
 * the call. Auto-retire was explicitly rejected because the available
 * same-form signals are unreliable -- form_number is not unique (a standard
 * W-7 and a firm's own variant share it) and labels are free text. A wrong
 * guess retires another firm's live form.
 *
 * These tests pin the two rules that follow: nothing is pre-selected, and
 * publishing without selecting is a first-class outcome rather than a cancel.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { RetireCandidatesDialog } from './RetireCandidatesDialog';
import type { RetireCandidate } from '../utils/remoteKitStore';

const CANDIDATES: RetireCandidate[] = [
  { kitId: 'w7-2024', label: 'W-7 (ITIN)', formNumber: 'W-7',
    edition: '12/2024', editionKind: 'edition_date', matchedOn: 'form_number' },
  { kitId: 'w7-firm', label: 'W-7 Firm Variant', formNumber: 'W-7',
    edition: '2026-01-01', editionKind: 'author_version', matchedOn: 'form_number' },
];

function open(overrides: { candidates?: RetireCandidate[]; busy?: boolean } = {}) {
  const onPublish = vi.fn();
  const onCancel = vi.fn();
  render(
    <RetireCandidatesDialog
      kitLabel="W-7 (2025)"
      candidates={CANDIDATES}
      onPublish={onPublish}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return { onPublish, onCancel };
}

describe('the retire suggestion never retires on its own', () => {
  it('pre-selects NOTHING', () => {
    // A pre-checked destructive default is an auto-retire wearing a
    // confirmation's clothes -- the exact thing the maintainer rejected.
    open();
    for (const radio of screen.getAllByRole('radio')) {
      expect((radio as HTMLInputElement).checked).toBe(false);
    }
  });

  it('publishes with NO replacement when nothing is selected', () => {
    // Publishing without retiring is a real outcome: the author may simply be
    // adding a form, and the suggestion may be wrong.
    const { onPublish } = open();

    fireEvent.click(screen.getByText('Publish, keep both'));

    expect(onPublish).toHaveBeenCalledWith(undefined);
  });

  it('sends ONLY the ticked kit id', () => {
    const { onPublish } = open();

    fireEvent.click(screen.getAllByRole('radio')[1]);
    fireEvent.click(screen.getByText('Publish and retire the old one'));

    expect(onPublish).toHaveBeenCalledWith('w7-firm');
  });

  it('is single-select, because the wire contract takes ONE replaces_kit_id', () => {
    // Checkboxes would let an author tick three and have two silently dropped.
    const { onPublish } = open();

    fireEvent.click(screen.getAllByRole('radio')[0]);
    fireEvent.click(screen.getAllByRole('radio')[1]);
    fireEvent.click(screen.getByText('Publish and retire the old one'));

    expect(onPublish).toHaveBeenCalledWith('w7-firm');
    expect(onPublish).toHaveBeenCalledTimes(1);
  });

  it('lets the author CLEAR a mis-click without losing the publish', () => {
    const { onPublish } = open();

    fireEvent.click(screen.getAllByRole('radio')[0]);
    fireEvent.click(screen.getByText('Clear selection'));
    fireEvent.click(screen.getByText('Publish, keep both'));

    expect(onPublish).toHaveBeenCalledWith(undefined);
  });

  it('cancels without publishing at all', () => {
    const { onPublish, onCancel } = open();

    fireEvent.click(screen.getByText('Cancel'));

    expect(onCancel).toHaveBeenCalled();
    expect(onPublish).not.toHaveBeenCalled();
  });
});

describe('the author can tell two candidates apart', () => {
  it('shows the id, the marker, and WHY each was suggested', () => {
    // form_number is not unique, so two candidates can look identical without
    // the kit id and the edition. The match reason matters too: a label guess
    // deserves more suspicion than a declared number.
    open();

    const first = screen.getByText('W-7 (ITIN)').closest('label') as HTMLElement;
    expect(within(first).getByText(/w7-2024/)).toBeTruthy();
    expect(within(first).getByText(/Edition\s*12\/2024/)).toBeTruthy();
    expect(within(first).getByText(/Same form number \(W-7\)/)).toBeTruthy();
  });

  it('labels an author-version marker as a Version, not an Edition', () => {
    open();

    const second = screen.getByText('W-7 Firm Variant').closest('label') as HTMLElement;
    expect(within(second).getByText(/Version\s*2026-01-01/)).toBeTruthy();
  });

  it('says when a suggestion came from the LABEL rather than a form number', () => {
    open({ candidates: [{ kitId: 'intake-old', label: 'Client Intake',
                          matchedOn: 'label' }] });

    expect(screen.getByText('Similar name')).toBeTruthy();
  });

  it('warns what retiring does, only once something is selected', () => {
    open();
    expect(screen.queryByText(/clients stop seeing it/i)).toBeNull();

    fireEvent.click(screen.getAllByRole('radio')[0]);

    expect(screen.getByText(/clients stop seeing it/i)).toBeTruthy();
  });
});
