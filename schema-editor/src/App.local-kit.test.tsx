/**
 * App local-mode kit-switch tests (bd polyglot-pdf-0yjb).
 *
 * Exit criteria under test: handleOpenKit (the File System Access sibling of
 * handleOpenRemoteKit, bd 92qe.2) must not revoke the currently-open kit's PDF
 * blob URL until the NEW kit's file handles have actually resolved. The remote
 * path was already fixed for this (App.hosted.test.tsx, "a failed kit-B open
 * keeps kit A pointing at a LIVE blob URL"); this is the same regression for
 * the local File System Access catalogue.
 *
 * The heavy children (PDFViewer/FieldList/FieldEditor/ValidationPanel) are
 * mocked, as is FormCatalogue itself -- its directory-picker internals are
 * covered by FormCatalogue.test.tsx, so here it is reduced to buttons that
 * call onOpenKit with a fixture CatalogueEntry (a fake dirHandle whose
 * getFileHandle can be made to throw for the failure case).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema } from './types/schema';
import type { CatalogueEntry } from './utils/formKitDirectory';

vi.mock('./components/PDFViewer', () => ({
  PDFViewer: ({ pdfPath }: { pdfPath: string }) => (
    <div data-testid="pdf">{pdfPath}</div>
  ),
}));
vi.mock('./components/FieldList', () => ({ FieldList: () => <div data-testid="list" /> }));
vi.mock('./components/FieldEditor', () => ({ FieldEditor: () => <div data-testid="editor" /> }));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div data-testid="vp" /> }));

// FormCatalogue is reduced to two buttons that call onOpenKit directly with
// fixture entries -- the directory-picker plumbing is covered elsewhere.
vi.mock('./components/FormCatalogue', () => ({
  FormCatalogue: ({ onOpenKit }: { onOpenKit: (entry: CatalogueEntry) => void }) => (
    <div>
      <button onClick={() => onOpenKit(kitA())}>open-A</button>
      <button onClick={() => onOpenKit(kitB())}>open-B</button>
    </div>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'Kit A', version: '1' },
  sections: [],
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

const SCHEMA_B: FormSchema = {
  form_metadata: { title: 'Kit B', version: '1' },
  sections: [],
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

/** A fake PDF File whose only observable trait is a stable blob URL. */
function fakePdfFile(): File {
  return { name: 'form.pdf' } as unknown as File;
}

// Each test can override how kit B's dirHandle behaves; kit A always succeeds.
let kitBGetFileHandle: ReturnType<typeof vi.fn>;

function kitA(): CatalogueEntry {
  return {
    id: 'kit-a', label: 'Kit A', status: 'draft', hasSchema: true, hasPdf: true,
    schemaFile: 'schema.json', pdfFile: 'form.pdf',
    dirHandle: {
      getFileHandle: vi.fn(async (name: string) => ({
        getFile: async () => (name === 'schema.json'
          ? { text: async () => JSON.stringify(SCHEMA) }
          : fakePdfFile()),
      })),
    } as unknown as CatalogueEntry['dirHandle'],
  };
}

function kitB(): CatalogueEntry {
  return {
    id: 'kit-b', label: 'Kit B', status: 'draft', hasSchema: true, hasPdf: true,
    schemaFile: 'schema.json', pdfFile: 'form.pdf',
    dirHandle: {
      getFileHandle: kitBGetFileHandle,
    } as unknown as CatalogueEntry['dirHandle'],
  };
}

vi.mock('./utils/formKitDirectory', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/formKitDirectory')>();
  return {
    ...actual,
    loadKitSchema: vi.fn(async (entry: CatalogueEntry) =>
      (entry.id === 'kit-a' ? SCHEMA : SCHEMA_B)),
  };
});

import { App } from './App';

afterEach(() => {
  vi.clearAllMocks();
});

describe('App local-mode kit switch (bd polyglot-pdf-0yjb)', () => {
  it('a failed kit-B open keeps kit A pointing at a LIVE blob URL', async () => {
    const revoke = vi.fn();
    const origRevoke = URL.revokeObjectURL;
    const origCreate = URL.createObjectURL;
    URL.revokeObjectURL = revoke as typeof URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => 'blob:kit-a') as typeof URL.createObjectURL;
    try {
      // Kit B's schema handle resolves fine, but its PDF file handle throws
      // (stale handle / revoked permission / deleted file).
      kitBGetFileHandle = vi.fn(async (name: string) => {
        if (name === 'form.pdf') throw new Error('NotFoundError: form.pdf');
        return { getFile: async () => ({ text: async () => JSON.stringify(SCHEMA_B) }) };
      });

      render(<App />);
      fireEvent.click(screen.getByText('open-A'));
      await waitFor(() => expect(screen.getByTestId('pdf')).toHaveTextContent('blob:kit-a'));

      // Open kit B: its PDF fetch throws. (Unlike the hosted/AuthError path,
      // handleOpenKit's catch always routes to the full-screen error view,
      // which unconditionally hides the editor -- that's pre-existing App
      // architecture, not part of this bug. What the fix guarantees is that
      // kit A's blob URL itself was never revoked, so if the human dismisses
      // the error and reopens kit A, its PDF still loads instead of showing a
      // dead/blank viewer.)
      fireEvent.click(screen.getByText('open-B'));
      await waitFor(() => expect(screen.getByText(/NotFoundError: form\.pdf/)).toBeInTheDocument());

      // Kit A's URL was never revoked.
      expect(revoke).not.toHaveBeenCalledWith('blob:kit-a');
    } finally {
      URL.revokeObjectURL = origRevoke;
      URL.createObjectURL = origCreate;
    }
  });

  it('a successful kit-B open DOES revoke kit A once B is fully loaded', async () => {
    const revoke = vi.fn();
    const origRevoke = URL.revokeObjectURL;
    const origCreate = URL.createObjectURL;
    URL.revokeObjectURL = revoke as typeof URL.revokeObjectURL;
    let created = 0;
    URL.createObjectURL = vi.fn(() => `blob:kit-${created++ === 0 ? 'a' : 'b'}`) as typeof URL.createObjectURL;
    try {
      kitBGetFileHandle = vi.fn(async (name: string) => ({
        getFile: async () => (name === 'schema.json'
          ? { text: async () => JSON.stringify(SCHEMA_B) }
          : fakePdfFile()),
      }));

      render(<App />);
      fireEvent.click(screen.getByText('open-A'));
      await waitFor(() => expect(screen.getByTestId('pdf')).toHaveTextContent('blob:kit-a'));

      fireEvent.click(screen.getByText('open-B'));
      await waitFor(() => expect(screen.getByTestId('pdf')).toHaveTextContent('blob:kit-b'));
      expect(revoke).toHaveBeenCalledWith('blob:kit-a');
    } finally {
      URL.revokeObjectURL = origRevoke;
      URL.createObjectURL = origCreate;
    }
  });
});
