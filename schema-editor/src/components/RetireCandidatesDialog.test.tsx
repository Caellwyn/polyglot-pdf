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

describe('it is actually a modal', () => {
  it('renders a real overlay, not phantom CSS class names', () => {
    // My first version used `modal-backdrop`/`modal-card`, which exist in NO
    // stylesheet -- so this rendered as an unstyled inline block with no
    // overlay, no centring, no card. Every test passed because JSDOM applies
    // no CSS (Opus fresh-eyes round 3).
    //
    // Asserting the utility classes the sibling dialogs use, because in a
    // Tailwind project those ARE the styling -- a class that does not exist
    // in the framework's output is indistinguishable from a typo at runtime.
    open();
    const backdrop = screen.getByRole('dialog');

    expect(backdrop.className).toContain('fixed');
    expect(backdrop.className).toContain('inset-0');
    expect(backdrop.className).toContain('z-50');
    // The dim: this is what physically covers the catalogue's Publish buttons.
    expect(backdrop.className).toMatch(/bg-black\//);
    expect(backdrop.className).not.toContain('modal-backdrop');
  });

  it('dismisses on a backdrop click, like its siblings', () => {
    const { onCancel } = open();

    fireEvent.mouseDown(screen.getByRole('dialog'));

    expect(onCancel).toHaveBeenCalled();
  });

  it('does NOT dismiss while a publish is running', () => {
    const { onCancel } = open({ busy: true });

    fireEvent.mouseDown(screen.getByRole('dialog'));

    expect(onCancel).not.toHaveBeenCalled();
  });
});

describe('every editionKind is labelled for what it IS', () => {
  // The whole justification for editionKind is that the UI can say "Edition
  // 12/2024" rather than a bare string the author has to interpret. Two of the
  // three branches had a named test; `published` had none -- deleting its
  // prefix, or relabelling it "Edition", left all 108 tests green.
  //
  // That is the branch for a kit with NO government edition date and no author
  // version: the firm-tier custom form this bead targets. Calling its publish
  // TIMESTAMP an "Edition" would tell an author a government edition exists,
  // on the one screen where misreading a candidate retires a live form
  // (Opus fresh-eyes round 9).
  it.each([
    ['edition_date', '12/2024', /Edition\s*12\/2024/, /Version|Published/],
    ['author_version', '2026-01-01', /Version\s*2026-01-01/, /Edition|Published/],
    ['published', '2026-02-03T10:00:00Z', /Published\s*2026-02-03/, /Edition|Version/],
  ])('labels %s as its own kind, not another', (kind, edition, expected, forbidden) => {
    open({ candidates: [{ kitId: 'k1', label: 'Firm Intake',
                          edition, editionKind: kind, matchedOn: 'label' }] });

    const row = screen.getByText('Firm Intake').closest('label') as HTMLElement;
    expect(within(row).getByText(expected)).toBeTruthy();
    // ...and is NOT labelled as one of the other two kinds.
    expect(row.textContent).not.toMatch(forbidden);
  });

  it('shows the marker even when the kind is unrecognised', () => {
    // Forward compatibility: a kind this build does not know still renders the
    // value rather than swallowing it, so the author sees SOMETHING to judge.
    open({ candidates: [{ kitId: 'k1', label: 'Firm Intake',
                          edition: '2026-05-05', editionKind: 'future_kind',
                          matchedOn: 'label' }] });

    const row = screen.getByText('Firm Intake').closest('label') as HTMLElement;
    expect(row.textContent).toContain('2026-05-05');
  });
});

describe('busy actually disables, it does not merely relabel', () => {
  // handleSetStatus has NO reentrancy guard of its own, and this dialog stays
  // mounted through the publish by design -- so these three `disabled={busy}`
  // gates are the ONLY barrier against a second concurrent publish, each
  // running the metered per-language translation sweep with racing metadata
  // and supersede writes.
  //
  // All three survived deletion with 112 tests green. The existing
  // "does NOT dismiss while a publish is running" test passes busy:true but
  // asserts only the backdrop path -- coverage in appearance, none in fact
  // (Opus fresh-eyes round 10).

  it('disables PUBLISH while a publish is running', () => {
    const { onPublish } = open({ busy: true });
    const btn = screen.getByText('Publishing...').closest('button') as HTMLButtonElement;

    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);

    expect(onPublish).not.toHaveBeenCalled();
  });

  it('disables CANCEL while a publish is running', () => {
    // Cancelling mid-publish would unmount the dialog while the request is in
    // flight, leaving the author with no indication it is still running.
    const { onCancel } = open({ busy: true });
    const btn = screen.getByText('Cancel').closest('button') as HTMLButtonElement;

    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);

    expect(onCancel).not.toHaveBeenCalled();
  });

  it('disables the candidate radios while a publish is running', () => {
    // Changing the selection mid-flight would leave the dialog showing a
    // choice that differs from the one actually being published.
    open({ busy: true });

    const radios = screen.getAllByRole('radio') as HTMLInputElement[];
    expect(radios.length).toBeGreaterThan(0);
    for (const radio of radios) {
      expect(radio.disabled).toBe(true);
    }
  });

  it('leaves all three ENABLED when no publish is running', () => {
    // The other direction: a busy gate that is always on is just a broken
    // dialog, and would pass every assertion above.
    const { onPublish } = open();

    const publish = screen.getByText('Publish, keep both').closest('button') as HTMLButtonElement;
    expect(publish.disabled).toBe(false);
    expect((screen.getByText('Cancel').closest('button') as HTMLButtonElement).disabled)
      .toBe(false);
    for (const radio of screen.getAllByRole('radio') as HTMLInputElement[]) {
      expect(radio.disabled).toBe(false);
    }
    fireEvent.click(publish);
    expect(onPublish).toHaveBeenCalled();
  });
});
