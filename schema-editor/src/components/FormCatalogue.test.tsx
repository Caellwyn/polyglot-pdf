/**
 * Component tests for the form catalogue (bd polyglot-pdf-b0pe): open a folder,
 * list kits, drop a PDF to onboard. The File System Access directory API is
 * mocked via window.showDirectoryPicker.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FormCatalogue } from './FormCatalogue';

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
    getFileHandle: async () => { throw new DOMException('x', 'NotFoundError'); },
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

  it('shows a per-form review percentage derived from field completion', async () => {
    // A schema with one fully-complete field -> 100% review.
    const fullSchema = JSON.stringify({
      form_metadata: { form_number: 'T-1' }, sections: [],
      fields: [{
        id: 'f1', name: 'f1', type: 'text', pdf_field_name: 'f1',
        read_only: false, spoken_name: 'first',
        help: { instructions: 'Enter it.' },
      }],
    });
    const root = mockRoot([
      mockKit('done', { 'schema.json': fullSchema, 'metadata.json': JSON.stringify({ label: 'Done', status: 'complete' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('Done');
    await waitFor(() => expect(screen.getByText('100%')).toBeTruthy());
  });

  it('shows a 0% bar for an extracted-but-empty schema, and no bar for a no-schema kit', async () => {
    const root = mockRoot([
      // empty-fields schema -> 0% (bar renders)
      mockKit('empty', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'Empty', status: 'draft' }) }),
      // no schema -> no bar
      mockKit('raw', { 'metadata.json': JSON.stringify({ label: 'Raw', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await expandCards();

    await screen.findByText('Empty');
    // The empty-schema kit shows a 0% review bar...
    await waitFor(() => expect(screen.getByText('0%')).toBeTruthy());
    // ...and there is exactly one "Review" bar (the no-schema 'raw' kit has none).
    expect(screen.getAllByText('Review')).toHaveLength(1);
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

  it('lets Refresh replace a cached kit percentage with the fresh disk scan', async () => {
    // Codex round 6: after a saved edit caches 60%, if the schema changes on disk
    // and the user clicks Refresh, the scan's value (0% for the empty fixture)
    // must win -- the cache cannot outrank a deliberate Refresh.
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

    // Save an edit -> 60% cached for A.
    rerender(
      <FormCatalogue
        onOpenKit={vi.fn()}
        selectedKitId="a"
        liveProgress={{ kitId: 'a', saved: true, percent: 60, complete: 3, total: 5 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('60%')).toBeTruthy());

    // Deselect (cache holds 60%) then click Refresh -> disk scan (0%) wins.
    rerender(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />);
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => expect(screen.getByText('0%')).toBeTruthy());
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
    // Codex round 5: an unsaved edit shows live on the open card, but if the user
    // discards it (switches kits without saving), the card must revert to the
    // disk-scan value, not keep phantom progress.
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

    // User opens A and edits it WITHOUT saving (saved:false) -> 60% shows live.
    rerender(
      <FormCatalogue
        onOpenKit={vi.fn()}
        selectedKitId="a"
        liveProgress={{ kitId: 'a', saved: false, percent: 60, complete: 3, total: 5 }}
      />,
    );
    await waitFor(() => expect(screen.getByText('60%')).toBeTruthy());

    // Edit discarded, kit deselected -> revert to disk scan (0%), NOT 60%.
    rerender(
      <FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} liveProgress={null} />,
    );
    expect(screen.getByText('0%')).toBeTruthy();
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
  }): typeof fetch {
    const impl = async (_input: unknown, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'GET') {
        return handlers.get?.() ?? ({ ok: false, status: 404, json: async () => ({}) } as unknown as Response);
      }
      const body = init?.body ? JSON.parse(init.body as string) : {};
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
});
