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

  it('onboards a dropped PDF into a new kit and opens it', async () => {
    const root = mockRoot([]);
    (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn(async () => root);
    const onOpenKit = vi.fn();

    render(<FormCatalogue onOpenKit={onOpenKit} selectedKitId={null} />);
    fireEvent.click(screen.getByText('Open form-kits folder'));
    await waitFor(() => expect(screen.getByText(/0 forms/)).toBeTruthy());

    const pdf = { name: 'Form I-90.pdf', type: 'application/pdf',
      arrayBuffer: async () => new ArrayBuffer(4) } as unknown as File;
    const dropZone = screen.getByTestId('form-catalogue');
    fireEvent.drop(dropZone, { dataTransfer: { files: [pdf] } });

    await waitFor(() => expect(onOpenKit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'form-i-90', status: 'draft' })));
    // the new kit folder was created in the root
    expect(root.created['form-i-90']).toBeTruthy();
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
});
