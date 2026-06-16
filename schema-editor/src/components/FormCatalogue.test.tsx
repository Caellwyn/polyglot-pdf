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
        liveProgress={{ kitId: 'i-90', percent: 75, complete: 3, total: 4 }}
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
});
