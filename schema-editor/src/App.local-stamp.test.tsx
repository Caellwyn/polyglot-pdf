/**
 * App local-save readiness stamping (sprint-18 C4b, bd polyglot-pdf-na1zy).
 *
 * The exit criteria under test, at the App wiring level (localStamp's own
 * unit tests cover the module internals):
 *  1. An IN-PLACE kit save refreshes the stamp: backend reachable + same
 *     folder proven -> the backend restamp route is called; no backend -> the
 *     old stamp is invalidated so the card degrades to the verify hint. A
 *     failed restamp falls back to invalidation -- nothing stale survives a
 *     completed save.
 *  2. Save-As never touches the kit's metadata (a picked destination must
 *     not stamp the kit it was opened from).
 *  3. Reload-from-file (the local discard) never writes a stamp -- only a
 *     SAVE may.
 */
import { WRITE_LOCKED_STATUSES } from './utils/formKitDirectory';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema } from './types/schema';
import type { CatalogueEntry } from './utils/formKitDirectory';

vi.mock('./components/PDFViewer', () => ({
  PDFViewer: () => <div data-testid="pdf" />,
}));
vi.mock('./components/FieldList', () => ({ FieldList: () => <div data-testid="list" /> }));
vi.mock('./components/FieldEditor', () => ({ FieldEditor: () => <div data-testid="editor" /> }));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div data-testid="vp" /> }));

vi.mock('./utils/localStamp', () => ({
  stampKitReadinessRemote: vi.fn(async () => ({ percent: 50, verified: true })),
  invalidateLocalStamp: vi.fn(async () => true),
}));

// Partial-mock the two modules whose environment probes the test drives:
// hasBackend (remoteKitStore) and verifySameFolder/loadKitSchema
// (formKitDirectory). Everything else stays real.
const hasBackendMock = vi.fn(() => false);
vi.mock('./utils/remoteKitStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./utils/remoteKitStore')>()),
  hasBackend: () => hasBackendMock(),
}));
const verifySameFolderMock = vi.fn(async () => ({ ok: true as const }));
vi.mock('./utils/formKitDirectory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./utils/formKitDirectory')>()),
  verifySameFolder: () => verifySameFolderMock(),
  loadKitSchema: vi.fn(async () => SCHEMA),
}));

// FormCatalogue reduced to: open kit A, and report a picked root folder (the
// same-folder handshake trigger). Its real internals are covered elsewhere.
vi.mock('./components/FormCatalogue', () => ({
  FormCatalogue: ({ onOpenKit, onRootChange }: {
    onOpenKit: (entry: CatalogueEntry) => void;
    onRootChange?: (dir: unknown) => void;
  }) => (
    <div>
      <button onClick={() => onOpenKit(kitEntry)}>open-A</button>
      <button onClick={() => onRootChange?.({ fake: 'root' })}>pick-root</button>
    </div>
  ),
}));

import { App } from './App';
import * as localStamp from './utils/localStamp';

const SCHEMA: FormSchema = {
  form_metadata: { title: 'Kit A', version: '1' },
  sections: [],
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

function makeWritable() {
  return { write: vi.fn(async () => undefined), close: vi.fn(async () => undefined) };
}

let schemaWritable: ReturnType<typeof makeWritable>;
let kitEntry: CatalogueEntry;

beforeEach(() => {
  vi.clearAllMocks();
  hasBackendMock.mockReturnValue(false);
  schemaWritable = makeWritable();
  const schemaHandle = {
    name: 'schema.json',
    createWritable: vi.fn(async () => schemaWritable),
    getFile: vi.fn(async () => ({ text: async () => JSON.stringify(SCHEMA) })),
  };
  kitEntry = {
    id: 'kit-a', label: 'Kit A', status: 'draft', hasSchema: true, hasPdf: false,
    schemaFile: 'schema.json', pdfFile: 'form.pdf',
    dirHandle: {
      getFileHandle: vi.fn(async () => schemaHandle),
    } as unknown as CatalogueEntry['dirHandle'],
  };
  // File System Access supported (the in-place path needs it).
  (window as unknown as Record<string, unknown>).showSaveFilePicker =
    vi.fn(async () => ({ name: 'elsewhere.json',
                         createWritable: vi.fn(async () => makeWritable()) }));
  (window as unknown as Record<string, unknown>).showDirectoryPicker = vi.fn();
});

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).showSaveFilePicker;
  delete (window as unknown as Record<string, unknown>).showDirectoryPicker;
});

async function openKitA() {
  render(<App />);
  fireEvent.click(screen.getByText('open-A'));
  await waitFor(() => expect(screen.getByTestId('list')).toBeInTheDocument());
}

