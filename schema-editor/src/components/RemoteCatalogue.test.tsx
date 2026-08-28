/**
 * RemoteCatalogue tests (bd polyglot-pdf-92qe.2): the hosted front door lists
 * kits from the editor API (drafts included -- the contractor work list), opens
 * a kit, flips status via the server (surfacing the promote-gate refusal), and
 * routes a 401 to the auth handler instead of a dead error banner.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  return {
    ...actual,
    listRemoteKits: vi.fn(),
    loadRemoteSchema: vi.fn(),
    setRemoteStatus: vi.fn(),
    fetchRetireCandidates: vi.fn(),
    deleteRemoteKit: vi.fn(),
    takeKitLock: vi.fn(),
    releaseKitLock: vi.fn(),
    setRemoteLabel: vi.fn(),
    onboardRemoteKit: vi.fn(),
    extractRemoteKit: vi.fn(),
    translateRemoteKitOptions: vi.fn(),
  };
});

import { RemoteCatalogue } from './RemoteCatalogue';
import {
  AuthError, ForbiddenError, extractRemoteKit, listRemoteKits, loadRemoteSchema,
  deleteRemoteKit,
  releaseKitLock, takeKitLock,
  onboardRemoteKit, setRemoteLabel, setRemoteStatus, translateRemoteKitOptions,
  fetchRetireCandidates,
  type RemoteKitEntry, type KitStatusResult, type RetireCandidate,
} from '../utils/remoteKitStore';

const KITS: RemoteKitEntry[] = [
  { id: 'done-kit', label: 'Done Form', status: 'complete', hasSchema: true,
    hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
  { id: 'draft-kit', label: 'Draft Form', status: 'draft', hasSchema: true,
    hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
  { id: 'fresh-kit', label: 'Fresh Form', status: 'draft', hasSchema: false,
    hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
];

// A minimal schema whose 1 field is incomplete -> a deterministic review %.
const SCHEMA = {
  fields: [{ id: 'f1', name: 'F1', type: 'text', pdf_field_name: 'F1[0]' }],
  sections: [],
} as never;

beforeEach(() => {
  vi.mocked(listRemoteKits).mockResolvedValue([...KITS]);
  // Every publish now asks this first (bd polyglot-pdf-bdedm). Default to "no
  // older versions" GLOBALLY, not per-describe: a bare vi.fn() resolves
  // undefined, and the caller reads .length off it, so an unmocked default
  // broke every publish test in the file.
  vi.mocked(fetchRetireCandidates).mockResolvedValue([]);
  vi.mocked(loadRemoteSchema).mockResolvedValue(SCHEMA);
  // Default: a clean complete flip with no drift (bd polyglot-pdf-783r). Tests
  // that exercise the drift notice / refusal override this per-case.
  vi.mocked(setRemoteStatus).mockResolvedValue({
    ok: true, status: 'complete', retranslated: 0, translationModel: null, supersededKitId: null });
});

afterEach(() => vi.clearAllMocks());

describe('RemoteCatalogue', () => {
  it('lists every kit from the API, drafts included', async () => {
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    expect(screen.getByText('Done Form')).toBeInTheDocument();
    expect(screen.getByText('Fresh Form')).toBeInTheDocument();
    // Aggregate summary reflects statuses (1 complete, 1 in progress, 1 awaiting).
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('3 forms');
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('1 complete');
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('1 in progress');
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('1 awaiting extraction');
  });

  it('opens a schema-bearing kit and disables a schemaless one', async () => {
    const onOpen = vi.fn();
    render(<RemoteCatalogue defaultExpanded onOpenKit={onOpen} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Draft Form'));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'draft-kit' }));

    const freshCard = screen.getByText('Fresh Form').closest('button');
    expect(freshCard).toBeDisabled();
  });

  it('shows the verify hint, NOT a percentage, for an unstamped kit (bd g687)', async () => {
    // Sprint-18 C4: the card reports the backend's readiness STAMP. The KITS
    // fixture carries none, so both schema kits must show the hint and NO
    // percentage. Critically it must NOT fall back to re-scanning the schema:
    // that fallback is what let a card and the open kit disagree (bd q3rm),
    // and a confident number nobody measured is the lie this bead ends.
    //
    // The schema below is FULLY REVIEWED on purpose. An unreviewed fixture
    // makes a re-scan compute 0%, which is too easy to confuse with "no number
    // rendered" -- a restored fallback survived that assertion (measured). A
    // 100%-reviewed schema makes the fallback produce a LOUD, unmistakable
    // "100%", so the no-fallback property is what actually gets pinned.
    vi.mocked(loadRemoteSchema).mockResolvedValue({
      fields: [{
        id: 'f1', name: 'F1', type: 'text', spoken_name: 'f',
        pdf_field_name: 'F1[0]', help: { instructions: 'x' },
        _review: { status: 'reviewed_correct' },
      }],
      sections: [],
    } as never);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getAllByTestId('readiness-hint').length).toBe(2));
    // No percentage of ANY value reached the cards -- not the re-scan's 100%,
    // not a 0%, nothing. Asserting the absence of the whole class beats
    // blacklisting one value.
    expect(screen.queryByText(/^\d+%$/)).not.toBeInTheDocument();
    // The compact STRIP says why too, in its terse register: withholding the
    // number alone left the collapsed default view unexplained (both Opus
    // outer reviewers). Every listed schema-bearing kit is unstamped here.
    const kitOptions = screen.getAllByRole('option')
      .map((o) => o.textContent ?? '')
      .filter((t) => t.includes(' -- '))          // skip the "Select a form..." placeholder
      .filter((t) => !t.includes('no schema yet'));  // nothing to measure
    expect(kitOptions.length).toBe(2);
    for (const text of kitOptions) expect(text).toContain('not measured');
  });

  it('renders the stamped percentage when the stamp is verified (bd g687)', async () => {
    // The number comes from the STAMP the backend wrote with publish_readiness
    // -- the same definition the open editor's strip mirrors -- never from a
    // client-side re-derivation.
    vi.mocked(listRemoteKits).mockResolvedValue(KITS.map((k) => (
      k.hasSchema
        ? { ...k, readiness: {
            reviewed: 3, toReview: 1, total: 4, errors: 0, percent: 75,
            ready: false, verified: true, schemaSha1: 'abc123',
          } }
        : k
    )));
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getAllByText('75%').length).toBe(2));
    expect(screen.queryByTestId('readiness-hint')).not.toBeInTheDocument();
  });

  it('a 199-of-200 kit shows a YELLOW bar, not a green 100% one (bd polyglot-pdf-87zbs)', async () => {
    // pct is a ROUNDED percentage (Math.round(199/200*100) === 100), so a
    // predicate keyed on pct===100 alone paints a confident green "finished"
    // bar on a kit that still has 1 unreviewed field -- directly contradicting
    // this same card's own hover title ("199 of 200 fields complete") right
    // next to it, and the publish gate that will still refuse it.
    vi.mocked(listRemoteKits).mockResolvedValue(KITS.map((k) => (
      k.hasSchema
        ? { ...k, readiness: {
            reviewed: 199, toReview: 0, total: 200, errors: 0, percent: 100,
            ready: false, verified: true, schemaSha1: 'abc123',
          } }
        : k
    )));
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getAllByText('100%').length).toBe(2));

    const bars = document.querySelectorAll('.h-full');
    const progressBars = Array.from(bars).filter((el) =>
      el.className.includes('bg-green-500') || el.className.includes('bg-yellow-500'));
    expect(progressBars.length).toBe(2);
    for (const bar of progressBars) {
      expect(bar.className).toContain('bg-yellow-500');
      expect(bar.className).not.toContain('bg-green-500');
    }
  });

  it('a genuinely complete (200-of-200) kit still shows a GREEN bar', async () => {
    // Regression guard for the fix above: the exact-ratio predicate must
    // still recognize TRUE completion, not just stop recognizing 100%.
    vi.mocked(listRemoteKits).mockResolvedValue(KITS.map((k) => (
      k.hasSchema
        ? { ...k, readiness: {
            reviewed: 200, toReview: 0, total: 200, errors: 0, percent: 100,
            ready: true, verified: true, schemaSha1: 'abc123',
          } }
        : k
    )));
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getAllByText('100%').length).toBe(2));

    const bars = document.querySelectorAll('.h-full');
    const progressBars = Array.from(bars).filter((el) =>
      el.className.includes('bg-green-500') || el.className.includes('bg-yellow-500'));
    expect(progressBars.length).toBe(2);
    for (const bar of progressBars) {
      expect(bar.className).toContain('bg-green-500');
    }
  });

  it('an UNREADABLE schema shows the corruption notice, never a stamped % (bd g687)', async () => {
    // A stamp measured an EARLIER, readable schema. If schema.json later
    // becomes corrupt, the card must say so -- not print the old stamp's
    // confident percentage while swallowing the notice. This regressed when
    // pct stopped coming from the same scan that sets schemaError (Opus
    // fresh-eyes round 3).
    vi.mocked(listRemoteKits).mockResolvedValue(KITS.map((k) => (
      k.hasSchema
        ? { ...k, readiness: {
            reviewed: 3, toReview: 1, total: 4, errors: 0, percent: 75,
            ready: false, verified: true, schemaSha1: 'abc123',
          } }
        : k
    )));
    // The schema fetch fails -> schemaError for both schema-bearing kits.
    vi.mocked(loadRemoteSchema).mockResolvedValue(null as never);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getAllByText(/Schema present but unreadable/).length).toBe(2));
    // ...and the stale stamp's number is nowhere on the card.
    expect(screen.queryByText('75%')).not.toBeInTheDocument();
    // ...nor in the compact STRIP dropdown, which round 3 missed entirely
    // (Opus fresh-eyes round 4): it is the DEFAULT view, so a confident number
    // there is the first thing a user sees, contradicting the card below it.
    for (const opt of screen.queryAllByRole('option')) {
      expect(opt.textContent ?? '').not.toMatch(/\d+%/);
    }
  });

  it('an UNVERIFIED stamp shows the hint, never its percentage (bd g687)', async () => {
    // verified:false means the counts were computed with no usable lint
    // report. The counts may look complete, but presenting 100% as checked is
    // exactly the confident-then-409 lie the epic exists to end -- so the
    // number is withheld even though the stamp carries one.
    vi.mocked(listRemoteKits).mockResolvedValue(KITS.map((k) => (
      k.hasSchema
        ? { ...k, readiness: {
            reviewed: 4, toReview: 0, total: 4, errors: 0, percent: 100,
            ready: true, verified: false, schemaSha1: 'abc123',
          } }
        : k
    )));
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getAllByTestId('readiness-hint').length).toBe(2));
    expect(screen.queryByText('100%')).not.toBeInTheDocument();
  });

  it('marks a draft complete via the server and refreshes', async () => {
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(within(
      screen.getByText('Draft Form').closest('li') as HTMLElement,
    ).getByText('Publish'));
    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalledWith('draft-kit', 'complete', {}));
    // Refresh happened (list re-requested).
    await waitFor(() => expect(vi.mocked(listRemoteKits).mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => expect(screen.getByText(/marked complete/)).toBeInTheDocument());
  });

  it('notes the drift sweep in the complete notice when it re-translated (bd 783r)', async () => {
    vi.mocked(setRemoteStatus).mockResolvedValue({
      ok: true, status: 'complete', retranslated: 3, translationModel: 'gemini-2.5-pro', supersededKitId: null });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(within(
      screen.getByText('Draft Form').closest('li') as HTMLElement,
    ).getByText('Publish'));
    await waitFor(() =>
      expect(screen.getByText(/Refreshed 3 translation entries/)).toBeInTheDocument());
  });

  it('surfaces the incomplete-translation refusal (409 "N of M") as the error banner (bd 783r)', async () => {
    vi.mocked(setRemoteStatus).mockRejectedValue(
      new Error('10 of 17 language translations complete. Please try again later to finish (retrying only the missing ones).'),
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(within(
      screen.getByText('Draft Form').closest('li') as HTMLElement,
    ).getByText('Publish'));
    await waitFor(() =>
      expect(screen.getByText(/10 of 17 language translations complete/)).toBeInTheDocument());
  });

  it('surfaces the promote-gate refusal detail (422) as the error banner', async () => {
    vi.mocked(setRemoteStatus).mockRejectedValue(
      new Error('Schema does not validate against the form contract'),
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(within(
      screen.getByText('Draft Form').closest('li') as HTMLElement,
    ).getByText('Publish'));
    await waitFor(() =>
      expect(screen.getByText(/does not validate/)).toBeInTheDocument());
  });

  it('mirrors the OPEN kit\'s Mark-complete refusal up through onStatusRefusal, and clears it on the next attempt (s18 C1)', async () => {
    // The producer side of the strip's refusal line (decision 1): a refused
    // completion of the OPEN kit reaches the host with the server's detail;
    // a later attempt clears the stale refusal first (null) before the call.
    const onStatusRefusal = vi.fn();
    vi.mocked(setRemoteStatus).mockRejectedValueOnce(
      new Error('Schema has 1 lint error(s), so it cannot be marked complete'),
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
      selectedKitId="draft-kit" role="author" onStatusRefusal={onStatusRefusal} />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    // The OPEN kit's Mark complete renders twice (compact selector + its own
    // card); both drive the same kit, so either button exercises the mirror.
    fireEvent.click(screen.getAllByText('Publish')[0]);
    await waitFor(() => expect(onStatusRefusal).toHaveBeenCalledWith(
      expect.stringContaining('cannot be marked complete')));
    // Called with null FIRST on entry (stale refusal cleared before the call).
    expect(onStatusRefusal.mock.calls[0]).toEqual([null]);

    // The retry succeeds (the once-rejection is spent): only the clear fires.
    onStatusRefusal.mockClear();
    fireEvent.click(screen.getAllByText('Publish')[0]);
    await waitFor(() => expect(screen.getByText(/marked complete/)).toBeInTheDocument());
    expect(onStatusRefusal).toHaveBeenCalledWith(null);
    expect(onStatusRefusal).not.toHaveBeenCalledWith(expect.stringContaining('cannot'));
  });

  it('a refusal about a NON-open kit never reaches the strip (Opus outer r3)', async () => {
    // The EXPANDED card grid offers Mark complete on every schema-bearing
    // card, so a refusal about another kit must stay on its card -- mirrored
    // onto the open kit's strip, its "Go to:" links would name fields the
    // open kit does not have (same gate FormCatalogue's local cards carry).
    const onStatusRefusal = vi.fn();
    vi.mocked(setRemoteStatus).mockRejectedValue(
      new Error('refused: fields (id=other_field)'),
    );
    // done-kit is the OPEN kit; draft-kit's card is the one clicked.
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
      selectedKitId="done-kit" role="author" onStatusRefusal={onStatusRefusal} />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(within(
      screen.getByText('Draft Form').closest('li') as HTMLElement,
    ).getByText('Publish'));
    // The refused call ran for the NON-open kit...
    await waitFor(() => expect(setRemoteStatus)
      .toHaveBeenCalledWith('draft-kit', 'complete', {}));
    // ...but the strip mirror was never touched (no clear, no detail).
    expect(onStatusRefusal).not.toHaveBeenCalled();
  });

  it('routes a 401 to onAuthError instead of the error banner', async () => {
    vi.mocked(listRemoteKits).mockRejectedValue(new AuthError());
    const onAuthError = vi.fn();
    render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId={null} role="editor"
        onAuthError={onAuthError}
      />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
    expect(screen.queryByText(/Invalid or missing/)).not.toBeInTheDocument();
  });

  // A 403 (a real account whose editor role was revoked) must route the SAME
  // way as a 401 -- otherwise every catalogue action dead-ends on an error
  // banner the person cannot act on, instead of reaching the refused screen.
  // The ERROR ITSELF is forwarded, since App tells the two apart by type.
  it('routes a 403 to onAuthError, carrying the error so App can tell it apart', async () => {
    const refusal = new ForbiddenError('This account does not have schema editor access');
    vi.mocked(listRemoteKits).mockRejectedValue(refusal);
    const onAuthError = vi.fn();
    render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId={null} role="editor"
        onAuthError={onAuthError}
      />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalledWith(refusal));
  });

  it('routes a 401 DURING THE PROGRESS SCAN to onAuthError, not a schema error', async () => {
    // The list call succeeds, but the code is revoked before the per-kit
    // schema fetches -- the auth state must reach onAuthError, never masquerade
    // as "schema unreadable" on every card (fresh-eyes gap 1).
    vi.mocked(loadRemoteSchema).mockRejectedValue(new AuthError());
    const onAuthError = vi.fn();
    render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId={null} role="editor"
        onAuthError={onAuthError}
      />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
    expect(screen.queryByText(/unreadable/)).not.toBeInTheDocument();
  });

  it('a plain per-kit schema failure still shows the unreadable notice (not auth)', async () => {
    vi.mocked(loadRemoteSchema).mockRejectedValue(new Error('boom'));
    const onAuthError = vi.fn();
    render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId={null} role="editor"
        onAuthError={onAuthError}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByText(/unreadable/).length).toBeGreaterThan(0));
    expect(onAuthError).not.toHaveBeenCalled();
  });

  it('shows the empty-workspace message when the store has no kits', async () => {
    vi.mocked(listRemoteKits).mockResolvedValue([]);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByText(/workspace is empty/)).toBeInTheDocument());
  });
});

describe('RemoteCatalogue Codex r1 fixes (PR #280)', () => {
  it('remembers a SAVED kit progress after it stops being the live one', async () => {
    const { rerender } = render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId="draft-kit" role="editor"
        liveProgress={{ kitId: 'draft-kit', saved: true, percent: 93, complete: 93, total: 100 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('93%')).toBeInTheDocument());
    // The kit closes (liveProgress gone) -- the saved value must survive, not
    // revert to the mount-time scan (0%).
    rerender(
      <RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />,
    );
    expect(screen.getByText('93%')).toBeInTheDocument();
  });

  it('never remembers UNSAVED live progress', async () => {
    const { rerender } = render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId="draft-kit" role="editor"
        liveProgress={{ kitId: 'draft-kit', saved: false, percent: 93, complete: 93, total: 100 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('93%')).toBeInTheDocument());
    rerender(
      <RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />,
    );
    // Discarded edit -> back to the scan value, no phantom 93%.
    await waitFor(() => expect(screen.queryByText('93%')).not.toBeInTheDocument());
  });

  it('blocks Mark complete while the open kit has unsaved edits', async () => {
    render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId="draft-kit" role="author"
        liveProgress={{ kitId: 'draft-kit', saved: false, percent: 50, complete: 1, total: 2 }}
      />,
    );
    // The selected kit's Mark-complete renders in BOTH the compact strip and
    // its card (bd tynm) -- the unsaved-edits guard must hold on every copy.
    await waitFor(() => expect(screen.getAllByText('Publish').length).toBeGreaterThan(0));
    for (const btn of screen.getAllByText('Publish')) {
      expect(btn).toBeDisabled();
      expect(btn).toHaveAttribute('title', expect.stringContaining('Save your changes first'));
      fireEvent.click(btn);
    }
    expect(setRemoteStatus).not.toHaveBeenCalled();
  });

  it('allows Mark complete once the open kit is saved', async () => {
    render(
      <RemoteCatalogue
        defaultExpanded
        onOpenKit={() => {}} selectedKitId="draft-kit" role="author"
        liveProgress={{ kitId: 'draft-kit', saved: true, percent: 100, complete: 2, total: 2 }}
      />,
    );
    await waitFor(() => expect(screen.getAllByText('Publish').length).toBeGreaterThan(0));
    for (const btn of screen.getAllByText('Publish')) {
      expect(btn).not.toBeDisabled();
    }
  });
});

describe('RemoteCatalogue Codex r2 fixes (PR #280)', () => {
  it('a schema whose fields entries are not objects surfaces as unreadable', async () => {
    // fields IS an array, but of junk -- must not "measure" as a bogus 0%.
    vi.mocked(loadRemoteSchema).mockResolvedValue(
      { fields: ['not', 'objects'], sections: [] } as never,
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getAllByText(/unreadable/).length).toBeGreaterThan(0));
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });
});

describe('RemoteCatalogue author tier (bd 92qe.3)', () => {
  it('editor role sees neither the upload nor the extraction controls', async () => {
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Fresh Form')).toBeInTheDocument());
    expect(screen.queryByText('Add a form (PDF)')).not.toBeInTheDocument();
    expect(screen.queryByText('Run extraction')).not.toBeInTheDocument();
  });

  it('author uploads a PDF -> onboard + refresh + notice', async () => {
    vi.mocked(onboardRemoteKit).mockResolvedValue({
      id: 'new-kit', label: 'New Kit', status: 'draft', hasSchema: false,
      hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf',
    });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Add a form (PDF)')).toBeInTheDocument());

    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], 'Form W-7.pdf',
      { type: 'application/pdf' });
    fireEvent.change(screen.getByTestId('upload-pdf-input'), { target: { files: [file] } });

    await waitFor(() => expect(onboardRemoteKit).toHaveBeenCalledWith(file));
    await waitFor(() =>
      expect(screen.getByText(/Added "new-kit"/)).toBeInTheDocument());
    expect(vi.mocked(listRemoteKits).mock.calls.length).toBeGreaterThan(1); // refreshed
  });

  it('author uploading a non-PDF is refused client-side', async () => {
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Add a form (PDF)')).toBeInTheDocument());
    const bad = new File([new Uint8Array([1])], 'page.html', { type: 'text/html' });
    fireEvent.change(screen.getByTestId('upload-pdf-input'), { target: { files: [bad] } });
    await waitFor(() =>
      expect(screen.getByText(/Pick an AcroForm PDF/)).toBeInTheDocument());
    expect(onboardRemoteKit).not.toHaveBeenCalled();
  });

  it('author runs extraction on a schemaless kit -> server call + notice', async () => {
    vi.mocked(extractRemoteKit).mockResolvedValue({
      ok: true, detail: '[OK] wrote schema.json -- 42 fields', fieldCount: 42,
    });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(extractRemoteKit).toHaveBeenCalledWith(
      'fresh-kit', { instructionsPdf: undefined, translateOptions: true,
        enrichGuidance: true }));
    await waitFor(() =>
      expect(screen.getByText(/Extracted "fresh-kit"/)).toBeInTheDocument());
  });

  it('unchecking the translate-options checkbox threads false (bd 2h9j)', async () => {
    vi.mocked(extractRemoteKit).mockResolvedValue({
      ok: true, detail: '[OK] wrote schema.json -- 42 fields', fieldCount: 42,
    });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeInTheDocument());

    const checkbox = screen.getByTestId('translate-options-checkbox');
    expect(checkbox).toBeChecked(); // default ON
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(extractRemoteKit).toHaveBeenCalledWith(
      'fresh-kit', { instructionsPdf: undefined, translateOptions: false,
        enrichGuidance: true }));
  });

  it('unchecking the enrich-guidance checkbox threads false (bd wsao.6)', async () => {
    vi.mocked(extractRemoteKit).mockResolvedValue({
      ok: true, detail: '[OK] wrote schema.json -- 42 fields', fieldCount: 42,
    });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('enrich-guidance-checkbox'));
    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(extractRemoteKit).toHaveBeenCalledWith(
      'fresh-kit', { instructionsPdf: undefined, translateOptions: true,
        enrichGuidance: false }));
  });

  it('store-with-issues extraction surfaces the lint counts (bd v96b)', async () => {
    vi.mocked(extractRemoteKit).mockResolvedValue({
      ok: true, detail: '[ISSUES] wrote schema.json -- 42 fields', fieldCount: 42,
      storedWithIssues: true, errorCount: 3, warningCount: 1,
    });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() =>
      expect(screen.getByText(/with issues \(3 errors, 1 warning\)/)).toBeInTheDocument());
    expect(screen.getByText(/repair before marking complete/)).toBeInTheDocument();
  });

  it('extraction failure surfaces the server detail', async () => {
    vi.mocked(extractRemoteKit).mockRejectedValue(
      new Error('Extraction failed (exit 1): model refused'),
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() =>
      expect(screen.getByText(/model refused/)).toBeInTheDocument());
  });
});

describe('RemoteCatalogue extraction progress state (fresh-eyes 92qe.3)', () => {
  it('shows the elapsed ticker and disables controls while extracting', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let resolveExtract: (r: { ok: boolean; detail: string }) => void = () => {};
    vi.mocked(extractRemoteKit).mockImplementation(
      () => new Promise((res) => { resolveExtract = res; }),
    );
    try {
      render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
      await waitFor(() => expect(screen.getByText('Run extraction')).toBeInTheDocument());

      fireEvent.click(screen.getByText('Run extraction'));
      // Mid-flight: the button shows the elapsed ticker...
      await waitFor(() =>
        expect(screen.getByText(/Extracting\.\.\. \d+s/)).toBeInTheDocument());
      // ...and the header controls are disabled while it runs.
      expect(screen.getByText('Refresh')).toBeDisabled();
      expect(screen.getByText('Add a form (PDF)')).toBeDisabled();

      resolveExtract({ ok: true, detail: '[OK] wrote schema.json -- 7 fields' });
      await waitFor(() =>
        expect(screen.getByText(/Extracted "fresh-kit"/)).toBeInTheDocument());
      expect(screen.queryByText(/Extracting\.\.\./)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('RemoteCatalogue mark-complete drift-sweep ticker (bd 783r)', () => {
  it('shows the re-translating ticker while the complete sweep runs, then reverts', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let resolveStatus: (r: KitStatusResult) => void = () => {};
    vi.mocked(setRemoteStatus).mockImplementation(
      () => new Promise((res) => { resolveStatus = res; }),
    );
    try {
      render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="author" />);
      await waitFor(() => expect(within(
        screen.getByText('Draft Form').closest('li') as HTMLElement,
      ).getByText('Publish')).toBeInTheDocument());

      fireEvent.click(within(
        screen.getByText('Draft Form').closest('li') as HTMLElement,
      ).getByText('Publish'));
      // Mid-flight: the button shows the elapsed re-translating ticker (the
      // sweep can take tens of seconds -- a dead button would read as a hang).
      await waitFor(() =>
        expect(screen.getByText(/Re-translating & validating\.\.\. \d+s/)).toBeInTheDocument());

      resolveStatus({
        ok: true, status: 'complete', retranslated: 2, translationModel: 'gemini-2.5-pro', supersededKitId: null });
      await waitFor(() =>
        expect(screen.getByText(/marked complete/)).toBeInTheDocument());
      // Ticker gone once the flip resolved.
      expect(screen.queryByText(/Re-translating & validating\.\.\./)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('compact selector strip (bd tynm)', () => {
  it('collapses the card grid by default; the dropdown lists every kit', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByLabelText('Select a form')).toBeInTheDocument());
    // No card buttons in the collapsed default -- just the dropdown options.
    expect(screen.queryByTitle('Open Draft Form for editing')).not.toBeInTheDocument();
    const select = screen.getByLabelText('Select a form') as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.text);
    expect(labels.some((t) => t.includes('Draft Form'))).toBe(true);
    expect(labels.some((t) => t.includes('Fresh Form') && t.includes('no schema yet'))).toBe(true);
  });

  it('selecting a schema-bearing kit opens it; a schemaless kit only selects', async () => {
    const onOpen = vi.fn();
    render(<RemoteCatalogue onOpenKit={onOpen} selectedKitId={null} role="author" />);
    await waitFor(() =>
      expect(screen.getByLabelText('Select a form')).toBeInTheDocument());
    const select = screen.getByLabelText('Select a form');

    fireEvent.change(select, { target: { value: 'draft-kit' } });
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'draft-kit' }));

    onOpen.mockClear();
    fireEvent.change(select, { target: { value: 'fresh-kit' } });
    expect(onOpen).not.toHaveBeenCalled();
    // ...but the schemaless kit's Run extraction is reachable from the strip.
    expect(screen.getByText('Run extraction')).toBeInTheDocument();
  });

  it('never offers Mark complete for a schema kit whose open was not confirmed', async () => {
    // The open is async and can FAIL: selecting a kit sets the strip's local
    // selection optimistically, but status-changing actions must only render
    // once the parent confirms the open (selectedKitId). Here the parent never
    // opens it (onOpenKit no-ops), so no Mark complete may appear (fresh-eyes,
    // bd tynm: a failed open must not leave the strip offering to complete an
    // unreviewed kit).
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() =>
      expect(screen.getByLabelText('Select a form')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Select a form'), {
      target: { value: 'draft-kit' },
    });
    expect(screen.queryByText('Publish')).not.toBeInTheDocument();
    expect(screen.queryByText('Submit for review')).not.toBeInTheDocument();
    expect(screen.queryByText('Revert to draft')).not.toBeInTheDocument();
  });

  it('the toggle expands the full card grid and collapses it again', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Show form cards'));
    expect(screen.getByTitle('Open Draft Form for editing')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Hide form cards'));
    expect(screen.queryByTitle('Open Draft Form for editing')).not.toBeInTheDocument();
  });
});

describe('author version prompt on publish (bd polyglot-pdf-xzw5)', () => {
  const REFUSAL = 'AUTHOR_VERSION_REQUIRED: this form has no government edition '
    + 'date, so it needs an author version to identify which revision a client '
    + 'confirmed against.';

  async function publishDraftKit() {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Show form cards'));
    // Scope to the CARD: 'Publish' renders in the strip too now, so an index
    // would pick whichever happens to come first in the DOM.
    const card = screen.getByText('Draft Form').closest('li') as HTMLElement;
    fireEvent.click(within(card).getByText('Publish'));
  }

  it('opens the version dialog when the publish gate asks for one', async () => {
    // The catalogue listing does not read schemas, so it CANNOT know a kit
    // needs a version -- the server's refusal is the trigger. Keying on the
    // machine-readable token keeps the rule in one place.
    vi.mocked(setRemoteStatus).mockRejectedValueOnce(new Error(REFUSAL));
    await publishDraftKit();

    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());
    // The raw refusal is NOT dumped on the card -- the dialog replaces it.
    expect(screen.queryByText(/AUTHOR_VERSION_REQUIRED/)).not.toBeInTheDocument();
  });

  it('does not start a SECOND publish while the lookup is in flight', async () => {
    // The buttons are gated on busy/completingId, but those are set inside
    // handleSetStatus -- which now runs only AFTER the candidate lookup
    // resolves. Without a pending flag set before the await, every click
    // during the lookup starts its own publish, each running the METERED
    // per-language sweep with racing writes.
    //
    // This fix was made in round 1, LOST to a git checkout during my own
    // mutation testing, and reproduced by round 2. It was invisible because
    // nothing pinned it -- so this test exists as much for the regression as
    // for the bug.
    let release: (v: RetireCandidate[]) => void = () => {};
    vi.mocked(fetchRetireCandidates).mockReturnValue(
      new Promise<RetireCandidate[]>((res) => { release = res; }));
    await publishDraftKit();

    // The button is DISABLED while the lookup runs -- which is the fix, and
    // is why there is no second "Publish" to click. Assert the guard rather
    // than a click count: a count test would pass just as well if the button
    // were merely slow to re-render.
    const card = screen.getByText('Draft Form').closest('li') as HTMLElement;
    await waitFor(() =>
      expect(within(card).queryByText('Publish')).not.toBeInTheDocument());

    release([]);

    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalled());
    expect(setRemoteStatus).toHaveBeenCalledTimes(1);
    // ...and the button comes back afterwards, so a failed lookup cannot
    // strand the catalogue disabled.
    await waitFor(() =>
      expect(within(card).getByText('Publish')).toBeInTheDocument());
  });

  it('keeps the retire dialog OPEN while the publish runs', async () => {
    // Publish takes tens of seconds (the per-language sweep). Dismissing the
    // dialog first made its busy guard dead code and dropped the author back
    // to an unchanged catalogue with an enabled Publish button -- the exact
    // failure AuthorVersionDialog's deferred unmount exists to prevent.
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'old-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    let finish: (v: KitStatusResult) => void = () => {};
    vi.mocked(setRemoteStatus).mockReturnValue(
      new Promise<KitStatusResult>((res) => { finish = res; }));
    await publishDraftKit();

    await waitFor(() => expect(screen.getByText('Client Intake')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Publish, keep both'));

    // Still mounted, and showing progress, while the publish is in flight.
    await waitFor(() => expect(screen.getByText('Publishing...')).toBeInTheDocument());

    finish({ ok: true, status: 'complete', retranslated: 0,
             translationModel: null, supersededKitId: null });
    await waitFor(() =>
      expect(screen.queryByText('Client Intake')).not.toBeInTheDocument());
  });

  it.each([
    ['done-kit', 'Done Form', 'Revert to draft'],
  ])('the REPUBLISH path asks about older versions too', async () => {
    // A retired form returning to service is precisely when a same-form live
    // kit exists, so this is the highest-value path -- and it was the one with
    // no coverage: reverting its wiring left 80/80 green (Opus fresh-eyes
    // round 2).
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'done-kit' ? { ...k, status: 'unpublished' } : k)));
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'other-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
                            selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Done Form')).toBeInTheDocument());

    const card = screen.getByText('Done Form').closest('li') as HTMLElement;
    fireEvent.click(within(card).getByText('Publish again'));

    await waitFor(() => expect(fetchRetireCandidates).toHaveBeenCalledWith('done-kit'));
    expect(setRemoteStatus).not.toHaveBeenCalled();
  });

  it('the STRIP republish button asks too (the twin)', async () => {
    // Every publish control in this file exists twice -- compact strip and
    // expanded card. Four separate times on this bead a mutation "survived"
    // only because I had reverted the twin the test does not click. Each twin
    // gets its own click.
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'done-kit' ? { ...k, status: 'unpublished' } : k)));
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'other-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    // Strip only -- no card grid.
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="done-kit"
                            role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Publish again'));

    await waitFor(() => expect(fetchRetireCandidates).toHaveBeenCalledWith('done-kit'));
  });

  it('the STRIP submitted-kit Publish asks too (the last unpinned twin)', async () => {
    // The one publish site of six with no test: reverting it left 85/85 green.
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'draft-kit' ? { ...k, status: 'submitted' } : k)));
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'other-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="draft-kit"
                            role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Publish'));

    await waitFor(() => expect(fetchRetireCandidates).toHaveBeenCalledWith('draft-kit'));
  });

  it.each([
    ['the compact strip', false],
    ['the expanded card grid', true],
  ])('freezes the PUBLISH controls in %s while the dialog is open', async (_name, expand) => {
    // Not one button: the whole set, in BOTH views. Nine of the ten original
    // gates could be deleted with the suite green, because the only test
    // clicked a single card button -- the twin-shaped miss, now inside the fix
    // for the twin-shaped miss (Opus fresh-eyes round 4).
    //
    // Hand-lists four labels -- it does NOT auto-cover a control added later,
    // and an earlier version of this comment claimed it did, which is exactly
    // the kind of promise that stops the next author adding a case. The
    // all-four-statuses test above is the one with a census assertion; this
    // one is the per-view check.
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'done-kit' ? { ...k, status: 'complete' } : k)));
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'done-kit', label: 'Done Form', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue defaultExpanded={expand} onOpenKit={() => {}}
                            selectedKitId="draft-kit" role="author" />);
    // Wait on a control that exists in BOTH views: the strip renders kits as
    // <select> options (not text) and the toggle's label flips with the view,
    // so either would be a view-dependent anchor.
    await waitFor(() =>
      expect(screen.getAllByText('Publish').length).toBeGreaterThan(0));

    fireEvent.click(screen.getAllByText('Publish')[0]);
    await waitFor(() => expect(screen.getByText('Done Form')).toBeInTheDocument());

    // Every control that CHANGES a kit's status must be inert behind the
    // dialog -- otherwise the candidate list goes stale under the author, or
    // two publishes race, each running the metered per-language sweep.
    for (const label of ['Publish', 'Publish again', 'Revert to draft', 'Unpublish']) {
      for (const el of screen.queryAllByText(label)) {
        const btn = el.closest('button') as HTMLButtonElement | null;
        // Buttons INSIDE the dialog are the point of the dialog; skip them.
        if (!btn || btn.closest('[role="dialog"]')) continue;
        expect(btn.disabled).toBe(true);
      }
    }
  });

  // The STRIP renders controls for the SELECTED kit only, so its branch is
  // decided by that kit's status -- one selection exercises ONE strip branch.
  // Selecting a single kit is why the grid covered four statuses while the
  // strip covered one, and why three strip gates survived four rounds of
  // fixes (Opus fresh-eyes round 8). Parametrized over the selection.
  it.each([
    ['live-kit', 'complete'],
    ['retired-kit', 'unpublished'],
    ['review-kit', 'submitted'],
    ['wip-kit', 'draft'],
  ])('freezes EVERY status control with a %s (%s) kit selected', async (selectedId) => {
    // The root cause of four rounds of the same hole: the shared KITS fixture
    // has only `complete` and `draft` kits, so no `unpublished` or `submitted`
    // card ever renders -- and 8 of the 14 freeze gates live on exactly those
    // two statuses. They were unreachable by any test, so each round's fix
    // covered a different subset and the rest stayed deletable with the whole
    // suite green (Opus fresh-eyes round 7).
    //
    // A local fixture rather than widening KITS, which 100+ other tests rely
    // on. Every status is present, so every gate is reachable.
    const ALL_STATUSES: RemoteKitEntry[] = [
      { id: 'live-kit', label: 'Live Form', status: 'complete', hasSchema: true,
        hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
      { id: 'retired-kit', label: 'Retired Form', status: 'unpublished', hasSchema: true,
        hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
      { id: 'review-kit', label: 'Review Form', status: 'submitted', hasSchema: true,
        hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
      { id: 'wip-kit', label: 'WIP Form', status: 'draft', hasSchema: true,
        hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
    ];
    vi.mocked(listRemoteKits).mockResolvedValue(ALL_STATUSES);
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'live-kit', label: 'Live Form', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
                            selectedKitId={selectedId} role="author" />);
    const cards = await screen.findByRole('list');
    await waitFor(() =>
      expect(within(cards).getByText('WIP Form')).toBeInTheDocument());

    // Open from a DRAFT card that is not the selection, so the strip keeps
    // rendering the selected kit's own controls behind the dialog.
    const opener = selectedId === 'wip-kit' ? 'Review Form' : 'WIP Form';
    const openerCard = within(cards).getByText(opener).closest('li') as HTMLElement;
    fireEvent.click(within(openerCard).getByText('Publish'));
    await waitFor(() =>
      expect(screen.getByText(/looks like a newer version/)).toBeInTheDocument());

    // EVERY status-changing control, wherever it renders. Each label carries
    // its own existence assertion: a label matching zero elements is how the
    // previous three versions of this test passed while checking nothing.
    const LABELS = ['Publish', 'Publish again', 'Revert to draft',
                    'Unpublish', 'Send back', 'Reopen'];
    let checked = 0;
    let stripChecked = 0;
    for (const label of LABELS) {
      const buttons = screen.queryAllByText(label)
        .map((e) => e.closest('button') as HTMLButtonElement | null)
        .filter((b): b is HTMLButtonElement => !!b && !b.closest('[role="dialog"]'));
      if (buttons.length === 0) continue;
      for (const btn of buttons) {
        expect(btn.disabled, `${label} was clickable behind the dialog`).toBe(true);
        checked += 1;
        if (!cards.contains(btn)) stripChecked += 1;
      }
    }
    // The census the earlier versions lacked. The number is deliberately the
    // measured floor rather than an aspiration: an earlier comment here
    // claimed "well over a dozen", which was false -- the strip contributes
    // only the SELECTED kit's controls, so the real count is 8 and the
    // threshold bound by equality alone (round 8). What makes this test bite
    // is the parametrization over selections, not the size of this number.
    expect(checked).toBeGreaterThanOrEqual(6);
    // ...and at least one STRIP control was among them, or this has silently
    // become a card-grid-only test again.
    expect(stripChecked, 'no STRIP control was asserted on').toBeGreaterThan(0);
  });

  it('freezes the STRIP destructive pair behind the dialog', async () => {
    // The card grid is ADDITIVE, not a replacement -- the strip renders
    // unconditionally beneath it. So with a COMPLETE kit selected (its strip
    // shows Revert to draft + Unpublish) and the grid expanded, a DIFFERENT
    // draft card's Publish opens the dialog and the strip pair sits right
    // behind it, clickable.
    //
    // My round-5 test asserted this was unreachable and covered only the card
    // grid, so deleting the two STRIP gates left all 103 tests green while a
    // click genuinely fired setRemoteStatus behind the open dialog -- retiring
    // a live form while the author is being asked which live form to retire.
    // Third consecutive round this twin-shaped hole survived its own fix
    // (Opus fresh-eyes round 6).
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'done-kit', label: 'Done Form', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
                            selectedKitId="done-kit" role="author" />);
    const cards = await screen.findByRole('list');
    await waitFor(() =>
      expect(within(cards).getByText('Draft Form')).toBeInTheDocument());

    const draftCard = within(cards).getByText('Draft Form').closest('li') as HTMLElement;
    fireEvent.click(within(draftCard).getByText('Publish'));
    await waitFor(() =>
      expect(screen.getByText(/looks like a newer version/)).toBeInTheDocument());

    for (const label of ['Revert to draft', 'Unpublish']) {
      const stripBtn = screen.getAllByText(label)
        .map((e) => e.closest('button') as HTMLButtonElement)
        .find((b) => b && !b.closest('[role="dialog"]') && !cards.contains(b));
      // The EXISTENCE assertion is the point: a `find` returning undefined is
      // exactly how the last two versions of this test went vacuous.
      expect(stripBtn, `no STRIP ${label} button rendered`).toBeTruthy();
      expect(stripBtn!.disabled).toBe(true);
    }

    const stripUnpublish = screen.getAllByText('Unpublish')
      .map((e) => e.closest('button') as HTMLButtonElement)
      .find((b) => b && !b.closest('[role="dialog"]') && !cards.contains(b));
    fireEvent.click(stripUnpublish!);
    expect(setRemoteStatus).not.toHaveBeenCalled();
  });

  it('freezes REVERT TO DRAFT and UNPUBLISH behind the dialog', async () => {
    // The two most destructive controls, and the pair the parametrized test
    // above cannot reach: a COMPLETE kit renders them instead of Publish, and
    // the strip shows controls only for the SELECTED kit -- so in the strip
    // there is no Publish left to open the dialog with. Deleting these two
    // gates left the whole 1376-test suite green (Opus fresh-eyes round 5,
    // catching the round-4 flaw repeated inside the round-4 fix).
    //
    // The card grid is where both coexist: draft-kit's Publish opens the
    // dialog, done-kit's destructive pair must freeze.
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'done-kit', label: 'Done Form', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
                            selectedKitId={null} role="author" />);
    // Scope to the CARD LIST: the labels also appear in the strip's <select>,
    // so a bare getByText matches two elements.
    const cards = await screen.findByRole('list');
    await waitFor(() =>
      expect(within(cards).getByText('Done Form')).toBeInTheDocument());

    const draftCard = within(cards).getByText('Draft Form').closest('li') as HTMLElement;
    fireEvent.click(within(draftCard).getByText('Publish'));
    await waitFor(() =>
      expect(screen.getByText(/looks like a newer version/)).toBeInTheDocument());

    const liveCard = within(cards).getByText('Done Form').closest('li') as HTMLElement;
    for (const label of ['Revert to draft', 'Unpublish']) {
      const btn = within(liveCard).getByText(label).closest('button') as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    }
    // Clicking one must not fire a status change behind the open dialog.
    fireEvent.click(within(liveCard).getByText('Unpublish'));
    expect(setRemoteStatus).not.toHaveBeenCalled();
  });

  it('disables the catalogue Publish buttons while the dialog is open', async () => {
    // completingId clears before the prompt opens, so every Publish button was
    // live behind the dialog -- and clicking one replaced the pending prompt,
    // letting an author tick a candidate computed for a DIFFERENT kit. Only
    // reachable because the dialog had no real overlay (round 3, findings 1+2).
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'old-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    await publishDraftKit();
    await waitFor(() => expect(screen.getByText('Client Intake')).toBeInTheDocument());

    const card = screen.getByText('Draft Form').closest('li') as HTMLElement;
    const publish = within(card).queryByText('Publish');
    expect(publish === null || (publish.closest('button') as HTMLButtonElement).disabled)
      .toBe(true);
  });

  it('the SUBMITTED-kit publish path asks about older versions too', async () => {
    // An author publishing a kit an editor submitted -- the hqztg flow.
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'draft-kit' ? { ...k, status: 'submitted' } : k)));
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'other-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
                            selectedKitId={null} role="author" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    const card = screen.getByText('Draft Form').closest('li') as HTMLElement;
    fireEvent.click(within(card).getByText('Publish'));

    await waitFor(() => expect(fetchRetireCandidates).toHaveBeenCalledWith('draft-kit'));
  });

  it('asks from the compact STRIP publish button too, not just the card', async () => {
    // The twin. My mutation testing initially reverted only the strip button
    // and every test stayed green -- because publishDraftKit clicks the CARD.
    // Each twin needs its own click, or one of the pair can lose the wiring
    // silently. This repo's most repeated defect, and it nearly landed again.
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'old-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    // No card grid: the compact strip is the default view.
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="draft-kit"
                            role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Publish'));

    await waitFor(() => expect(fetchRetireCandidates).toHaveBeenCalledWith('draft-kit'));
    expect(setRemoteStatus).not.toHaveBeenCalled();
  });

  it('asks about older versions from the DRAFT publish path too', async () => {
    // The path that actually matters, and the one I missed: an author
    // publishing a DRAFT. Its button reads `isAuthor ? 'complete' :
    // 'submitted'`, so a search for the literal `handleSetStatus(kit,
    // 'complete')` skipped it -- the suggestion never fired on the primary
    // publish route while every other test stayed green.
    //
    // Asserts the CALL, not just the dialog: reverting the wiring makes the
    // check silently not happen, which is exactly what shipped.
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'old-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    await publishDraftKit();

    await waitFor(() => expect(fetchRetireCandidates).toHaveBeenCalledWith('draft-kit'));
    expect(await screen.findByText('Client Intake')).toBeInTheDocument();
    // ...and nothing is published until the author answers.
    expect(setRemoteStatus).not.toHaveBeenCalled();
  });

  it('an EDITOR submitting a draft is never asked about retirement', async () => {
    // Submitting retires nothing, so asking would be a question with no
    // meaning -- and the route is author-only anyway.
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'old-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Show form cards'));
    const card = screen.getByText('Draft Form').closest('li') as HTMLElement;
    fireEvent.click(within(card).getByText('Submit for review'));

    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalled());
    expect(fetchRetireCandidates).not.toHaveBeenCalled();
    expect(vi.mocked(setRemoteStatus).mock.calls[0][1]).toBe('submitted');
  });

  it('carries a ticked RETIREMENT through the version prompt', async () => {
    // The firm-tier case this whole bead targets: a custom form has no
    // government edition date, so publishing it needs BOTH dialogs -- pick the
    // form to retire, then name a version. The retry re-called publish with
    // only the version, so the author ticked a form, named a version, and got
    // a publish with nothing retired and NO ERROR (Opus fresh-eyes round 1).
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'old-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    vi.mocked(setRemoteStatus)
      .mockRejectedValueOnce(new Error(REFUSAL))
      .mockResolvedValueOnce({
        ok: true, status: 'complete', retranslated: 0,
        translationModel: null, supersededKitId: 'old-kit',
      });
    await publishDraftKit();

    // Tick the candidate and publish.
    await waitFor(() => expect(screen.getByText('Client Intake')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('radio')[0]);
    fireEvent.click(screen.getByText('Publish and retire the old one'));

    // The gate asks for a version...
    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Version'), { target: { value: '2026-08-07' } });
    fireEvent.click(screen.getByText('Save version & publish'));

    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalledTimes(2));
    // BOTH survive the retry. Asserting the whole options object, not just the
    // version: the bug was an omission, and a partial assertion would miss it.
    expect(vi.mocked(setRemoteStatus).mock.calls[1]).toEqual(
      ['draft-kit', 'complete',
       { authorVersion: '2026-08-07', replacesKitId: 'old-kit' }],
    );
  });

  it('publishes with NO retirement when the author ticks nothing', async () => {
    vi.mocked(fetchRetireCandidates).mockResolvedValue([
      { kitId: 'old-kit', label: 'Client Intake', matchedOn: 'label' },
    ]);
    vi.mocked(setRemoteStatus).mockResolvedValueOnce({
      ok: true, status: 'complete', retranslated: 0,
      translationModel: null, supersededKitId: null,
    });
    await publishDraftKit();

    await waitFor(() => expect(screen.getByText('Client Intake')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Publish, keep both'));

    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalled());
    // The VALUE, not the key's presence: the options object legitimately
    // carries `replacesKitId: undefined`, and setRemoteStatus omits the wire
    // field for any falsy value -- so asserting the key's absence would fail
    // while the shipped request is correct.
    expect(vi.mocked(setRemoteStatus).mock.calls[0][2]?.replacesKitId).toBeUndefined();
  });

  it('shows NO extra step when nothing looks like the same form', async () => {
    // The common case must not grow a dialog (the bead is explicit).
    vi.mocked(fetchRetireCandidates).mockResolvedValue([]);
    vi.mocked(setRemoteStatus).mockResolvedValueOnce({
      ok: true, status: 'complete', retranslated: 0,
      translationModel: null, supersededKitId: null,
    });
    await publishDraftKit();

    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalled());
    expect(screen.queryByText(/looks like a newer version/)).not.toBeInTheDocument();
  });

  it('retries the SAME publish with the version attached', async () => {
    vi.mocked(setRemoteStatus)
      .mockRejectedValueOnce(new Error(REFUSAL))
      .mockResolvedValueOnce({
        ok: true, status: 'complete', retranslated: 0,
        translationModel: null, supersededKitId: null,
      });
    await publishDraftKit();
    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Version'), { target: { value: 'v2026-08-07' } });
    fireEvent.click(screen.getByText('Save version & publish'));

    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalledTimes(2));
    // Normalized (leading v stripped), and carried in the options object -- a
    // positional third argument here would silently be read as replaces_kit_id
    // and retire an unrelated kit.
    expect(vi.mocked(setRemoteStatus).mock.calls[1]).toEqual(
      ['draft-kit', 'complete', { authorVersion: '2026-08-07' }],
    );
  });

  it('cancelling leaves the kit unpublished and calls nothing further', async () => {
    vi.mocked(setRemoteStatus).mockRejectedValueOnce(new Error(REFUSAL));
    await publishDraftKit();
    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Cancel'));

    expect(screen.queryByText(/Name this version of/)).not.toBeInTheDocument();
    expect(setRemoteStatus).toHaveBeenCalledTimes(1);
  });

  it('cancelling does NOT strand the catalogue disabled', async () => {
    // `busy` gates every control here (Mark complete, Unpublish, Revert,
    // Refresh, Rename, Extract). The early return that opens the dialog used to
    // skip setBusy(false) -- which sat at the END of the catch -- so cancelling
    // disabled the whole component until a reload (Opus fresh-eyes,
    // reproduced). Both resets now live in `finally`.
    vi.mocked(setRemoteStatus).mockRejectedValueOnce(new Error(REFUSAL));
    await publishDraftKit();
    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Cancel'));

    await waitFor(() => {
      const btn = screen.getAllByText('Publish')[0].closest('button');
      expect(btn?.disabled).toBe(false);
    });
  });

  it('hides the previous-version line rather than printing "unknown"', async () => {
    // versionInfoFromSchema falls back to the literal 'unknown', and this
    // dialog only opens for a kit with no marker -- so the rubric's "previous
    // value shown" clause rendered "Previous version: unknown" every time.
    vi.mocked(setRemoteStatus).mockRejectedValueOnce(new Error(REFUSAL));
    await publishDraftKit();
    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());

    expect(screen.queryByText(/Previous version/)).not.toBeInTheDocument();
  });

  it('keeps the dialog open while the retry runs', async () => {
    // The retry re-translates one language per LLM call -- tens of seconds.
    // Closing the dialog first showed an unchanged catalogue with no progress
    // and an inviting Mark complete, and made the dialog's own busy guard
    // unreachable.
    let settle: (v: KitStatusResult) => void = () => {};
    vi.mocked(setRemoteStatus)
      .mockRejectedValueOnce(new Error(REFUSAL))
      .mockImplementationOnce(() => new Promise((res) => { settle = res; }));
    await publishDraftKit();
    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Save version & publish'));
    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalledTimes(2));
    // Still mounted mid-flight.
    expect(screen.getByText(/Name this version of/)).toBeInTheDocument();

    settle({ ok: true, status: 'complete', retranslated: 0,
             translationModel: null, supersededKitId: null });
    await waitFor(() =>
      expect(screen.queryByText(/Name this version of/)).not.toBeInTheDocument());
  });

  it('surfaces a SECOND refusal instead of leaving the dialog hanging', async () => {
    // If the retry is refused for a different reason (lint, translations), the
    // dialog closes and the real error must be visible -- not swallowed.
    vi.mocked(setRemoteStatus)
      .mockRejectedValueOnce(new Error(REFUSAL))
      .mockRejectedValueOnce(new Error('Schema has 2 lint error(s), so it cannot be marked complete'));
    await publishDraftKit();
    await waitFor(() =>
      expect(screen.getByText(/Name this version of/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Save version & publish'));

    await waitFor(() => expect(screen.getByText(/lint error/)).toBeInTheDocument());
    expect(screen.queryByText(/Name this version of/)).not.toBeInTheDocument();
  });

  it('a DIFFERENT publish refusal still shows as an error, not the dialog', async () => {
    // The dialog must be scoped to its own token. A lint refusal that opened a
    // version prompt would hide the real problem and prompt for the wrong fix.
    vi.mocked(setRemoteStatus).mockRejectedValueOnce(
      new Error('Schema has 3 lint error(s), so it cannot be marked complete'),
    );
    await publishDraftKit();

    await waitFor(() =>
      expect(screen.getByText(/lint error/)).toBeInTheDocument());
    expect(screen.queryByText(/Name this version of/)).not.toBeInTheDocument();
  });
});

describe('rename from the selector strip (bd 15ic)', () => {
  it('renames the selected kit via the inline input (works without an open)', async () => {
    vi.mocked(setRemoteLabel).mockResolvedValue(undefined);
    // onOpenKit no-ops: rename must work even for a kit whose open was never
    // confirmed (it is metadata-only).
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByLabelText('Select a form')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Select a form'), {
      target: { value: 'draft-kit' },
    });

    fireEvent.click(screen.getByText('Rename'));
    const input = screen.getByLabelText('New form name') as HTMLInputElement;
    expect(input.value).toBe('Draft Form');  // pre-filled with the current label
    fireEvent.change(input, { target: { value: '  IRS W-9  ' } });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() =>
      expect(setRemoteLabel).toHaveBeenCalledWith('draft-kit', 'IRS W-9'));
    // The catalogue refreshed after the rename.
    await waitFor(() =>
      expect(vi.mocked(listRemoteKits).mock.calls.length).toBeGreaterThan(1));
  });

  it('Escape cancels the rename without a server call', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByLabelText('Select a form')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Select a form'), {
      target: { value: 'draft-kit' },
    });
    fireEvent.click(screen.getByText('Rename'));
    fireEvent.keyDown(screen.getByLabelText('New form name'), { key: 'Escape' });
    expect(screen.queryByLabelText('New form name')).not.toBeInTheDocument();
    expect(setRemoteLabel).not.toHaveBeenCalled();
  });
});

describe('RemoteCatalogue standalone Translate options (bd 2h9j)', () => {
  const REPORT = {
    changed: true, model: 'gemini-2.5-pro', failedLanguages: [] as string[],
    languages: {
      spanish: { labels: 3, missing: 3, translated: 3, options_updated: 4, failed: false },
      french: { labels: 3, missing: 3, translated: 3, options_updated: 4, failed: false },
    },
    flags: [], errorCount: 0, warningCount: 0,
  };

  it('author bakes translations for an OPEN draft kit -> call + notice + reopen', async () => {
    vi.mocked(translateRemoteKitOptions).mockResolvedValue(REPORT);
    const onOpenKit = vi.fn();
    render(<RemoteCatalogue onOpenKit={onOpenKit} selectedKitId="draft-kit" role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Translate options')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Translate options'));
    await waitFor(() => expect(translateRemoteKitOptions)
      .toHaveBeenCalledWith('draft-kit'));
    await waitFor(() => expect(
      screen.getByText(/8 option-language entries baked/)).toBeInTheDocument());
    // The open kit is re-opened so the editor shows the stored (translated) schema.
    expect(onOpenKit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'draft-kit' }));
  });

  it('reports failed languages and does not reopen when nothing changed', async () => {
    vi.mocked(translateRemoteKitOptions).mockResolvedValue(
      { ...REPORT, changed: false });
    const onOpenKit = vi.fn();
    render(<RemoteCatalogue onOpenKit={onOpenKit} selectedKitId="draft-kit" role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Translate options')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Translate options'));
    await waitFor(() => expect(
      screen.getByText(/already fully translated/)).toBeInTheDocument());
    expect(onOpenKit).not.toHaveBeenCalled();
  });

  it('points the author at the flagged option rows when the bake flags translations (bd 9djc, re-homed by s18 C1)', async () => {
    vi.mocked(translateRemoteKitOptions).mockResolvedValue({
      ...REPORT,
      flags: [
        { severity: 'WARNING', rule: 'translation-drift-unresolved',
          path: 'fields[0] (id=x).options[m].label_translations.spanish',
          field_id: 'x', message: 'judge: drift' },
        { severity: 'WARNING', rule: 'translation-ambiguous-source',
          path: 'fields[1] (id=y).options[s].label_translations.french',
          field_id: 'y', message: 'under-determined' },
      ],
    });
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="draft-kit" role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Translate options')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Translate options'));
    await waitFor(() => expect(
      screen.getByText(/2 translation flags to review/)).toBeInTheDocument());
    // The pane is gone (s18 C1): the notice must send the author to where
    // flags now render -- the field list rows + the option in the editor --
    // and must NOT mention the removed panel.
    expect(screen.getByText(/shows on its answer choice in the field editor/))
      .toBeInTheDocument();
    expect(screen.queryByText(/validation panel/)).toBeNull();
  });

  it('still surfaces the flags and reloads when they arrive without label changes (bd 9djc)', async () => {
    // Reachable on a force re-bake that reproduces identical values: the
    // backend persists the flags (changed=false, flags non-empty), so the
    // notice must not read as a pure no-op and the open kit must reload.
    vi.mocked(translateRemoteKitOptions).mockResolvedValue({
      ...REPORT,
      changed: false,
      flags: [
        { severity: 'WARNING', rule: 'translation-drift-unresolved',
          path: 'fields[0] (id=x).options[m].label_translations.spanish',
          field_id: 'x', message: 'judge: drift' },
      ],
    });
    const onOpenKit = vi.fn();
    render(<RemoteCatalogue onOpenKit={onOpenKit} selectedKitId="draft-kit" role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Translate options')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Translate options'));
    await waitFor(() => expect(
      screen.getByText(/1 translation flag to review/)).toBeInTheDocument());
    expect(onOpenKit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'draft-kit' }));
  });

  it('surfaces failed languages in the notice', async () => {
    vi.mocked(translateRemoteKitOptions).mockResolvedValue(
      { ...REPORT, failedLanguages: ['french'] });
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="draft-kit" role="author" />);
    await waitFor(() =>
      expect(screen.getByText('Translate options')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Translate options'));
    await waitFor(() => expect(
      screen.getByText(/FAILED: french/)).toBeInTheDocument());
  });

  it('editor tier never sees the action; complete kits never offer it', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="draft-kit" role="editor" />);
    await waitFor(() =>
      expect(screen.getByTestId('catalogue-strip')).toBeInTheDocument());
    expect(screen.queryByText('Translate options')).not.toBeInTheDocument();

    // Author + a COMPLETE open kit: the route would 409; the button is absent.
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="done-kit" role="author" />);
    await waitFor(() =>
      expect(screen.getAllByTestId('catalogue-strip').length).toBeGreaterThan(0));
    expect(screen.queryByText('Translate options')).not.toBeInTheDocument();
  });

  it('routes a 401 to onAuthError', async () => {
    vi.mocked(translateRemoteKitOptions).mockRejectedValue(new AuthError());
    const onAuthError = vi.fn();
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId="draft-kit"
      role="author" onAuthError={onAuthError} />);
    await waitFor(() =>
      expect(screen.getByText('Translate options')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Translate options'));
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
  });

  // --- the unpublished status (bd polyglot-pdf-6dz0) ------------------------
  // Round 2 of review found three defects in this status's UI, ALL of them in
  // paths no test touched: the file had zero references to 'unpublished'.

  it('offers Unpublish on a published kit and reports the retirement honestly', async () => {
    vi.mocked(setRemoteStatus).mockResolvedValue({
      ok: true, status: 'unpublished', retranslated: 0, translationModel: null,
      supersededKitId: null });
    // AUTHOR tier: retiring a live form is an author action (bd
    // polyglot-pdf-hqztg). What this pins -- the honest retirement notice --
    // is unchanged by who performs it.
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
      selectedKitId="done-kit" role="author" />);
    await waitFor(() => expect(screen.getByText('Done Form')).toBeInTheDocument());

    fireEvent.click(screen.getAllByText('Unpublish')[0]);

    await waitFor(() =>
      expect(setRemoteStatus).toHaveBeenCalledWith('done-kit', 'unpublished', {}));
    // The notice must name the RETIREMENT. It previously said "reverted to
    // draft" -- the wrong action, and it implies the kit is editable again.
    await waitFor(() => {
      const notice = screen.getByText(/is unpublished/);
      expect(notice).toBeInTheDocument();
      expect(notice.textContent).not.toMatch(/reverted to draft/);
    });
  });

  it('offers Publish again -- never Mark complete -- on a retired kit', async () => {
    vi.mocked(listRemoteKits).mockResolvedValue([
      { id: 'old-kit', label: 'Retired Form', status: 'unpublished',
        hasSchema: true, hasPdf: true, schemaFile: 'schema.json',
        pdfFile: 'form.pdf' },
    ]);
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
      selectedKitId="old-kit" role="author" />);
    await waitFor(() => expect(screen.getByText('Retired Form')).toBeInTheDocument());

    // A retired revision returns to service only through the publish gate.
    expect(screen.getAllByText('Publish again').length).toBeGreaterThan(0);
    expect(screen.queryByText('Publish')).not.toBeInTheDocument();
    // ...and it is never offered a revert-to-draft, which would unlock it.
    expect(screen.queryByText('Revert to draft')).not.toBeInTheDocument();
  });

  it('counts a retired kit separately so the summary still adds up', async () => {
    vi.mocked(listRemoteKits).mockResolvedValue([
      { id: 'live', label: 'Live Form', status: 'complete', hasSchema: true,
        hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
      { id: 'old', label: 'Retired Form', status: 'unpublished', hasSchema: true,
        hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
    ]);
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByTestId('catalogue-summary')).toBeInTheDocument());

    const summary = screen.getByTestId('catalogue-summary').textContent ?? '';
    expect(summary).toMatch(/2 forms/);
    expect(summary).toMatch(/1 complete/);
    // Without this the retired kit vanishes from the breakdown and the
    // sub-counts silently stop summing to the total.
    expect(summary).toMatch(/1 retired/);
  });
});


describe('guarded delete (bd polyglot-pdf-6x1j)', () => {
  async function openCards(role: 'author' | 'editor') {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role={role} />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Show form cards'));
  }

  it('offers Delete to an AUTHOR', async () => {
    await openCards('author');
    expect(screen.getAllByText('Delete').length).toBeGreaterThan(0);
  });

  it('does NOT offer Delete to an EDITOR', async () => {
    // Maintainer rule: editors never take destructive actions. The server
    // enforces it too (an editor holds a token and can call the API), but the
    // button must not be there to click.
    await openCards('editor');
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
  });

  it('requires the kit id to be typed before deleting', async () => {
    await openCards('author');
    fireEvent.click(screen.getAllByText('Delete')[0]);

    await waitFor(() =>
      expect(screen.getByText(/Delete .* permanently\?/)).toBeInTheDocument());
    expect((screen.getByText('Delete permanently') as HTMLButtonElement).disabled).toBe(true);
    expect(deleteRemoteKit).not.toHaveBeenCalled();
  });

  it('deletes and refreshes once the id matches', async () => {
    vi.mocked(deleteRemoteKit).mockResolvedValueOnce(3);
    await openCards('author');
    fireEvent.click(screen.getAllByText('Delete')[0]);
    await waitFor(() =>
      expect(screen.getByLabelText(/Type/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'done-kit' } });
    fireEvent.click(screen.getByText('Delete permanently'));

    await waitFor(() => expect(deleteRemoteKit).toHaveBeenCalledWith('done-kit'));
    await waitFor(() =>
      expect(vi.mocked(listRemoteKits).mock.calls.length).toBeGreaterThan(1));
  });

  it('renders Delete LAST, after the extraction row on a schemaless kit', async () => {
    // The mis-click mitigation is "never the button next to the one you meant".
    // That held for schema-bearing kits but not for schemaless ones, where the
    // extraction row rendered BELOW Delete -- and those are exactly the kits an
    // author triages as junk (Opus fresh-eyes round 4).
    await openCards('author');

    const html = document.body.innerHTML;
    const deleteAt = html.lastIndexOf('>Delete<');
    const extractAt = html.indexOf('Run extraction');
    expect(extractAt).toBeGreaterThan(-1);   // the fixture has a schemaless kit
    expect(deleteAt).toBeGreaterThan(extractAt);
  });

  it('clears a stale success notice when a later delete is REFUSED', async () => {
    // Deleting A then being refused on B showed a green '"A" was deleted
    // permanently' beside B's red refusal -- on the one workflow where "did
    // that just delete something?" must never be ambiguous.
    vi.mocked(deleteRemoteKit).mockResolvedValueOnce(3);
    await openCards('author');
    fireEvent.click(screen.getAllByText('Delete')[0]);
    await waitFor(() => expect(screen.getByLabelText(/Type/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'done-kit' } });
    fireEvent.click(screen.getByText('Delete permanently'));
    await waitFor(() =>
      expect(screen.getByText(/was deleted permanently/)).toBeInTheDocument());

    // Now a refusal on a different kit. The list refreshed after the first
    // delete, so target the card by its LABEL rather than by index -- an index
    // here silently re-opens whichever card happens to be first.
    vi.mocked(deleteRemoteKit).mockRejectedValueOnce(
      new Error('"draft-kit" has confirmation records. Unpublish it instead.'),
    );
    const draftCard = screen.getByText('Draft Form').closest('li');
    fireEvent.click(within(draftCard as HTMLElement).getByText('Delete'));
    await waitFor(() => expect(screen.getByLabelText(/Type/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'draft-kit' } });
    fireEvent.click(screen.getByText('Delete permanently'));

    await waitFor(() =>
      expect(screen.getByText(/has confirmation records/)).toBeInTheDocument());
    expect(screen.queryByText(/was deleted permanently/)).not.toBeInTheDocument();
  });

  it('keeps the dialog OPEN and shows the guard refusal verbatim', async () => {
    // A 409 here is the guard working, not a transient error: it names why the
    // form cannot be deleted and offers unpublish. Dismissing the dialog would
    // strand that explanation away from the form it is about.
    vi.mocked(deleteRemoteKit).mockRejectedValueOnce(
      new Error('"done-kit" has confirmation records: clients have agreed to this '
        + 'form. Unpublish it instead.'),
    );
    await openCards('author');
    fireEvent.click(screen.getAllByText('Delete')[0]);
    await waitFor(() =>
      expect(screen.getByLabelText(/Type/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'done-kit' } });
    fireEvent.click(screen.getByText('Delete permanently'));

    await waitFor(() =>
      expect(screen.getByText(/has confirmation records/)).toBeInTheDocument());
    // Still open, so the refusal sits next to the form it names.
    expect(screen.getByText('Delete permanently')).toBeTruthy();
  });

  it('calls clearOpenKit when the DELETED kit is the currently-open one (bd polyglot-pdf-hbfky)', async () => {
    vi.mocked(deleteRemoteKit).mockResolvedValueOnce(3);
    const clearOpenKit = vi.fn();
    render(
      <RemoteCatalogue
        onOpenKit={() => {}}
        selectedKitId="done-kit"
        role="author"
        clearOpenKit={clearOpenKit}
      />
    );
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Show form cards'));

    fireEvent.click(screen.getAllByText('Delete')[0]);
    await waitFor(() => expect(screen.getByLabelText(/Type/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'done-kit' } });
    fireEvent.click(screen.getByText('Delete permanently'));

    await waitFor(() => expect(deleteRemoteKit).toHaveBeenCalledWith('done-kit'));
    expect(clearOpenKit).toHaveBeenCalledTimes(1);
  });

  it('does NOT call clearOpenKit when the deleted kit is NOT the open one', async () => {
    // The editor pane must stay put when a different, unrelated kit is
    // deleted -- only the SAME kit id being open triggers the reset.
    vi.mocked(deleteRemoteKit).mockResolvedValueOnce(3);
    const clearOpenKit = vi.fn();
    render(
      <RemoteCatalogue
        onOpenKit={() => {}}
        selectedKitId="some-other-open-kit"
        role="author"
        clearOpenKit={clearOpenKit}
      />
    );
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Show form cards'));

    fireEvent.click(screen.getAllByText('Delete')[0]);
    await waitFor(() => expect(screen.getByLabelText(/Type/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'done-kit' } });
    fireEvent.click(screen.getByText('Delete permanently'));

    await waitFor(() => expect(deleteRemoteKit).toHaveBeenCalledWith('done-kit'));
    expect(clearOpenKit).not.toHaveBeenCalled();
  });
});


describe('the editing lock is reachable from the UI (bd polyglot-pdf-hqztg)', () => {
  async function cards(role: 'author' | 'editor') {
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role={role} />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
  }

  function card(label: string) {
    return screen.getByText(label).closest('li') as HTMLElement;
  }

  it('offers Take for editing on an unheld kit', async () => {
    await cards('editor');
    expect(within(card('Draft Form')).getByText('Take for editing')).toBeTruthy();
  });

  it('takes the lock through the API, not just in local state', async () => {
    vi.mocked(takeKitLock).mockResolvedValueOnce({
      ok: true, kitId: 'draft-kit', heldBy: 'editor', preempted: false });
    await cards('editor');

    fireEvent.click(within(card('Draft Form')).getByText('Take for editing'));

    await waitFor(() => expect(takeKitLock).toHaveBeenCalledWith('draft-kit'));
    await waitFor(() =>
      expect(vi.mocked(listRemoteKits).mock.calls.length).toBeGreaterThan(1));
  });

  it('shows the holder and RELEASES through the API', async () => {
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'draft-kit' ? { ...k, heldBy: 'editor' } : k)));
    vi.mocked(releaseKitLock).mockResolvedValueOnce({
      ok: true, kitId: 'draft-kit', heldBy: null, preempted: false });
    await cards('editor');

    expect(within(card('Draft Form')).getByText('Editor editing')).toBeTruthy();
    fireEvent.click(within(card('Draft Form')).getByText('Release'));

    await waitFor(() => expect(releaseKitLock).toHaveBeenCalledWith('draft-kit'));
  });

  it('lets an AUTHOR take a kit back from an editor', async () => {
    // The maintainer's rule, reachable in the product rather than only in the
    // API: authors can always steal it back.
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'draft-kit' ? { ...k, heldBy: 'editor' } : k)));
    vi.mocked(takeKitLock).mockResolvedValueOnce({
      ok: true, kitId: 'draft-kit', heldBy: 'author', preempted: true });
    await cards('author');

    fireEvent.click(within(card('Draft Form')).getByText('Take back'));

    await waitFor(() => expect(takeKitLock).toHaveBeenCalledWith('draft-kit'));
    // The person who took it is TOLD they took it -- the other side cannot be
    // notified, so silently winning would leave nobody aware.
    await waitFor(() =>
      expect(screen.getByText(/took "Draft Form" from an editor/)).toBeInTheDocument());
  });

  it('does NOT offer an editor a kit an author holds', async () => {
    // Preemption is one-way. The server refuses it too; the button must not be
    // there to click.
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'draft-kit' ? { ...k, heldBy: 'author' } : k)));
    await cards('editor');

    const c = card('Draft Form');
    expect(within(c).getByText('Author editing')).toBeTruthy();
    expect(within(c).queryByText('Take for editing')).not.toBeInTheDocument();
    expect(within(c).queryByText('Take back')).not.toBeInTheDocument();
    expect(within(c).queryByText('Release')).not.toBeInTheDocument();
  });
  it('lets an author FREE an abandoned editor lock without taking it', async () => {
    // The stale-lock escape you actually want when someone closed their laptop
    // and went on holiday. "Take back" transfers the lock to the author, so
    // using it to clear an abandoned kit leaves the kit locked to THEM unless
    // they remember a second step (found by enumerating the six
    // holder x viewer cells rather than spot-checking).
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'draft-kit' ? { ...k, heldBy: 'editor' } : k)));
    vi.mocked(releaseKitLock).mockResolvedValueOnce({
      ok: true, kitId: 'draft-kit', heldBy: null, preempted: false });
    await cards('author');

    fireEvent.click(within(card('Draft Form')).getByText('Free it'));

    await waitFor(() => expect(releaseKitLock).toHaveBeenCalledWith('draft-kit'));
    expect(takeKitLock).not.toHaveBeenCalled();
  });

  it('does not offer Free it to an EDITOR', async () => {
    // Releasing someone else's lock is an author capability; the server 409s
    // an editor who tries, so the button must not be there.
    vi.mocked(listRemoteKits).mockResolvedValue(
      KITS.map((k) => (k.id === 'draft-kit' ? { ...k, heldBy: 'author' } : k)));
    await cards('editor');

    expect(within(card('Draft Form')).queryByText('Free it')).not.toBeInTheDocument();
  });
});


describe('the submit notice names what happened (bd polyglot-pdf-hqztg)', () => {
  it('a successful SUBMIT does not report "reverted to draft"', async () => {
    // The notice chain branched on complete and unpublished and let everything
    // else fall into a terminal else that said "reverted to draft" -- so the
    // editor tier's most-used new action reported the OPPOSITE of what it did.
    // The unpublished branch exists because that status hit this same bug;
    // adding a fourth status reintroduced it (Opus fresh-eyes round 6).
    vi.mocked(setRemoteStatus).mockResolvedValue({
      ok: true, status: 'submitted', retranslated: 0,
      translationModel: null, supersededKitId: null });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
      selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(within(
      screen.getByText('Draft Form').closest('li') as HTMLElement,
    ).getByText('Submit for review'));

    const notice = await screen.findByText(/submitted for review/);
    expect(notice.textContent).not.toMatch(/reverted to draft/);
    expect(notice.textContent).toMatch(/An author checks it/);
  });
});
