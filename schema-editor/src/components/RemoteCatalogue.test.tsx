/**
 * RemoteCatalogue tests (bd polyglot-pdf-92qe.2): the hosted front door lists
 * kits from the editor API (drafts included -- the contractor work list), opens
 * a kit, flips status via the server (surfacing the promote-gate refusal), and
 * routes a 401 to the auth handler instead of a dead error banner.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  return {
    ...actual,
    listRemoteKits: vi.fn(),
    loadRemoteSchema: vi.fn(),
    setRemoteStatus: vi.fn(),
    setRemoteLabel: vi.fn(),
    onboardRemoteKit: vi.fn(),
    extractRemoteKit: vi.fn(),
    translateRemoteKitOptions: vi.fn(),
  };
});

import { RemoteCatalogue } from './RemoteCatalogue';
import {
  AuthError, extractRemoteKit, listRemoteKits, loadRemoteSchema,
  onboardRemoteKit, setRemoteLabel, setRemoteStatus, translateRemoteKitOptions,
  type RemoteKitEntry, type KitStatusResult,
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
  vi.mocked(loadRemoteSchema).mockResolvedValue(SCHEMA);
  // Default: a clean complete flip with no drift (bd polyglot-pdf-783r). Tests
  // that exercise the drift notice / refusal override this per-case.
  vi.mocked(setRemoteStatus).mockResolvedValue({
    ok: true, status: 'complete', retranslated: 0, translationModel: null,
  });
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

  it('computes review progress from each kit schema (shared definition)', async () => {
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    // The one-field schema is incomplete -> 0% bars on both schema kits.
    await waitFor(() => expect(screen.getAllByText('0%').length).toBe(2));
    expect(vi.mocked(loadRemoteSchema)).toHaveBeenCalledWith('done-kit');
    expect(vi.mocked(loadRemoteSchema)).toHaveBeenCalledWith('draft-kit');
    // The schemaless kit is never fetched.
    expect(vi.mocked(loadRemoteSchema)).not.toHaveBeenCalledWith('fresh-kit');
  });

  it('marks a draft complete via the server and refreshes', async () => {
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalledWith('draft-kit', 'complete'));
    // Refresh happened (list re-requested).
    await waitFor(() => expect(vi.mocked(listRemoteKits).mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => expect(screen.getByText(/marked complete/)).toBeInTheDocument());
  });

  it('notes the drift sweep in the complete notice when it re-translated (bd 783r)', async () => {
    vi.mocked(setRemoteStatus).mockResolvedValue({
      ok: true, status: 'complete', retranslated: 3, translationModel: 'gemini-2.5-pro',
    });
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() =>
      expect(screen.getByText(/Refreshed 3 translation entries/)).toBeInTheDocument());
  });

  it('surfaces the incomplete-translation refusal (409 "N of M") as the error banner (bd 783r)', async () => {
    vi.mocked(setRemoteStatus).mockRejectedValue(
      new Error('10 of 17 language translations complete. Please try again later to finish (retrying only the missing ones).'),
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() =>
      expect(screen.getByText(/10 of 17 language translations complete/)).toBeInTheDocument());
  });

  it('surfaces the promote-gate refusal detail (422) as the error banner', async () => {
    vi.mocked(setRemoteStatus).mockRejectedValue(
      new Error('Schema does not validate against the form contract'),
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() =>
      expect(screen.getByText(/does not validate/)).toBeInTheDocument());
  });

  it('mirrors a Mark-complete refusal up through onStatusRefusal, and clears it on the next attempt (s18 C1)', async () => {
    // The producer side of the strip's refusal line (decision 1): a refused
    // completion reaches the host with the server's detail; a later attempt
    // clears the stale refusal first (null) before the call runs.
    const onStatusRefusal = vi.fn();
    vi.mocked(setRemoteStatus).mockRejectedValueOnce(
      new Error('Schema has 1 lint error(s), so it cannot be marked complete'),
    );
    render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}}
      selectedKitId={null} role="editor" onStatusRefusal={onStatusRefusal} />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() => expect(onStatusRefusal).toHaveBeenCalledWith(
      expect.stringContaining('cannot be marked complete')));
    // Called with null FIRST on entry (stale refusal cleared before the call).
    expect(onStatusRefusal.mock.calls[0]).toEqual([null]);

    // The retry succeeds (the once-rejection is spent): only the clear fires.
    onStatusRefusal.mockClear();
    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() => expect(screen.getByText(/marked complete/)).toBeInTheDocument());
    expect(onStatusRefusal).toHaveBeenCalledWith(null);
    expect(onStatusRefusal).not.toHaveBeenCalledWith(expect.stringContaining('cannot'));
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
        onOpenKit={() => {}} selectedKitId="draft-kit" role="editor"
        liveProgress={{ kitId: 'draft-kit', saved: false, percent: 50, complete: 1, total: 2 }}
      />,
    );
    // The selected kit's Mark-complete renders in BOTH the compact strip and
    // its card (bd tynm) -- the unsaved-edits guard must hold on every copy.
    await waitFor(() => expect(screen.getAllByText('Mark complete').length).toBeGreaterThan(0));
    for (const btn of screen.getAllByText('Mark complete')) {
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
        onOpenKit={() => {}} selectedKitId="draft-kit" role="editor"
        liveProgress={{ kitId: 'draft-kit', saved: true, percent: 100, complete: 2, total: 2 }}
      />,
    );
    await waitFor(() => expect(screen.getAllByText('Mark complete').length).toBeGreaterThan(0));
    for (const btn of screen.getAllByText('Mark complete')) {
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
      render(<RemoteCatalogue defaultExpanded onOpenKit={() => {}} selectedKitId={null} role="editor" />);
      await waitFor(() => expect(screen.getByText('Mark complete')).toBeInTheDocument());

      fireEvent.click(screen.getByText('Mark complete'));
      // Mid-flight: the button shows the elapsed re-translating ticker (the
      // sweep can take tens of seconds -- a dead button would read as a hang).
      await waitFor(() =>
        expect(screen.getByText(/Re-translating & validating\.\.\. \d+s/)).toBeInTheDocument());

      resolveStatus({
        ok: true, status: 'complete', retranslated: 2, translationModel: 'gemini-2.5-pro',
      });
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
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByLabelText('Select a form')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Select a form'), {
      target: { value: 'draft-kit' },
    });
    expect(screen.queryByText('Mark complete')).not.toBeInTheDocument();
    expect(screen.queryByText('Revert to draft')).not.toBeInTheDocument();
  });

  it('the toggle expands the full card grid and collapses it again', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByText('Show form cards')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Show form cards'));
    expect(screen.getByTitle('Open Draft Form for editing')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Hide form cards'));
    expect(screen.queryByTitle('Open Draft Form for editing')).not.toBeInTheDocument();
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
});