describe('local-save readiness stamping (bd na1zy)', () => {
  it('an in-place save with NO backend invalidates the old stamp (criterion 1)', async () => {
    await openKitA();
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() =>
      expect(localStamp.invalidateLocalStamp).toHaveBeenCalledTimes(1));
    expect(localStamp.invalidateLocalStamp)
      .toHaveBeenCalledWith(kitEntry.dirHandle);
    expect(localStamp.stampKitReadinessRemote).not.toHaveBeenCalled();
    expect(schemaWritable.write).toHaveBeenCalledTimes(1); // the save itself
  });

  it('an in-place save with backend + proven folder restamps via the backend (criterion 1)', async () => {
    hasBackendMock.mockReturnValue(true);
    await openKitA();
    // Pick a root so the same-folder handshake runs and proves agreement.
    fireEvent.click(screen.getByText('pick-root'));
    await waitFor(() => expect(verifySameFolderMock).toHaveBeenCalled());
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() =>
      expect(localStamp.stampKitReadinessRemote).toHaveBeenCalledTimes(1));
    expect(localStamp.stampKitReadinessRemote)
      .toHaveBeenCalledWith('kit-a', expect.objectContaining({
        form_metadata: expect.objectContaining({ title: 'Kit A' }),
      }));
    expect(localStamp.invalidateLocalStamp).not.toHaveBeenCalled();
  });

  it('a failed backend restamp falls back to invalidation (criterion 1)', async () => {
    hasBackendMock.mockReturnValue(true);
    vi.mocked(localStamp.stampKitReadinessRemote)
      .mockRejectedValueOnce(new Error('backend down'));
    await openKitA();
    fireEvent.click(screen.getByText('pick-root'));
    await waitFor(() => expect(verifySameFolderMock).toHaveBeenCalled());
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() =>
      expect(localStamp.invalidateLocalStamp).toHaveBeenCalledTimes(1));
    // The save itself still succeeded -- no error banner.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  // stampKitReadinessRemote is the editor's OTHER direct fetch site -- it does
  // NOT go through editorFetch -- so its auth failures were swallowed into a
  // console.warn for four review rounds while every other call site routed
  // them. A 403 here means the role was revoked mid-session, which needs the
  // same routing as anywhere else: local mode surfaces it, hosted drops to the
  // gate. Anything less is a silent failure in the path whose entire job is to
  // avoid silent staleness.
  it('an auth failure from the restamp is ROUTED, not swallowed', async () => {
    hasBackendMock.mockReturnValue(true);
    const { ForbiddenError } = await import('./utils/remoteKitStore');
    vi.mocked(localStamp.stampKitReadinessRemote)
      .mockRejectedValueOnce(new ForbiddenError('access revoked'));
    await openKitA();
    fireEvent.click(screen.getByText('pick-root'));
    await waitFor(() => expect(verifySameFolderMock).toHaveBeenCalled());
    fireEvent.keyDown(window, { key: 's', metaKey: true });

    // LOCAL mode has no gate screen, so handleAuthExpired surfaces a banner --
    // proof the error reached the router instead of a console line.
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('Save-As touches neither the stamp nor the metadata (criterion 2)', async () => {
    await openKitA();
    fireEvent.keyDown(window, { key: 's', metaKey: true, shiftKey: true });
    await waitFor(() => expect(
      (window as unknown as { showSaveFilePicker: ReturnType<typeof vi.fn> })
        .showSaveFilePicker).toHaveBeenCalledTimes(1));
    // Give any (wrongly) scheduled stamp work a tick to surface.
    await new Promise((r) => setTimeout(r, 0));
    expect(localStamp.invalidateLocalStamp).not.toHaveBeenCalled();
    expect(localStamp.stampKitReadinessRemote).not.toHaveBeenCalled();
  });

  // DERIVED from the shipped set, not retyped: this list said "the FULL set,
  // not a sample" while naming two of three, and stayed green when a fourth
  // status made it a sample again (Opus fresh-eyes round 7). Enumerating the
  // real constant is the only version of this test that cannot drift.
  // A complete kit is live,
  // an unpublished one holds the bytes earlier confirmation records were
  // confirmed against. Neither may have its metadata touched -- not even to
  // retract a stamp claim (Opus cross-surface round 3).
  it.each(WRITE_LOCKED_STATUSES)(
    'a write-locked kit (%s) gets NO stamp activity on save', async (status) => {
      hasBackendMock.mockReturnValue(true);
      kitEntry.status = status;
      await openKitA();
      fireEvent.click(screen.getByText('pick-root'));
      await waitFor(() => expect(verifySameFolderMock).toHaveBeenCalled());
      fireEvent.keyDown(window, { key: 's', metaKey: true });
      await waitFor(() => expect(schemaWritable.write).toHaveBeenCalledTimes(1));
      await new Promise((r) => setTimeout(r, 0));
      expect(localStamp.stampKitReadinessRemote).not.toHaveBeenCalled();
      expect(localStamp.invalidateLocalStamp).not.toHaveBeenCalled();
    });

  it('reload-from-file (discard) never writes a stamp (criterion 3)', async () => {
    await openKitA();
    // Save once in place (establishes the handle + the Reload button)...
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() =>
      expect(localStamp.invalidateLocalStamp).toHaveBeenCalledTimes(1));
    // ...then discard via reload: no FURTHER stamp activity of either kind.
    fireEvent.click(await screen.findByText('Reload from file'));
    await new Promise((r) => setTimeout(r, 0));
    expect(localStamp.invalidateLocalStamp).toHaveBeenCalledTimes(1);
    expect(localStamp.stampKitReadinessRemote).not.toHaveBeenCalled();
  });
});
