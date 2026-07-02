/**
 * App hosted-delivery-mode tests (bd polyglot-pdf-92qe.2).
 *
 * Exit criteria under test:
 * - hosted mode lists kits from the API (drafts included), opens one (schema +
 *   PDF via the routes), saves via PUT, marks complete via POST;
 * - the access-code flow prompts when no code is stored, re-prompts on 401, and
 *   hosted mode never touches the File System Access APIs;
 * - default (non-hosted) behavior is unchanged when the flag is unset (the
 *   existing App suites cover it; a sanity check here proves the gate is off).
 *
 * Heavy children are mocked; the remote store's fetch layer is mocked at the
 * module level so App's orchestration (gate -> catalogue -> open -> save) is
 * what runs.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema } from './types/schema';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/FieldList', () => ({ FieldList: () => <div data-testid="list" /> }));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div data-testid="vp" /> }));
// FieldEditor is mocked with an edit button so a test can dirty the schema.
vi.mock('./components/FieldEditor', () => ({
  FieldEditor: ({ onUpdateField, field }: {
    onUpdateField: (f: unknown) => void; field: { id: string } | null;
  }) => (
    <button
      data-testid="edit-field"
      onClick={() => onUpdateField({ id: 'f1', name: 'F1', type: 'text', spoken_name: 'edited' })}
    >
      edit {field?.id ?? 'metadata'}
    </button>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'Remote Form', version: '1' },
  sections: [],
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

const KIT = {
  id: 'draft-kit', label: 'Draft Form', status: 'draft' as const, hasSchema: true,
  hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf',
};

vi.mock('./utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/remoteKitStore')>();
  return {
    ...actual,
    isHostedMode: vi.fn(() => true),
    probeSession: vi.fn(),
    listRemoteKits: vi.fn(),
    loadRemoteSchema: vi.fn(),
    loadRemotePdfBlobUrl: vi.fn(),
    saveRemoteSchema: vi.fn(),
    setRemoteStatus: vi.fn(),
  };
});

import { App } from './App';
import {
  AuthError, isHostedMode, listRemoteKits, loadRemotePdfBlobUrl,
  loadRemoteSchema, probeSession, saveRemoteSchema,
} from './utils/remoteKitStore';

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(isHostedMode).mockReturnValue(true);
  vi.mocked(probeSession).mockResolvedValue({ role: 'editor' });
  vi.mocked(listRemoteKits).mockResolvedValue([KIT]);
  vi.mocked(loadRemoteSchema).mockResolvedValue(
    JSON.parse(JSON.stringify(SCHEMA)) as FormSchema,
  );
  vi.mocked(loadRemotePdfBlobUrl).mockResolvedValue('blob:fake-pdf');
  vi.mocked(saveRemoteSchema).mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

/** Enter the access code through the gate and land on the catalogue. */
async function passGate() {
  render(<App />);
  const input = await screen.findByLabelText('Access code');
  fireEvent.change(input, { target: { value: 'sekret' } });
  fireEvent.click(screen.getByText('Open the workspace'));
  await waitFor(() => expect(screen.getByTestId('remote-catalogue')).toBeInTheDocument());
}

describe('App hosted mode (bd 92qe.2)', () => {
  it('prompts for an access code, validates it, and shows the remote catalogue', async () => {
    await passGate();
    expect(probeSession).toHaveBeenCalled();
    // The kit list came from the API, and the local-folder UI never rendered.
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    expect(screen.queryByText('Open form-kits folder')).not.toBeInTheDocument();
  });

  it('a stored code is probed silently on load (no prompt for returning users)', async () => {
    window.localStorage.setItem('schema-editor.accessCode', 'remembered');
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('remote-catalogue')).toBeInTheDocument());
    expect(screen.queryByLabelText('Access code')).not.toBeInTheDocument();
  });

  it('re-prompts when the code is refused (401), with the stored code cleared', async () => {
    window.localStorage.setItem('schema-editor.accessCode', 'stale');
    vi.mocked(probeSession).mockRejectedValue(new AuthError());
    render(<App />);
    // The silent probe fails -> the gate form renders and the code is gone.
    const input = await screen.findByLabelText('Access code');
    expect(input).toBeInTheDocument();
    expect(window.localStorage.getItem('schema-editor.accessCode')).toBeNull();
  });

  it('opens a kit from the remote catalogue: schema + PDF via the routes', async () => {
    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('pdf')).toBeInTheDocument());
    expect(loadRemoteSchema).toHaveBeenCalledWith('draft-kit');
    expect(loadRemotePdfBlobUrl).toHaveBeenCalledWith('draft-kit');
  });

  it('Cmd+S saves the edited schema back through the remote store', async () => {
    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());

    // Dirty the schema, then save.
    fireEvent.click(screen.getByTestId('edit-field'));
    fireEvent.keyDown(window, { key: 's', metaKey: true });

    await waitFor(() => expect(saveRemoteSchema).toHaveBeenCalledTimes(1));
    const [kitId, saved] = vi.mocked(saveRemoteSchema).mock.calls[0];
    expect(kitId).toBe('draft-kit');
    expect((saved as FormSchema).fields[0]).toMatchObject({ spoken_name: 'edited' });
    // The header reflects the persisted state.
    await waitFor(() =>
      expect(screen.getByText(/Saved to the shared workspace/)).toBeInTheDocument());
  });

  it('hosted mode never calls the File System Access pickers', async () => {
    const savePicker = vi.fn();
    const dirPicker = vi.fn();
    (window as unknown as Record<string, unknown>).showSaveFilePicker = savePicker;
    (window as unknown as Record<string, unknown>).showDirectoryPicker = dirPicker;
    try {
      await passGate();
      fireEvent.click(screen.getByText('Draft Form'));
      await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());
      fireEvent.click(screen.getByTestId('edit-field'));
      fireEvent.keyDown(window, { key: 's', metaKey: true });
      await waitFor(() => expect(saveRemoteSchema).toHaveBeenCalled());
      expect(savePicker).not.toHaveBeenCalled();
      expect(dirPicker).not.toHaveBeenCalled();
      // FS-only affordances are hidden in hosted mode.
      expect(screen.queryByText('Save As...')).not.toBeInTheDocument();
      expect(screen.queryByText('Reload from file')).not.toBeInTheDocument();
    } finally {
      delete (window as unknown as Record<string, unknown>).showSaveFilePicker;
      delete (window as unknown as Record<string, unknown>).showDirectoryPicker;
    }
  });

  it('a mid-session 401 on save drops back to the access gate', async () => {
    await passGate();
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-field'));
    vi.mocked(saveRemoteSchema).mockRejectedValue(new AuthError());
    vi.mocked(probeSession).mockRejectedValue(new AuthError()); // stored code is dead too
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(screen.getByLabelText('Access code')).toBeInTheDocument());
  });

  it('non-hosted default renders the local catalogue path unchanged', async () => {
    vi.mocked(isHostedMode).mockReturnValue(false);
    render(<App />);
    // No gate, no remote catalogue -- the local front door renders instead
    // (in jsdom the directory API is absent, so FormCatalogue shows its
    // unsupported-browser message: that IS the local path).
    expect(screen.queryByTestId('access-code-gate')).not.toBeInTheDocument();
    expect(screen.queryByTestId('remote-catalogue')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/File System Access directory API/)).toBeInTheDocument());
    expect(probeSession).not.toHaveBeenCalled();
  });
});
