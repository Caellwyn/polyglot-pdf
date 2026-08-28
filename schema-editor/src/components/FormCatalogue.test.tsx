/**
 * Component tests for the form catalogue (bd polyglot-pdf-b0pe): open a folder,
 * list kits, drop a PDF to onboard. The File System Access directory API is
 * mocked via window.showDirectoryPicker.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { FormCatalogue } from './FormCatalogue';
import { ForbiddenError } from '../utils/remoteKitStore';


// --- in-memory mock directory ---------------------------------------------- //
function mockFile(name: string, contents = '') {
  const state = { contents };
  return { kind: 'file' as const, name,
    createWritable: async () => ({
      write: async (d: string | ArrayBuffer) => {
        state.contents = typeof d === 'string' ? d : '';
      },
      close: async () => {},
    }),
    getFile: async () => ({ text: async () => state.contents } as unknown as File) };
}
function mockKit(name: string, files: Record<string, string>) {
  const children = new Map<string, ReturnType<typeof mockFile>>();
  for (const [fn, c] of Object.entries(files)) children.set(fn, mockFile(fn, c));
  return {
    kind: 'directory' as const, name, children,
    async *entries() { for (const [n, h] of children) yield [n, h]; },
    getFileHandle: async (fn: string, opts?: { create?: boolean }) => {
      let f = children.get(fn);
      if (!f) { if (!opts?.create) throw new DOMException('x', 'NotFoundError'); f = mockFile(fn); children.set(fn, f); }
      return f;
    },
    getDirectoryHandle: async () => { throw new DOMException('x', 'NotFoundError'); },
  };
}
function mockRoot(kits: ReturnType<typeof mockKit>[]) {
  const children = new Map<string, ReturnType<typeof mockKit>>();
  for (const k of kits) children.set(k.name, k);
  const created: Record<string, ReturnType<typeof mockKit>> = {};
  const files = new Map<string, ReturnType<typeof mockFile>>();
  return {
    kind: 'directory' as const, name: 'form-kits', children, created,
    async *entries() { for (const [n, h] of children) yield [n, h]; },
    getDirectoryHandle: async (name: string, opts?: { create?: boolean }) => {
      let d = children.get(name);
      if (!d) {
        if (!opts?.create) throw new DOMException('x', 'NotFoundError');
        d = mockKit(name, {}); children.set(name, d); created[name] = d;
      }
      return d;
    },
    // The same-folder handshake (bd polyglot-pdf-ball) writes a nonce marker
    // into the ROOT and removes it after. Files created here are tracked in
    // `files` so a test can assert the marker was cleaned up.
    files,
    getFileHandle: async (fn: string, opts?: { create?: boolean }) => {
      let f = files.get(fn);
      if (!f) {
        if (!opts?.create) throw new DOMException('x', 'NotFoundError');
        f = mockFile(fn); files.set(fn, f);
      }
      return f;
    },
    removeEntry: async (fn: string) => { files.delete(fn); },
  };
}

const SCHEMA = JSON.stringify({ form_metadata: { title: 'X' }, fields: [] });

// bd tynm parity: the card grid is collapsed by default behind the compact
// selector strip; expand it so a test that asserts card-level content (labels,
// status toggles, Run-extraction, review bars) can see the cards. Waits for the
// toggle to appear (it renders only once a folder with kits has loaded).
async function expandCards() {
  await waitFor(() => expect(screen.getByText('Show form cards')).toBeTruthy());
  fireEvent.click(screen.getByText('Show form cards'));
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).showDirectoryPicker;
  vi.clearAllMocks();
});

describe('FormCatalogue', () => {
  beforeEach(() => {
    (window as unknown as Record<string, unknown>).showDirectoryPicker = undefined;
  });

  it('shows an unsupported message when the directory API is absent', () => {
    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    expect(screen.getByText(/does not support the File System Access/i)).toBeTruthy();
  });

  it('opens a folder and lists the kits with status badges', async () => {
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
      mockKit('n-400', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'N-400', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await waitFor(() => expect(screen.getByText('I-90')).toBeTruthy());
    expect(screen.getByText('N-400')).toBeTruthy();
    expect(screen.getByText('complete')).toBeTruthy();
    expect(screen.getByText('draft')).toBeTruthy();
  });

  it('opens a kit when its card is clicked', async () => {
    const root = mockRoot([mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) })]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
    const onOpenKit = vi.fn();

    render(<FormCatalogue onOpenKit={onOpenKit} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('I-90')).toBeTruthy());

    fireEvent.click(screen.getByText('I-90'));
    expect(onOpenKit).toHaveBeenCalledWith(expect.objectContaining({ id: 'i-90' }));
  });

  it('onboards a dropped PDF into a new kit (added, not auto-opened)', async () => {
    const root = mockRoot([]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
    const onOpenKit = vi.fn();

    render(<FormCatalogue onOpenKit={onOpenKit} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(screen.getByText(/0 forms/)).toBeTruthy());

    const pdf = { name: 'Form I-90.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(4) } as unknown as File;
    fireEvent.drop(screen.getByTestId('form-catalogue'), { dataTransfer: { files: [pdf] } });

    // The new kit folder is created and surfaced as a notice, but NOT auto-opened
    // (it has no schema yet -- opening it would error; fresh-eyes finding).
    await waitFor(() => expect(screen.getByText(/Added "form-i-90"/)).toBeTruthy());
    expect(root.created['form-i-90']).toBeTruthy();
    expect(onOpenKit).not.toHaveBeenCalled();
  });

  it('clears the "Added" notice when the folder is changed', async () => {
    const root = mockRoot([]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(screen.getByText(/0 forms/)).toBeTruthy());

    const pdf = { name: 'a.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(4) } as unknown as File;
    fireEvent.drop(screen.getByTestId('form-catalogue'), { dataTransfer: { files: [pdf] } });
    await waitFor(() => expect(screen.getByText(/Added "a"/)).toBeTruthy());

    // Change folder -> the stale success notice must be gone.
    fireEvent.click(screen.getByText('Change folder'));
    await waitFor(() => expect(screen.queryByText(/Added "a"/)).toBeNull());
  });

  it('errors when a non-PDF is dropped', async () => {
    const root = mockRoot([]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(screen.getByText(/0 forms/)).toBeTruthy());

    const txt = { name: 'notes.txt', type: 'text/plain' } as unknown as File;
    const dropZone = screen.getByTestId('form-catalogue');
    fireEvent.drop(dropZone, { dataTransfer: { files: [txt] } });
    await waitFor(() => expect(screen.getByText(/Drop an AcroForm PDF/i)).toBeTruthy());
  });

  // --- D3 dashboard: aggregate overview + per-form review % (bd vl3o) -------- //

  it('shows an aggregate overview of complete vs in-progress forms', async () => {
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
      mockKit('n-400', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'N-400', status: 'draft' }) }),
      mockKit('g-28', { 'metadata.json': JSON.stringify({ label: 'G-28', status: 'draft' }) }), // no schema
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

    const summary = await screen.findByTestId('catalogue-summary');
    expect(summary.textContent).toMatch(/3 forms/);
    expect(summary.textContent).toMatch(/1 complete/);
    expect(summary.textContent).toMatch(/1 in progress/);
    expect(summary.textContent).toMatch(/1 awaiting extraction/);
  });

  it('shows a per-form review percentage from the kit READINESS STAMP', async () => {
    // Sprint-18 C4 (bd polyglot-pdf-g687): the card renders the stamp the
    // BACKEND wrote into metadata.json with publish_readiness -- the same
    // definition the open editor's strip mirrors -- rather than re-deriving a
    // percentage from the schema on disk. The schema below is fully signed off,
    // but it is the STAMP that supplies the number.
    const fullSchema = JSON.stringify({
      form_metadata: { form_number: 'T-1' }, sections: [],
      fields: [{
        id: 'f1', name: 'f1', type: 'text', pdf_field_name: 'f1',
        read_only: false, spoken_name: 'first',
        help: { instructions: 'Enter it.' },
        _review: { status: 'reviewed_correct' },
      }],
    });
    const root = mockRoot([
      mockKit('done', {
        'schema.json': fullSchema,
        'metadata.json': JSON.stringify({
          label: 'Done', status: 'complete',
          readiness: {
            reviewed: 1, toReview: 0, total: 1, errors: 0, percent: 100,
            ready: true, verified: true, schema_sha1: 'abc123',
          },
        }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('Done');
    await waitFor(() => expect(screen.getByText('100%')).toBeTruthy());
  });

  it('a 199-of-200 kit shows a YELLOW bar, not a green 100% one (bd polyglot-pdf-87zbs)', async () => {
    // pct is a ROUNDED percentage (Math.round(199/200*100) === 100), so a
    // predicate keyed on pct===100 alone paints a confident green "finished"
    // bar on a kit that still has 1 unreviewed field -- directly contradicting
    // this same card's own hover title ("199 of 200 fields complete") right
    // next to it, and the publish gate that will still refuse it.
    const fullSchema = JSON.stringify({
      form_metadata: { form_number: 'T-1' }, sections: [],
      fields: [{
        id: 'f1', name: 'f1', type: 'text', pdf_field_name: 'f1',
        read_only: false, spoken_name: 'first',
        help: { instructions: 'Enter it.' },
        _review: { status: 'reviewed_correct' },
      }],
    });
    const root = mockRoot([
      mockKit('almost-done', {
        'schema.json': fullSchema,
        'metadata.json': JSON.stringify({
          label: 'Almost Done', status: 'draft',
          readiness: {
            reviewed: 199, toReview: 0, total: 200, errors: 0, percent: 100,
            ready: false, verified: true, schema_sha1: 'abc123',
          },
        }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('Almost Done');
    await waitFor(() => expect(screen.getByText('100%')).toBeTruthy());

    const bars = document.querySelectorAll('.h-full');
    const progressBars = Array.from(bars).filter((el) =>
      el.className.includes('bg-green-500') || el.className.includes('bg-yellow-500'));
    expect(progressBars.length).toBe(1);
    expect(progressBars[0].className).toContain('bg-yellow-500');
    expect(progressBars[0].className).not.toContain('bg-green-500');
  });

  it('a genuinely complete (200-of-200) kit still shows a GREEN bar', async () => {
    // Regression guard for the fix above: the exact-ratio predicate must
    // still recognize TRUE completion, not just stop recognizing 100%.
    const fullSchema = JSON.stringify({
      form_metadata: { form_number: 'T-1' }, sections: [],
      fields: [{
        id: 'f1', name: 'f1', type: 'text', pdf_field_name: 'f1',
        read_only: false, spoken_name: 'first',
        help: { instructions: 'Enter it.' },
        _review: { status: 'reviewed_correct' },
      }],
    });
    const root = mockRoot([
      mockKit('really-done', {
        'schema.json': fullSchema,
        'metadata.json': JSON.stringify({
          label: 'Really Done', status: 'complete',
          readiness: {
            reviewed: 200, toReview: 0, total: 200, errors: 0, percent: 100,
            ready: true, verified: true, schema_sha1: 'abc123',
          },
        }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('Really Done');
    await waitFor(() => expect(screen.getByText('100%')).toBeTruthy());

    const bars = document.querySelectorAll('.h-full');
    const progressBars = Array.from(bars).filter((el) =>
      el.className.includes('bg-green-500') || el.className.includes('bg-yellow-500'));
    expect(progressBars.length).toBe(1);
    expect(progressBars[0].className).toContain('bg-green-500');
  });

  it('the compact STRIP dropdown shows no percentage for an unstamped kit (bd g687)', async () => {
    // The strip is the DEFAULT view (cards are behind "Show form cards"), and
    // it originally kept reading the local disk re-scan -- so it printed a
    // client-recomputed number while the card below showed the verify hint
    // (fresh-eyes gap 1). Deliberately does NOT expand the cards: this pins the
    // strip on its own.
    //
    // The schema is FULLY REVIEWED so a restored re-scan would print a loud
    // "100%", not a 0% that is easy to confuse with "no number".
    const reviewedSchema = JSON.stringify({
      form_metadata: { form_number: 'T-1' }, sections: [],
      fields: [{
        id: 'f1', name: 'f1', type: 'text', pdf_field_name: 'f1',
        read_only: false, spoken_name: 'first',
        help: { instructions: 'Enter it.' },
        _review: { status: 'reviewed_correct' },
      }],
    });
    const root = mockRoot([
      mockKit('a', {
        'schema.json': reviewedSchema,
        'metadata.json': JSON.stringify({ label: 'Kit A', status: 'draft' }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

    await waitFor(() => expect(screen.getByText('Show form cards')).toBeTruthy());
    // The strip lists the kit but attaches no percentage of any value...
    await waitFor(() => expect(screen.getByRole('option', { name: /Kit A/ })).toBeTruthy());
    const optText = screen.getByRole('option', { name: /Kit A/ }).textContent ?? '';
    expect(optText).not.toMatch(/\d+%/);
    // ...and it SAYS WHY. Withholding the number alone left the default view
    // (cards are collapsed) silently missing a percentage with no explanation
    // -- and since no shipped kit carries a stamp yet, that is every kit. The
    // card's full sentence would be unusable in an <option>, so the strip
    // carries the same message compressed (both Opus outer reviewers).
    expect(optText).toContain('not measured');
  });

  it('an UNREADABLE schema shows the corruption notice, never a stamped % (bd g687)', async () => {
    // The local twin of the RemoteCatalogue test. Round 3 fixed BOTH files but
    // tested only the hosted one, so this half could have silently regressed --
    // which is how the pair got out of sync to begin with (Opus fresh-eyes
    // round 4). Covers the card AND the strip: neither may print a stale
    // stamp's number for a schema nobody can read.
    const root = mockRoot([
      mockKit('a', {
        'schema.json': 'not json{',
        'metadata.json': JSON.stringify({
          label: 'Kit A', status: 'draft',
          readiness: {
            reviewed: 3, toReview: 1, total: 4, errors: 0, percent: 75,
            ready: false, verified: true, schema_sha1: 'abc123',
          },
        }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

    // The STRIP (default view) must not carry the stale percentage...
    await waitFor(() => expect(screen.getByRole('option', { name: /Kit A/ })).toBeTruthy());
    expect(screen.getByRole('option', { name: /Kit A/ }).textContent).not.toMatch(/\d+%/);

    // ...and the card says plainly that the schema cannot be read.
    await expandCards();
    await waitFor(() =>
      expect(screen.getByText(/Schema present but unreadable/)).toBeTruthy());
    expect(screen.queryByText('75%')).not.toBeInTheDocument();
  });

  it('the compact STRIP dropdown shows the STAMPED percentage (bd g687)', async () => {
    const root = mockRoot([
      mockKit('a', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({
          label: 'Kit A', status: 'draft',
          readiness: {
            reviewed: 1, toReview: 3, total: 4, errors: 0, percent: 25,
            ready: false, verified: true, schema_sha1: 'abc123',
          },
        }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

    await waitFor(() =>
      expect(screen.getByRole('option', { name: /Kit A/ }).textContent).toMatch(/25%/));
  });

  it('shows the verify hint for an UNSTAMPED kit, and nothing for a no-schema kit', async () => {
    // Sprint-18 C4: a schema-bearing kit with no readiness stamp cannot be
    // given a percentage -- nobody measured it -- so the card shows the verify
    // hint. A kit with NO schema has nothing to measure and gets neither a
    // number nor a hint (it already reads as awaiting extraction).
    const root = mockRoot([
      mockKit('empty', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'Empty', status: 'draft' }) }),
      mockKit('raw', { 'metadata.json': JSON.stringify({ label: 'Raw', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('Empty');
    // Exactly one hint: the schema-bearing kit. No percentage anywhere, and no
    // review bar (the bar renders only alongside a trustworthy number).
    await waitFor(() =>
      expect(screen.getAllByTestId('readiness-hint')).toHaveLength(1));
    expect(screen.queryByText(/^\d+%$/)).not.toBeInTheDocument();
    expect(screen.queryAllByText('Review')).toHaveLength(0);
  });

  it('persists the live percentage after the kit stops being live (no revert to stale scan)', async () => {
    // Codex round 4 / bd 8srh: after editing+saving kit A then opening B, A's card
    // must keep the edited % instead of reverting to the disk-scan value. The
    // catalogue caches the last live value into its progress map.
    const root = mockRoot([
      mockKit('a', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'Kit A', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    // Real sequence: open the folder first (no kit open yet)...
    const { rerender } = render(
      <FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await screen.findByText('Kit A');

    // ...then the user opens Kit A and edits it (liveProgress appears at 60%)...
    rerender(
      <FormCatalogue
        onOpenKit={vi.fn()}
        selectedKitId="a"
        liveProgress={{ kitId: 'a', saved: true, percent: 60, complete: 3, total: 5 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('60%')).toBeTruthy());

    // ...then Kit A is deselected (user opened a different kit) -> liveProgress gone.
    rerender(
      <FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />,
    );
    // A's card still shows the persisted 60%, not the disk scan's 0%.
    expect(screen.getByText('60%')).toBeTruthy();
    expect(screen.queryByText('0%')).toBeNull();
  });

  it('lets Refresh replace a cached kit percentage with the fresh stamp', async () => {
    // Codex round 6, carried to the stamp (sprint-18 C4): after a saved edit
    // caches 60%, a deliberate Refresh must re-read from disk and let THAT win
    // -- the session cache cannot outrank an explicit Refresh. The disk value
    // is now the kit's readiness stamp (25%) rather than a re-scan.
    //
    // KNOWN CONSEQUENCE, tracked as bd polyglot-pdf-bqgr: in LOCAL mode
    // nothing writes a stamp (local save is a pure File System Access write),
    // so this "disk wins" rule can move the number BACKWARD after a local
    // save -- the opposite of what Refresh used to mean. This test encodes the
    // precedence, NOT an endorsement of that outcome; bqgr decides whether
    // local save stamps or local mode keeps a client-side fallback.
    const root = mockRoot([
      mockKit('a', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({
          label: 'Kit A', status: 'draft',
          readiness: {
            reviewed: 1, toReview: 3, total: 4, errors: 0, percent: 25,
            ready: false, verified: true, schema_sha1: 'abc123',
          },
        }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    const { rerender } = render(
      <FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await screen.findByText('Kit A');

    // Save an edit -> 60% cached for A.
    rerender(
      <FormCatalogue
        onOpenKit={vi.fn()}
        selectedKitId="a"
        liveProgress={{ kitId: 'a', saved: true, percent: 60, complete: 3, total: 5 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('60%')).toBeTruthy());

    // Deselect (cache holds 60%) then click Refresh -> the stamp (25%) wins.
    rerender(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />);
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => expect(screen.getByText('25%')).toBeTruthy());
    expect(screen.queryByText('60%')).toBeNull();
  });

  it('keeps a cached saved percentage across a non-deliberate (post-onboard) scan', async () => {
    // Codex round 7: only a deliberate Refresh clears the cache; an automatic scan
    // (e.g. the re-scan after onboarding a dropped PDF) must NOT wipe a just-saved
    // cached value, else the post-save revert returns.
    const root = mockRoot([
      mockKit('a', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'Kit A', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    const { rerender } = render(
      <FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await screen.findByText('Kit A');

    // Save an edit -> 60% cached for A, then deselect.
    rerender(
      <FormCatalogue
        onOpenKit={vi.fn()}
        selectedKitId="a"
        liveProgress={{ kitId: 'a', saved: true, percent: 60, complete: 3, total: 5 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('60%')).toBeTruthy());
    rerender(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />);

    // A non-deliberate scan (drop a PDF -> post-onboard refresh) must keep 60%.
    const pdf = { name: 'b.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(4) } as unknown as File;
    fireEvent.drop(screen.getByTestId('form-catalogue'), { dataTransfer: { files: [pdf] } });
    await waitFor(() => expect(screen.getByText(/Added "b"/)).toBeTruthy());
    expect(screen.getByText('60%')).toBeTruthy(); // cache survived the auto-scan
  });

  it('does NOT persist an UNSAVED edit after the kit is deselected (discard flow)', async () => {
    // Codex round 5, carried to the stamp (sprint-18 C4): an unsaved edit shows
    // live on the open card, but if the user discards it (switches kits without
    // saving), the card must revert to the kit's RECORDED value (25%), never
    // keep phantom progress from an edit that was thrown away.
    const root = mockRoot([
      mockKit('a', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({
          label: 'Kit A', status: 'draft',
          readiness: {
            reviewed: 1, toReview: 3, total: 4, errors: 0, percent: 25,
            ready: false, verified: true, schema_sha1: 'abc123',
          },
        }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    const { rerender } = render(
      <FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await screen.findByText('Kit A');

    // User opens A and edits it WITHOUT saving (saved:false) -> 60% shows live.
    rerender(
      <FormCatalogue
        onOpenKit={vi.fn()}
        selectedKitId="a"
        liveProgress={{ kitId: 'a', saved: false, percent: 60, complete: 3, total: 5 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('60%')).toBeTruthy());

    // Edit discarded, kit deselected -> revert to the recorded 25%, NOT 60%.
    rerender(
      <FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />,
    );
    expect(screen.getByText('25%')).toBeTruthy();
    expect(screen.queryByText('60%')).toBeNull();
  });

  it('overrides the open kit bar with the live in-editor percentage', async () => {
    // The disk schema is empty (0%); liveProgress reports 75% for the open kit, so
    // the card must show 75% (tracks unsaved edits), not the stale 0% (Codex finding).
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(
      <FormCatalogue
        onOpenKit={vi.fn()}
        selectedKitId="i-90"
        liveProgress={{ kitId: 'i-90', saved: false, percent: 75, complete: 3, total: 4 }}
      />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('I-90');
    await waitFor(() => expect(screen.getByText('75%')).toBeTruthy());
    expect(screen.queryByText('0%')).toBeNull();
  });

  it('promotes a draft kit to complete via the status toggle (bd nr8u)', async () => {
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await screen.findByText('I-90');
    expect(screen.getByText('draft')).toBeTruthy();

    // Click "Mark complete" -> writes status:complete, re-scans, badge updates.
    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() => expect(screen.getByText('complete')).toBeTruthy());
    // The toggle now offers the reverse action.
    expect(screen.getByText('Revert to draft')).toBeTruthy();

    // The metadata.json on disk now carries status:complete (preserved label).
    const metaText = await (await root.children.get('i-90')!.children.get('metadata.json')!.getFile()).text();
    const meta = JSON.parse(metaText);
    expect(meta.status).toBe('complete');
    expect(meta.label).toBe('I-90');
  });

  it('does not show a status toggle for a kit with no schema', async () => {
    const root = mockRoot([
      mockKit('raw', { 'metadata.json': JSON.stringify({ label: 'Raw', status: 'draft' }) }), // no schema
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await screen.findByText('Raw');
    expect(screen.queryByText('Mark complete')).toBeNull(); // schema-less -> no toggle
  });

  it('shows an unreadable-schema notice (distinct from no schema)', async () => {
    const root = mockRoot([
      mockKit('broken', { 'schema.json': 'not json{', 'metadata.json': JSON.stringify({ label: 'Broken', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('Broken');
    await waitFor(() => expect(screen.getByText(/Schema present but unreadable/i)).toBeTruthy());
  });

  it('aborts the folder switch (no picker, no clear) when confirmFolderChange returns false', async () => {
    // Codex P0: switching folders with unsaved edits must be confirmable; a false
    // return (user declined) means the picker is never opened and the open kit is
    // never cleared.
    const root = mockRoot([mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90' }) })]);
    const picker = vi.fn(async () => root);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = picker;
    const confirmFolderChange = vi.fn(() => false); // user declined to discard edits
    const clearOpenKit = vi.fn();

    render(
      <FormCatalogue
        onOpenKit={vi.fn()}
        confirmFolderChange={confirmFolderChange}
        clearOpenKit={clearOpenKit}
        selectedKitId="i-90"
      />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));

    expect(confirmFolderChange).toHaveBeenCalled();
    expect(picker).not.toHaveBeenCalled(); // aborted before opening the picker
    expect(clearOpenKit).not.toHaveBeenCalled(); // open kit left intact
  });

  it('does NOT clear the open kit when the picker is cancelled', async () => {
    // Codex round 4: clearing before the picker would discard the open kit even if
    // the user then cancels the native picker. clearOpenKit runs only on success.
    const confirmFolderChange = vi.fn(() => true);
    const clearOpenKit = vi.fn();
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => {
      throw new DOMException('cancelled', 'AbortError');
    });

    render(
      <FormCatalogue
        onOpenKit={vi.fn()}
        confirmFolderChange={confirmFolderChange}
        clearOpenKit={clearOpenKit}
        selectedKitId="i-90"
      />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(confirmFolderChange).toHaveBeenCalled());
    expect(clearOpenKit).not.toHaveBeenCalled(); // cancelled -> kit intact
  });

  it('clears the open kit after the picker successfully returns a folder', async () => {
    const root = mockRoot([mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90' }) })]);
    const clearOpenKit = vi.fn();
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(
      <FormCatalogue
        onOpenKit={vi.fn()}
        confirmFolderChange={vi.fn(() => true)}
        clearOpenKit={clearOpenKit}
        selectedKitId="i-90"
      />,
    );
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(clearOpenKit).toHaveBeenCalled());
  });
});

// --- Compact selector strip (bd tynm parity) ------------------------------- //
//
// The card grid is collapsed by default behind a dropdown + Show/Hide toggle, so
// the header gives its vertical space to the editor (the same behavior the hosted
// RemoteCatalogue already had). These mirror RemoteCatalogue's strip tests.
describe('FormCatalogue -- compact selector strip (bd tynm)', () => {
  beforeEach(() => {
    (window as unknown as Record<string, unknown>).showDirectoryPicker = undefined;
  });

  it('collapses the card grid by default; the dropdown lists every kit', async () => {
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
      mockKit('raw', { 'metadata.json': JSON.stringify({ label: 'Raw', status: 'draft' }) }), // no schema
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

    // The dropdown appears; no card buttons render in the collapsed default.
    await waitFor(() => expect(screen.getByLabelText('Select a form')).toBeTruthy());
    expect(screen.queryByTitle('Open I-90 for editing')).toBeNull();
    const select = screen.getByLabelText('Select a form') as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.text);
    expect(labels.some((t) => t.includes('I-90'))).toBe(true);
    // A schemaless kit is listed too, tagged so the user knows it can't be opened.
    expect(labels.some((t) => t.includes('Raw') && t.includes('no schema yet'))).toBe(true);
  });

  it('selecting a schema-bearing kit opens it; a schemaless kit only selects', async () => {
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
      mockKit('raw', { 'metadata.json': JSON.stringify({ label: 'Raw', status: 'draft' }) }), // no schema
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
    const onOpenKit = vi.fn();

    render(<FormCatalogue onOpenKit={onOpenKit} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(screen.getByLabelText('Select a form')).toBeTruthy());
    const select = screen.getByLabelText('Select a form');

    fireEvent.change(select, { target: { value: 'i-90' } });
    expect(onOpenKit).toHaveBeenCalledWith(expect.objectContaining({ id: 'i-90' }));

    // A schemaless kit can be selected in the dropdown but is not "opened".
    onOpenKit.mockClear();
    fireEvent.change(select, { target: { value: 'raw' } });
    expect(onOpenKit).not.toHaveBeenCalled();
  });

  it('the toggle expands the full card grid and collapses it again', async () => {
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(screen.getByText('Show form cards')).toBeTruthy());

    // Collapsed: no card. Expand -> the card appears. Collapse -> it is gone.
    expect(screen.queryByTitle('Open I-90 for editing')).toBeNull();
    fireEvent.click(screen.getByText('Show form cards'));
    expect(screen.getByTitle('Open I-90 for editing')).toBeTruthy();
    fireEvent.click(screen.getByText('Hide form cards'));
    expect(screen.queryByTitle('Open I-90 for editing')).toBeNull();
  });

  it('returns to the collapsed default after changing folders', async () => {
    // A fresh folder open resets the grid to collapsed -- expanding folder A must
    // not leave folder B expanded (fresh-eyes finding on bd rykl).
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(screen.getByText('Show form cards')).toBeTruthy());

    // Expand the grid for the first folder...
    fireEvent.click(screen.getByText('Show form cards'));
    expect(screen.getByTitle('Open I-90 for editing')).toBeTruthy();

    // ...then change folders: the grid must be collapsed again for the new folder.
    fireEvent.click(screen.getByText('Change folder'));
    await waitFor(() => expect(screen.getByText('Show form cards')).toBeTruthy());
    expect(screen.queryByTitle('Open I-90 for editing')).toBeNull();
  });
});

// --- Run-extraction button (bd 7a9.17) ------------------------------------- //
//
// A schemaless kit WITH a pdf gets a "Run extraction" button ONLY when the host
// endpoint is reachable (vite dev). We drive both the GET capability probe and
// the POST extraction through a mocked fetch.
describe('FormCatalogue -- run extraction', () => {
  // A PDF-only kit (form.pdf present, no schema.json) is the button's precondition.
  const pdfOnlyKit = () =>
    mockKit('w7', { 'form.pdf': 'PDF', 'metadata.json': JSON.stringify({ label: 'W7', status: 'draft' }) });

  function fetchMock(handlers: {
    get?: () => Response;
    post?: (body: unknown) => Response;
    /**
     * The same-folder handshake (bd polyglot-pdf-ball). Extraction is gated on
     * it, so it DEFAULTS to agreement -- otherwise every test here would be
     * testing the refusal instead of what it was written to test. Override it to
     * exercise the refusal itself.
     */
    handshake?: (body: unknown) => Response;
  }): typeof fetch {
    const impl = async (input: unknown, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'GET') {
        return handlers.get?.() ?? ({ ok: false, status: 404, json: async () => ({}) } as unknown as Response);
      }
      const body = init?.body ? JSON.parse(init.body as string) : {};
      // Route by URL: the handshake and the extraction are both POSTs.
      if (String(input).endsWith('/handshake')) {
        return handlers.handshake?.(body)
          ?? (okJson({ sameFolder: true, extractorRoot: '/repo/form-kits' }));
      }
      return handlers.post?.(body) ?? ({ ok: false, status: 500, json: async () => ({ ok: false, detail: 'x' }) } as unknown as Response);
    };
    return vi.fn(impl) as unknown as typeof fetch;
  }
  const okJson = (b: unknown) => ({ ok: true, status: 200, json: async () => b } as unknown as Response);
  const errJson = (b: unknown) => ({ ok: false, status: 500, json: async () => b } as unknown as Response);

  afterEach(() => { vi.restoreAllMocks(); });

  it('hides the button (shows the manual hint) when the endpoint is absent', async () => {
    global.fetch = fetchMock({ get: () => ({ ok: false, status: 404, json: async () => ({}) } as unknown as Response) });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('W7')).toBeTruthy());

    // No button; the degraded instruction hint is shown instead.
    expect(screen.queryByText('Run extraction')).toBeNull();
    expect(screen.getByText(/Run the extractor to produce its schema/i)).toBeTruthy();
  });

  it('shows the button for a schemaless+pdf kit when the endpoint is available', async () => {
    global.fetch = fetchMock({ get: () => okJson({ ok: true, detail: 'available' }) });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());
  });

  it('does NOT show the button for a kit that already has a schema', async () => {
    global.fetch = fetchMock({ get: () => okJson({ ok: true, detail: 'available' }) });
    const root = mockRoot([
      mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('I-90')).toBeTruthy());
    expect(screen.queryByText('Run extraction')).toBeNull();
  });

  it('runs extraction on click and surfaces the success notice', async () => {
    let posted: unknown = null;
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: (body) => { posted = body; return okJson({ ok: true, detail: '61 fields, validated', schemaFile: 'schema.json' }); },
    });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(screen.getByText(/Extracted "w7"/)).toBeTruthy());
    // The kit id (and resolved filenames) reached the endpoint.
    expect(posted).toMatchObject({ id: 'w7', pdfFile: 'form.pdf', schemaFile: 'schema.json' });
  });

  it('threads a selected instructions PDF into the kit dir AND the POST (bd s4dp.3)', async () => {
    let posted: Record<string, unknown> | null = null;
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: (body) => { posted = body as Record<string, unknown>; return okJson({ ok: true, detail: 'done', schemaFile: 'schema.json' }); },
    });
    const kit = pdfOnlyKit();
    const root = mockRoot([kit]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    // Pick an instructions PDF via the hidden file input (the "+ instructions PDF" label).
    // jsdom's File lacks arrayBuffer(); supply it the way the drop tests do.
    const instrPdf = { name: 'i90-instructions.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(5) } as unknown as File;
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [instrPdf] } });
    // The label reflects the chosen filename.
    await waitFor(() => expect(screen.getByText(/instructions: i90-instructions\.pdf/)).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(screen.getByText(/Extracted "w7"/)).toBeTruthy());

    // The endpoint got the fixed in-kit filename, and the file was written there.
    expect(posted).toMatchObject({ id: 'w7', instructionsPdfFile: 'instructions.pdf' });
    expect(kit.children.has('instructions.pdf')).toBe(true);
  });

  it('rejects a non-PDF instructions selection and does not thread it (Codex PR #274)', async () => {
    let posted: Record<string, unknown> | null = null;
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: (body) => { posted = body as Record<string, unknown>; return okJson({ ok: true, detail: 'done', schemaFile: 'schema.json' }); },
    });
    const kit = pdfOnlyKit();
    const root = mockRoot([kit]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;

    // First pick a VALID PDF, so we can prove a later bad pick CLEARS it.
    const goodPdf = { name: 'good.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(4) } as unknown as File;
    fireEvent.change(input, { target: { files: [goodPdf] } });
    await waitFor(() => expect(screen.getByText(/instructions: good\.pdf/)).toBeTruthy());

    // Now pick a non-PDF (text) file: the accept filter is advisory, so this is possible.
    const txt = { name: 'notes.txt', type: 'text/plain',
      arrayBuffer: async () => new ArrayBuffer(3) } as unknown as File;
    fireEvent.change(input, { target: { files: [txt] } });
    // Surfaced as an error; the bad file is NOT stored AND the prior good pick is
    // cleared (label returns to the "+ instructions PDF" prompt) -- no contradictory state.
    await waitFor(() => expect(screen.getByText(/instructions file must be a PDF/i)).toBeTruthy());
    expect(screen.queryByText(/instructions: notes\.txt/)).toBeNull();
    expect(screen.queryByText(/instructions: good\.pdf/)).toBeNull();

    // Running extraction now carries NO instructions file (the bad pick was dropped)
    // and writes nothing extra into the kit dir.
    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(screen.getByText(/Extracted "w7"/)).toBeTruthy());
    expect((posted as unknown as Record<string, unknown>)?.instructionsPdfFile).toBeUndefined();
    expect(kit.children.has('instructions.pdf')).toBe(false);
  });

  it('omits instructionsPdfFile from the POST when none is selected (/TU-only)', async () => {
    let posted: Record<string, unknown> | null = null;
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: (body) => { posted = body as Record<string, unknown>; return okJson({ ok: true, detail: 'done', schemaFile: 'schema.json' }); },
    });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(screen.getByText(/Extracted "w7"/)).toBeTruthy());
    // No instructions PDF selected -> the key is absent/undefined (server falls back to /TU).
    expect((posted as unknown as Record<string, unknown>)?.instructionsPdfFile).toBeUndefined();
  });

  it('surfaces an error notice when extraction fails', async () => {
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: () => errJson({ ok: false, detail: 'extraction failed (exit 1): boom' }),
    });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(screen.getByText(/Extraction failed for "w7".*boom/i)).toBeTruthy());
  });

  // --- same-folder gate (bd polyglot-pdf-ball) ------------------------------ //
  //
  // The extractor resolves the kit id against the VITE HOST's FORM_KITS_ROOT and
  // WRITES schema.json there. Point the editor at a copy elsewhere whose kit id
  // also exists under that root, and "Run extraction" silently overwrites the
  // HOST's copy while the catalogue refreshes the picked one and shows no change.
  // These pin the refusal, so the gate cannot be dropped silently.
  //
  // NOT covered by the App-level serverActionsOk gate (bd polyglot-pdf-s2bf):
  // that proves agreement with the FastAPI backend's FORM_KITS_LOCAL_ROOT, a
  // SEPARATE setting from the Vite host's root.

  it('REFUSES to extract when the picked folder is not the extractor host root', async () => {
    let posted: unknown = null;
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: (body) => { posted = body; return okJson({ ok: true, detail: 'done', schemaFile: 'schema.json' }); },
      // The host cannot see the nonce the browser just wrote -- it is looking at
      // a different directory.
      handshake: () => okJson({ sameFolder: false, reason: 'mismatch', extractorRoot: '/repo/form-kits' }),
    });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));

    // THE INVARIANT: no extraction POST is made, so nothing on the host is
    // overwritten. This is the assertion the bug would break.
    await waitFor(() => expect(screen.getByText(/not the one the extractor uses/i)).toBeTruthy());
    expect(posted).toBeNull();
    // The message names the folder the extractor would have written to.
    expect(screen.getByText(/\/repo\/form-kits/)).toBeTruthy();
  });

  it('does NOT write the instructions PDF into the kit when the folder is refused', async () => {
    // Second-order bug in the bead: the browser writes instructions.pdf into the
    // PICKED kit dir while the endpoint looks for it under the HOST's root, so a
    // mismatched folder left a stray file behind AND 400d. Gate first, write after.
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      handshake: () => okJson({ sameFolder: false, reason: 'mismatch', extractorRoot: '/repo/form-kits' }),
    });
    const kit = pdfOnlyKit();
    const root = mockRoot([kit]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    // Pick an instructions PDF via the hidden file input, as the s4dp.3 test does
    // (jsdom's File lacks arrayBuffer(), so supply it).
    const instrPdf = { name: 'instr.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(5) } as unknown as File;
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [instrPdf] } });

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(screen.getByText(/not the one the extractor uses/i)).toBeTruthy());
    expect(kit.children.has('instructions.pdf')).toBe(false);
  });

  it('refuses when the picked folder cannot be written to, pointing at the HOST root', async () => {
    // verifySameFolder cannot even drop its marker -- a read-only source folder
    // is not a viable extraction target either way.
    let posted: unknown = null;
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: (body) => { posted = body; return okJson({ ok: true, detail: 'done' }); },
    });
    const root = mockRoot([pdfOnlyKit()]);
    root.getFileHandle = async () => { throw new DOMException('read-only', 'NotAllowedError'); };
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    const msg = await screen.findByText(/cannot be written to/i);
    expect(posted).toBeNull();
    // The advice must lead somewhere that WORKS (bd polyglot-pdf-6pzs). The s2bf
    // modal's "make a copy and open that" is right for SAVING but is a dead end
    // here: extraction always writes under the HOST's root, so ANY copy is by
    // construction not that root and the next click just fails the mismatch
    // branch instead.
    //
    // ALLOWLIST, not a blacklist. Two earlier versions of this test failed to
    // hold, each time because they described the WRONG advice instead of the
    // right advice:
    //   v1 banned the literal s2bf sentence -> a reworded copy-elsewhere ("open
    //      a writable COPY of the folder the dev server uses") sailed through.
    //   v2 banned the word "copy" -> "DUPLICATE it somewhere writable" sailed
    //      through. Every blacklist is one synonym from being defeated.
    // So pin what the message may SAY. This branch has exactly two remedies that
    // reach a working state -- make this folder writable, or open the server's
    // own folder -- and anything else is a bug regardless of how it is worded.
    const SANCTIONED = [
      /make this folder writable/i,
      /open the folder the dev server uses/i,
    ];
    for (const remedy of SANCTIONED) expect(msg.textContent).toMatch(remedy);
    // Strip the sanctioned remedies and the framing, then require that NO further
    // instruction survives. A third remedy -- copy, duplicate, clone, "point
    // FORM_KITS_ROOT at...", anything -- leaves residue here and fails, without
    // this test having to guess the word.
    const residue = (msg.textContent ?? '')
      .replace(/Cannot run extraction for "[^"]*":/i, '')
      .replace(/the folder you opened cannot be written to, so the editor cannot confirm it is the folder the extractor uses\./i, '')
      .replace(SANCTIONED[0], '')
      .replace(SANCTIONED[1], '')
      .replace(/[\s,.;:-]|\bor\b/gi, '');
    expect(residue).toBe('');
  });

  it('treats an unreachable handshake as UNPROVEN, not as agreement', async () => {
    // Fail-closed: a network error must never read as "same folder", because the
    // action it gates is a destructive overwrite.
    let posted: unknown = null;
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: (body) => { posted = body; return okJson({ ok: true, detail: 'done' }); },
      handshake: () => { throw new Error('network down'); },
    });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    // Refused (fail-closed) -- but NOT with the wrong-folder diagnosis. The host
    // never answered, so claiming the folder is wrong would send the user to
    // change configuration that is actually correct (same defect class as bd
    // polyglot-pdf-6pzs, one branch over).
    await waitFor(() => expect(screen.getByText(/could not reach the extraction service/i)).toBeTruthy());
    expect(screen.queryByText(/not the one the extractor uses/i)).toBeNull();
    expect(posted).toBeNull();
  });

  it('sends a FRESH nonce per check and cleans the marker up afterwards', async () => {
    // A per-check nonce is what makes a leftover marker read as stale rather
    // than as a false match.
    const nonces: string[] = [];
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: () => okJson({ ok: true, detail: 'done', schemaFile: 'schema.json' }),
      handshake: (body) => {
        nonces.push((body as { nonce: string }).nonce);
        return okJson({ sameFolder: true, extractorRoot: '/repo/form-kits' });
      },
    });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    await waitFor(() => expect(screen.getByText(/Extracted "w7"/)).toBeTruthy());

    expect(nonces).toHaveLength(1);
    expect(nonces[0]).toBeTruthy();
    // The marker does not outlive the check.
    expect(root.files.has('.editor-extract-check.json')).toBe(false);
  });

  it('disables folder controls and refuses drops WHILE extraction is in flight (Codex r3)', async () => {
    // Hold the POST open so extraction stays in-flight while we probe the guards.
    let releasePost: (r: Response) => void = () => {};
    const postHeld = new Promise<Response>((resolve) => { releasePost = resolve; });
    global.fetch = fetchMock({
      get: () => okJson({ ok: true, detail: 'available' }),
      post: () => postHeld as unknown as Response,
    });
    const root = mockRoot([pdfOnlyKit()]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Run extraction')).toBeTruthy());

    fireEvent.click(screen.getByText('Run extraction'));
    // Button shows the in-flight label and Change-folder is disabled.
    await waitFor(() => expect(screen.getByText('Extracting...')).toBeTruthy());
    expect((screen.getByText('Change folder') as HTMLButtonElement).disabled).toBe(true);

    // A drop mid-extraction is refused (its finally must NOT clear the guard).
    const pdf = { name: 'b.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(4) } as unknown as File;
    fireEvent.drop(screen.getByTestId('form-catalogue'), { dataTransfer: { files: [pdf] } });
    await waitFor(() => expect(screen.getByText(/Extraction is running/i)).toBeTruthy());
    // The drop did NOT onboard a new kit (the guard held).
    expect(root.created['b']).toBeUndefined();

    // Let extraction finish; controls re-enable.
    releasePost({ ok: true, status: 200, json: async () => ({ ok: true, detail: 'done', schemaFile: 'schema.json' }) } as unknown as Response);
    await waitFor(() => expect((screen.getByText('Change folder') as HTMLButtonElement).disabled).toBe(false));
  });

  // --- Mark complete routes through the PUBLISH GATE (bd polyglot-pdf-rh5v) --- //
  //
  // Completion is the publish gate: server-side it runs six checks and then the
  // translation drift sweep, refusing to complete a kit whose translations are
  // missing. The local path used to write metadata.json directly and skip all of
  // it, which is how a kit reached status:complete carrying a field with ZERO
  // translations. These pin that it now calls the server whenever it can.

  describe('mark complete: publish gate', () => {
    function completeFetchMock(post: (body: unknown) => Response): typeof fetch {
      const impl = async (input: unknown, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? 'GET').toUpperCase();
        // Capability probes: no extractor, no deploy endpoint in these tests.
        if (method === 'GET') {
          return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
        }
        if (url.includes('/status')) {
          return post(init?.body ? JSON.parse(init.body as string) : {});
        }
        return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
      };
      return impl as unknown as typeof fetch;
    }

    it('opens the version dialog instead of dumping the raw refusal token', async () => {
      // run-schema-editor.sh starts the BACKEND too, so local mode hits the
      // same publish gate as hosted. Without this branch the author saw
      // "AUTHOR_VERSION_REQUIRED: ..." verbatim in the error area with no
      // input, and an edition-less kit was un-publishable here at all (Opus
      // fresh-eyes round 3). Drives the REAL setRemoteStatus via fetch.
      const root = mockRoot([
        mockKit('acme', { 'schema.json': SCHEMA,
                          'metadata.json': JSON.stringify({ label: 'Acme Intake', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = completeFetchMock(() => ({
        ok: false, status: 422,
        json: async () => ({ detail: 'AUTHOR_VERSION_REQUIRED: this form has no '
          + 'government edition date, so it needs an author version.' }),
      } as unknown as Response));

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await waitFor(() => expect(screen.getByText('Acme Intake')).toBeTruthy());
      fireEvent.click(screen.getByText('Mark complete'));

      await waitFor(() =>
        expect(screen.getByText(/Name this version of/)).toBeInTheDocument());
      expect(screen.queryByText(/AUTHOR_VERSION_REQUIRED/)).not.toBeInTheDocument();
    });

    // A 403 is NOT a refused publish: mark-complete on a real backend can be
    // refused for lack of the ROLE, and that needs the host's auth routing
    // (sign-in vs the refused screen), not this card's notice line. Local mode
    // is not exempt -- run-schema-editor.sh starts the real backend. Found in
    // review round 3: this file handled auth nowhere at all.
    it('routes a 403 from mark-complete to onAuthError, not the notice line', async () => {
      const root = mockRoot([
        mockKit('acme', { 'schema.json': SCHEMA,
                          'metadata.json': JSON.stringify({ label: 'Acme Intake', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = completeFetchMock(() => ({
        ok: false, status: 403,
        json: async () => ({ detail: 'This account does not have schema editor access' }),
      } as unknown as Response));
      const onAuthError = vi.fn();

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk
        onAuthError={onAuthError} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await waitFor(() => expect(screen.getByText('Acme Intake')).toBeTruthy());
      fireEvent.click(screen.getByText('Mark complete'));

      await waitFor(() => expect(onAuthError).toHaveBeenCalled());
      // The ERROR travels, so the host can tell 403 from 401.
      expect(onAuthError.mock.calls[0][0]).toBeInstanceOf(ForbiddenError);
    });

    it('retries through the server with the normalized version attached', async () => {
      const root = mockRoot([
        mockKit('acme', { 'schema.json': SCHEMA,
                          'metadata.json': JSON.stringify({ label: 'Acme Intake', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      const posted: unknown[] = [];
      let call = 0;
      global.fetch = completeFetchMock((body) => {
        posted.push(body);
        call += 1;
        return call === 1
          ? ({ ok: false, status: 422,
               json: async () => ({ detail: 'AUTHOR_VERSION_REQUIRED: needs a version.' }),
             } as unknown as Response)
          : ({ ok: true, status: 200,
               json: async () => ({ ok: true, status: 'complete', retranslated: 0,
                                    translationModel: null, supersededKitId: null }),
             } as unknown as Response);
      });

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await waitFor(() => expect(screen.getByText('Acme Intake')).toBeTruthy());
      fireEvent.click(screen.getByText('Mark complete'));
      await waitFor(() =>
        expect(screen.getByText(/Name this version of/)).toBeInTheDocument());

      fireEvent.change(screen.getByLabelText('Version'), { target: { value: 'v2026-08-07' } });
      fireEvent.click(screen.getByText('Save version & publish'));

      await waitFor(() => expect(posted.length).toBe(2));
      // Leading v stripped, and sent under the wire key the route reads.
      expect(posted[1]).toEqual({ status: 'complete', author_version: '2026-08-07' });
    });

    it('a NON-version refusal still shows as an error, not the dialog', async () => {
      const root = mockRoot([
        mockKit('acme', { 'schema.json': SCHEMA,
                          'metadata.json': JSON.stringify({ label: 'Acme Intake', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = completeFetchMock(() => ({
        ok: false, status: 409,
        json: async () => ({ detail: 'Schema has 2 lint error(s), so it cannot be marked complete' }),
      } as unknown as Response));

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await waitFor(() => expect(screen.getByText('Acme Intake')).toBeTruthy());
      fireEvent.click(screen.getByText('Mark complete'));

      await waitFor(() => expect(screen.getByText(/lint error/)).toBeInTheDocument());
      expect(screen.queryByText(/Name this version of/)).not.toBeInTheDocument();
    });

    it('calls the backend instead of writing metadata.json when server actions are OK', async () => {
      const root = mockRoot([
        mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      const posted: unknown[] = [];
      global.fetch = completeFetchMock((body) => {
        posted.push(body);
        return { ok: true, status: 200, json: async () => ({
          status: 'complete', retranslated: 3, translationModel: 'claude-cli',
        }) } as unknown as Response;
      });

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('I-90');

      fireEvent.click(screen.getByText('Mark complete'));
      // The server was asked -- this is the whole point of the bead.
      await waitFor(() => expect(posted).toEqual([{ status: 'complete' }]));
      // And the human is told the sweep actually did something.
      await screen.findByText(/Re-translated 3 entries/);
    });

    it('does NOT promote the card when the server refuses, and shows why', async () => {
      const root = mockRoot([
        mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = completeFetchMock(() => ({
        ok: false, status: 409,
        json: async () => ({ detail: '16 of 17 translations complete' }),
      } as unknown as Response));

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('I-90');

      fireEvent.click(screen.getByText('Mark complete'));
      // The refusal is the gate WORKING; surface the server's own reason.
      await screen.findByText(/16 of 17 translations complete/);
      // The badge must stay draft -- the server did not promote it, so neither
      // may the card. Showing 'complete' here is the original bug.
      expect(screen.getByText('draft')).toBeTruthy();
      const meta = JSON.parse(await (await root.children.get('i-90')!.children.get('metadata.json')!.getFile()).text());
      expect(meta.status).toBe('draft');
    });

    it('mirrors the refusal up through onStatusRefusal for the strip line (s18 C1)', async () => {
      // The producer side of the strip's refusal/error line (decision 1): a
      // refused completion of the OPEN kit reaches the host (cleared to null
      // first on entry). Only the open kit mirrors -- see the NON-open test.
      const root = mockRoot([
        mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = completeFetchMock(() => ({
        ok: false, status: 409,
        json: async () => ({ detail: '16 of 17 translations complete' }),
      } as unknown as Response));
      const onStatusRefusal = vi.fn();

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId="i-90"
        serverActionsOk onStatusRefusal={onStatusRefusal} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('I-90');

      fireEvent.click(screen.getByText('Mark complete'));
      await waitFor(() => expect(onStatusRefusal).toHaveBeenCalledWith(
        expect.stringContaining('16 of 17 translations complete')));
      expect(onStatusRefusal.mock.calls[0]).toEqual([null]);
    });

    it('a refusal about a NON-open kit never reaches the strip (Opus outer r2)', async () => {
      // Local mode offers Mark complete on EVERY card, so a refusal about
      // kit B must stay on B's card -- mirrored onto the strip below open
      // kit A, its "Go to:" links would select unrelated fields of A.
      // The open kit (i-90) is COMPLETE, so the only "Mark complete" button
      // on screen belongs to w-7 -- the non-open kit under test.
      const root = mockRoot([
        mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
        mockKit('w-7', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'W-7', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = completeFetchMock(() => ({
        ok: false, status: 409,
        json: async () => ({ detail: 'refused: fields (id=b_field)' }),
      } as unknown as Response));
      const onStatusRefusal = vi.fn();

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId="i-90"
        serverActionsOk onStatusRefusal={onStatusRefusal} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('W-7');

      fireEvent.click(screen.getByText('Mark complete'));
      // The card shows the refusal...
      await screen.findByText(/refused: fields/);
      // ...but the strip mirror was never touched (no clear, no detail).
      expect(onStatusRefusal).not.toHaveBeenCalled();
    });

    it('falls back to a local write with NO backend, and says it was unchecked', async () => {
      const root = mockRoot([
        mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      let posted = false;
      global.fetch = completeFetchMock(() => { posted = true; return { ok: true, status: 200, json: async () => ({}) } as unknown as Response; });

      // serverActionsOk omitted -> false: no reachable/agreeing backend.
      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('I-90');

      fireEvent.click(screen.getByText('Mark complete'));
      await waitFor(() => expect(screen.getByText('complete')).toBeTruthy());
      expect(posted).toBe(false);
      // It must never read as verified: name what was skipped.
      await screen.findByText(/WITHOUT the publish checks/);
    });

    it('reverting to draft stays local even when the backend is reachable', async () => {
      const root = mockRoot([
        mockKit('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'I-90', status: 'complete' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      let posted = false;
      global.fetch = completeFetchMock(() => { posted = true; return { ok: true, status: 200, json: async () => ({}) } as unknown as Response; });

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('I-90');

      fireEvent.click(screen.getByText('Revert to draft'));
      await waitFor(() => expect(screen.getByText('draft')).toBeTruthy());
      // Demotion must work even when the backend is down, so it is deliberately
      // NOT routed through the server.
      expect(posted).toBe(false);
    });
  });

  // --- Deploy this form (bd polyglot-pdf-ipzh) -------------------------------- //

  describe('deploy this form', () => {
    function deployFetchMock(opts: {
      available?: boolean; post?: (body: unknown) => Response;
    }): typeof fetch {
      const impl = async (input: unknown, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? 'GET').toUpperCase();
        if (url.includes('/api/deploy-kit')) {
          if (method === 'GET') {
            return opts.available
              ? ({ ok: true, status: 200, json: async () => ({ ok: true, detail: 'available', bucket: 'test-bucket' }) } as unknown as Response)
              : ({ ok: false, status: 404, json: async () => ({}) } as unknown as Response);
          }
          return opts.post?.(init?.body ? JSON.parse(init.body as string) : {})
            ?? ({ ok: true, status: 200, json: async () => ({ ok: true, detail: 'Deployed.' }) } as unknown as Response);
        }
        return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
      };
      return impl as unknown as typeof fetch;
    }

    it('is offered on a COMPLETE kit and uploads only after the confirm', async () => {
      const root = mockRoot([
        mockKit('w7', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'W-7', status: 'complete' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      const posted: unknown[] = [];
      global.fetch = deployFetchMock({
        available: true,
        post: (body) => { posted.push(body); return { ok: true, status: 200, json: async () => ({ ok: true, detail: 'Deployed W-7 to test-bucket.' }) } as unknown as Response; },
      });
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      const btn = await screen.findByText('Deploy this form');

      // DECLINED -> nothing is uploaded. The confirm is the guard that keeps a
      // publish deliberate, so this is the load-bearing half.
      fireEvent.click(btn);
      await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
      expect(posted).toEqual([]);
      // The dialog must NAME the destination.
      expect(String(confirmSpy.mock.calls[0][0])).toContain('test-bucket');

      // ACCEPTED -> it uploads that kit.
      confirmSpy.mockReturnValue(true);
      fireEvent.click(screen.getByText('Deploy this form'));
      await waitFor(() => expect(posted).toEqual([{ kitId: 'w7' }]));
      await screen.findByText(/Deployed W-7 to test-bucket/);
      confirmSpy.mockRestore();
    });

    it('is NOT offered on a draft kit', async () => {
      const root = mockRoot([
        mockKit('w7', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'W-7', status: 'draft' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = deployFetchMock({ available: true });

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('W-7');
      expect(screen.queryByText('Deploy this form')).toBeNull();
    });

    it('is NOT offered when the host endpoint is absent (static/hosted build)', async () => {
      const root = mockRoot([
        mockKit('w7', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'W-7', status: 'complete' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = deployFetchMock({ available: false });

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      await screen.findByText('W-7');
      // No endpoint -> no button, so a hosted build cannot publish.
      expect(screen.queryByText('Deploy this form')).toBeNull();
    });

    it('blocks a folder switch while a deploy is in flight', async () => {
      // A deploy is the longest-running and most consequential card action; if
      // the folder can change mid-upload, the result notice lands attributed to
      // a different catalogue. Extraction already guards this (Codex r3); the
      // deploy path must too.
      const root = mockRoot([
        mockKit('w7', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'W-7', status: 'complete' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      let releaseDeploy: (r: Response) => void = () => {};
      const held = new Promise<Response>((resolve) => { releaseDeploy = resolve; });
      global.fetch = ((input: unknown, init?: RequestInit) => {
        const method = (init?.method ?? 'GET').toUpperCase();
        if (String(input).includes('/api/deploy-kit')) {
          if (method === 'GET') {
            return Promise.resolve({ ok: true, status: 200, json: async () => ({ ok: true, detail: 'available', bucket: 'test-bucket' }) } as unknown as Response);
          }
          return held;
        }
        return Promise.resolve({ ok: false, status: 404, json: async () => ({}) } as unknown as Response);
      }) as unknown as typeof fetch;
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      fireEvent.click(await screen.findByText('Deploy this form'));

      // While the upload is open, the folder controls must be disabled.
      await waitFor(() => expect((screen.getByText('Change folder') as HTMLButtonElement).disabled).toBe(true));

      releaseDeploy({ ok: true, status: 200, json: async () => ({ ok: true, detail: 'Deployed.' }) } as unknown as Response);
      await waitFor(() => expect((screen.getByText('Change folder') as HTMLButtonElement).disabled).toBe(false));
      confirmSpy.mockRestore();
    });

    it('surfaces the real failure instead of a silent no-op', async () => {
      const root = mockRoot([
        mockKit('w7', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'W-7', status: 'complete' }) }),
      ]);
      (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
      global.fetch = deployFetchMock({
        available: true,
        post: () => ({ ok: false, status: 500, json: async () => ({
          ok: false, detail: 'deploy failed (exit 1) -- see the output below.',
          output: 'ERROR: (gcloud) You do not currently have an active account selected.',
        }) } as unknown as Response),
      });
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

      render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
      fireEvent.click(screen.getByText('Open form-kits folder'));
      await expandCards();
      fireEvent.click(await screen.findByText('Deploy this form'));
      await screen.findByText(/do not currently have an active account/);
      confirmSpy.mockRestore();
    });
  });

  // --- the retired (unpublished) status, LOCAL mode (bd polyglot-pdf-6dz0) ---
  // The hosted catalogue got three tests for this; this file got none, which is
  // why the local half of the same feature shipped three defects across review
  // rounds. The guard below is the ONLY thing stopping an offline editor from
  // republishing a retired revision's audit-referenced bytes, since local
  // setKitStatus is an unvalidated read-merge-write with no server gate.

  it('refuses an OFFLINE status change on a retired kit (reaches the guard)', async () => {
    // Drives handleSetStatus itself, not just the render branch. The first
    // version of this test only asserted which element rendered, so the guard
    // it claimed to pin was deletable with the suite green (Opus fresh-eyes) --
    // and that guard is the only thing stopping an offline editor from
    // republishing a retired revision's audit-referenced bytes.
    const root = mockRoot([
      mockKit('old-form', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({ label: 'Old Form', status: 'unpublished' }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    // serverActionsOk defaults false -> the backend is NOT reachable, so no
    // publish-gate path exists and every change must be refused.
    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Old Form')).toBeTruthy());

    // No actionable control at all, and the card explains why.
    expect(screen.queryByText('Mark complete')).not.toBeInTheDocument();
    expect(screen.queryByText('Publish again')).not.toBeInTheDocument();
    expect(screen.getByText(/Retired -- start the backend/)).toBeTruthy();
    // The metadata on disk is untouched -- nothing wrote through.
    const meta = await (await root.children.get('old-form')!
      .getFileHandle('metadata.json')).getFile();
    expect(JSON.parse(await meta.text()).status).toBe('unpublished');
  });

  it('offers a server-gated republish on a retired kit when the backend is up', async () => {
    // The one transition a retired kit HAS: back to complete, through the full
    // publish gate. Refusing this too made the status a one-way trip from the
    // local editor even with the backend reachable.
    const root = mockRoot([
      mockKit('old-form', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({ label: 'Old Form', status: 'unpublished' }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} serverActionsOk />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('Old Form')).toBeTruthy());

    expect(screen.getByText('Publish again')).toBeTruthy();
    expect(screen.queryByText('Mark complete')).not.toBeInTheDocument();
  });

  it('shows a retired kit with its own badge, not an unstyled one', async () => {
    // Widening KitStatus without widening STATUS_STYLE rendered
    // className="undefined" once retired kits became visible locally.
    const root = mockRoot([
      mockKit('old-form', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({ label: 'Old Form', status: 'unpublished' }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    const badge = await screen.findByText('unpublished');
    expect(badge.className).not.toContain('undefined');
    expect(badge.className).toMatch(/bg-/);
  });

  it('counts a retired kit separately in the local summary', async () => {
    const root = mockRoot([
      mockKit('live-form', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({ label: 'Live Form', status: 'complete' }),
      }),
      mockKit('old-form', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({ label: 'Old Form', status: 'unpublished' }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

    const summary = await screen.findByTestId('catalogue-summary');
    expect(summary.textContent).toMatch(/2 forms/);
    expect(summary.textContent).toMatch(/1 complete/);
    // Retired is not pending work: without its own bucket it inflates the
    // backlog AND the sub-counts stop summing to the total.
    expect(summary.textContent).toMatch(/1 retired/);
    expect(summary.textContent).not.toMatch(/1 in progress/);
  });
});


describe('local mode respects the submitted lock (bd polyglot-pdf-hqztg)', () => {
  it('does NOT offer Mark complete on a submitted kit', async () => {
    // Local mode bypasses the server when the backend is unreachable, so this
    // button would have promoted a kit awaiting author review with no publish
    // gate and no role check.
    const root = mockRoot([
      mockKit('w7', {
        'schema.json': SCHEMA,
        'metadata.json': JSON.stringify({ label: 'W-7', status: 'submitted' }),
      }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();
    await waitFor(() => expect(screen.getByText('W-7')).toBeTruthy());

    expect(screen.queryByText('Mark complete')).not.toBeInTheDocument();
    expect(screen.getByText(/an author publishes it/i)).toBeTruthy();
  });
});
