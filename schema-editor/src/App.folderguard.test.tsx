/**
 * Same-folder guard, at the App level (bd polyglot-pdf-s2bf).
 *
 * In LOCAL mode the editor reads and writes the folder the human PICKED, while
 * the backend resolves the same kit id against its OWN FORM_KITS_LOCAL_ROOT.
 * When those differ, the server-side actions (Repair all, Regenerate
 * divisions, Rewrite guidance) rewrite a DIFFERENT copy than the one on
 * screen -- destructive, and invisible to the human.
 *
 * So those actions stay OFF until the two are proven to agree, and the human
 * gets a dialog explaining why. Editing and saving are untouched: they go to
 * the picked folder either way.
 *
 * The panel mock exposes data-has-repair, which is the observable proof of
 * whether App handed down the server-side callback.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import type { FormSchema } from './types/schema';
import type { CatalogueEntry } from './utils/formKitDirectory';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/FieldList', () => ({ FieldList: () => <div data-testid="list" /> }));
vi.mock('./components/FieldEditor', () => ({ FieldEditor: () => <div data-testid="editor" /> }));
vi.mock('./components/ValidationPanel', () => ({
  ValidationPanel: ({ onRepairAll }: { onRepairAll?: () => Promise<void> }) => (
    <div data-testid="vp" data-has-repair={onRepairAll ? 'yes' : 'no'} />
  ),
}));

// The catalogue is reduced to: report a folder, and open a kit.
vi.mock('./components/FormCatalogue', () => ({
  FormCatalogue: ({ onOpenKit, onRootChange }: {
    onOpenKit: (e: CatalogueEntry) => void;
    onRootChange?: (d: unknown) => void;
  }) => (
    <div>
      <button onClick={() => onRootChange?.({ name: 'form-kits' })}>pick-folder</button>
      <button onClick={() => onRootChange?.({ name: 'other-copy' })}>pick-other</button>
      <button onClick={() => onOpenKit(kit())}>open-kit</button>
    </div>
  ),
}));

const verifySameFolder = vi.fn();
vi.mock('./utils/formKitDirectory', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/formKitDirectory')>();
  return {
    ...actual,
    verifySameFolder: (...a: unknown[]) => verifySameFolder(...a),
    loadKitSchema: async () => JSON.parse(JSON.stringify(SCHEMA)) as FormSchema,
  };
});

vi.mock('./utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/remoteKitStore')>();
  return {
    ...actual,
    isHostedMode: () => false,   // LOCAL mode: the handshake applies
    hasBackend: () => true,      // ...and a backend IS running
    verifyStoreFolder: vi.fn(),
  };
});

const SCHEMA: FormSchema = {
  form_metadata: { title: 'W-7', version: '1' },
  sections: [],
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

function kit(): CatalogueEntry {
  return {
    id: 'w7', label: 'W-7', status: 'draft', hasSchema: true, hasPdf: false,
    schemaFile: 'schema.json', pdfFile: 'form.pdf',
    dirHandle: {
      getFileHandle: async () => ({}),
    } as unknown as CatalogueEntry['dirHandle'],
  };
}

const { App } = await import('./App');

beforeEach(() => { verifySameFolder.mockReset(); });
afterEach(cleanup);

/** Open a kit after reporting a folder, and read the repair-callback probe. */
async function openWithFolder() {
  render(<App />);
  fireEvent.click(screen.getByText('pick-folder'));
  fireEvent.click(screen.getByText('open-kit'));
  await waitFor(() => expect(screen.getByTestId('vp')).toBeInTheDocument());
}

describe('App same-folder guard (bd polyglot-pdf-s2bf)', () => {
  it('ENABLES the server-side actions once the folders are proven to agree', async () => {
    verifySameFolder.mockResolvedValue({ ok: true });
    await openWithFolder();
    await waitFor(() =>
      expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('yes'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('DISABLES them and explains when the folder is not the backend\'s', async () => {
    verifySameFolder.mockResolvedValue({
      ok: false, reason: 'mismatch', backendRoot: '/repo/form-kits',
    });
    await openWithFolder();
    await waitFor(() =>
      expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no'));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent(/not the one the server uses/i);
    // The dialog names the folder to switch to -- otherwise the human cannot act.
    expect(dialog).toHaveTextContent('/repo/form-kits');
  });

  it('offers the make-a-copy fix when the folder is READ-ONLY', async () => {
    verifySameFolder.mockResolvedValue({ ok: false, reason: 'unwritable' });
    await openWithFolder();
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent(/cannot be written to/i);
    expect(dialog).toHaveTextContent(/[Mm]ake a copy/);
    expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no');
  });

  it('keeps the actions OFF while the check is still unproven', async () => {
    // A backend that cannot answer leaves agreement UNPROVEN. Fail safe: a
    // wrong-folder write is destructive, a disabled button is not.
    verifySameFolder.mockRejectedValue(new Error('backend down'));
    await openWithFolder();
    await waitFor(() =>
      expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no'));
    // ...and no dialog: the lint path already reports a dead backend, so this
    // would be a second dialog for the same cause.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('lets the human dismiss the dialog and keep editing', async () => {
    verifySameFolder.mockResolvedValue({ ok: false, reason: 'mismatch' });
    await openWithFolder();
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByTestId('folder-guard-dismiss'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    // Dismissing is not consent: the server-side actions stay off.
    expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no');
  });

  it('does not run the handshake at all before a folder is picked', async () => {
    verifySameFolder.mockResolvedValue({ ok: true });
    render(<App />);
    expect(verifySameFolder).not.toHaveBeenCalled();
  });

  it('a SLOW check for an abandoned folder cannot re-enable the actions', async () => {
    // The fail-open race: folder A (which AGREES) is still in flight when the
    // human switches to folder B (a copy, which does NOT). A's late {ok:true}
    // must not land after B's {ok:false}, or the server actions would be
    // enabled while B is on screen -- the wrong-folder write this guard exists
    // to stop. Only the seq token can catch this: clearing on entry does not,
    // because A's stale TRUE arrives last either way.
    let resolveA: (v: unknown) => void = () => {};
    verifySameFolder
      .mockReturnValueOnce(new Promise((res) => { resolveA = res; }))  // A: slow
      .mockResolvedValueOnce({ ok: false, reason: 'mismatch' });       // B: fast

    render(<App />);
    fireEvent.click(screen.getByText('pick-folder'));  // A -- in flight
    fireEvent.click(screen.getByText('pick-other'));   // B -- settles first
    fireEvent.click(screen.getByText('open-kit'));
    await waitFor(() =>
      expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no'));

    // A finally answers, for a folder the human already left.
    await act(async () => { resolveA({ ok: true }); });
    expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no');
  });

  it('turns the actions OFF the instant a new folder is reported', async () => {
    // Agreement is unproven from the moment the folder changes, so the actions
    // must be off for the whole in-flight window rather than riding the
    // PREVIOUS folder's verdict.
    verifySameFolder.mockResolvedValueOnce({ ok: true });
    render(<App />);
    fireEvent.click(screen.getByText('pick-folder'));
    fireEvent.click(screen.getByText('open-kit'));
    await waitFor(() =>
      expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('yes'));

    verifySameFolder.mockReturnValueOnce(new Promise(() => {}));  // never settles
    fireEvent.click(screen.getByText('pick-other'));
    await waitFor(() =>
      expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no'));
  });
});
