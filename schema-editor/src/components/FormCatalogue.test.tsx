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
        read_only: false, required: false, spoken_name: 'first',
        help: { instructions: 'Enter it.' },
      }],
    });
    const root = mockRoot([
      mockKit('done', { 'schema.json': fullSchema, 'metadata.json': JSON.stringify({ label: 'Done', status: 'complete' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

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

    await screen.findByText('I-90');
    await waitFor(() => expect(screen.getByText('75%')).toBeTruthy());
    expect(screen.queryByText('0%')).toBeNull();
  });

  it('shows an unreadable-schema notice (distinct from no schema)', async () => {
    const root = mockRoot([
      mockKit('broken', { 'schema.json': 'not json{', 'metadata.json': JSON.stringify({ label: 'Broken', status: 'draft' }) }),
    ]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);

    render(<FormCatalogue onOpenKit={vi.fn()} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));

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
